# Royal Yellow Analyzer

A lottery **historical-analysis** web app for Codencode Academy (codencode.my). It analyses past draws, ranks numbers by historical statistics, generates suggested combinations and Bao (system) sets, and runs walk-forward backtests against random selection.

> It is a statistical analysis tool, **not** a prediction engine. Scores describe past behaviour and are not probabilities of winning. A fair draw has no memory.

**Status:** all nine build steps are written; see the build order at the bottom. The backend and frontend test suites pass; the Docker setup has not been run yet.

## Running it

Pick one. All three start with the 122-draw Mega 6/45 history already loaded.

### A. Docker Compose (production-like)

Needs Docker with the Compose plugin.

```bash
cp .env.example .env            # Windows PowerShell: Copy-Item .env.example .env
# edit .env: set POSTGRES_PASSWORD (required; compose refuses to start without it)
docker compose up --build
```

| URL | What |
|---|---|
| http://localhost:8080 | the app (change the port with `WEB_PORT` in `.env`) |
| http://127.0.0.1:8000/docs | API docs (bound to loopback only) |

The backend applies migrations and loads `seed/mega645.csv` on every start (it skips draws that already exist). Useful commands:

```bash
docker compose logs -f backend          # follow the API / scheduler log
docker compose exec backend python -m app.collect --game vn_mega_645     # fetch the latest results now
docker compose down                     # stop, keep the data
docker compose down -v                  # stop and DELETE the database
```

### B. Local development without Docker

Needs Python 3.12+ and Node 22+ (24 LTS tested). No PostgreSQL install required: the dev launcher starts an embedded PostgreSQL 16.

Terminal 1, the API:

```bash
python -m venv .venv            # keep it outside OneDrive-synced folders if you can
.venv/Scripts/activate          # Linux/macOS: source .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend
python scripts/dev_server.py    # http://127.0.0.1:8000, data kept in ~/.royal-yellow/pgdata
```

Terminal 2, the web app:

```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173, proxies /api to 127.0.0.1:8000
```

Options for `dev_server.py`: `--port`, `--data-dir`, `--no-seed`, and `--scheduler` (the scheduled result updates are **off** by default so a dev run makes no outbound requests; the "Update now" button still works). To use your own PostgreSQL instead, set `DATABASE_URL` (see `.env.example`), then `alembic upgrade head` and `uvicorn app.main:app --reload` from `backend/`.

### C. Tests

```bash
cd backend && python -m pytest          # 348 tests, embedded PostgreSQL, no Docker needed
cd frontend && npm test                 # 24 tests (vitest)
cd frontend && npm run build            # type-check + production bundle
```

Set `TEST_DATABASE_URL=postgresql+psycopg://user:pass@host/db` to run the backend tests against your own PostgreSQL.

### Configuration

Read from the environment or `.env` (copy `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `royal` / (required) / `royal_yellow` | database credentials (Docker) |
| `DATABASE_URL` | local `postgresql+psycopg://...` | SQLAlchemy URL (set automatically by compose) |
| `SCHEDULER_ENABLED` | `true` | run the Wed/Fri/Sun 21:00 (Asia/Ho_Chi_Minh) result update |
| `COLLECTOR_MIN_INTERVAL_SECONDS` | `5` | minimum gap between requests to one source |
| `COLLECTOR_USER_AGENT` | descriptive RoyalYellowAnalyzer UA | sent to result sources |
| `SEED_ON_START` | `true` | Docker only: load the seed CSV at startup |
| `WEB_PORT` | `8080` | Docker only: published port of the web app |

### First things to try

1. Open the app. The **Data** panel shows the stored draws and the latest result; **Update now** runs the collector (needs internet).
2. Import your own history from the Data panel: a `.csv`/`.txt` (one draw per line, set "skip leading numbers" to 1 if each line starts with a draw ID) or an Excel grid. A file that disagrees with stored draws is held back as a conflict, never overwritten.
3. Adjust the weights in the score table, generate combinations and a Bao set, and download any of them as CSV or Excel.
4. Run a **walk-forward backtest** to see whether any method actually beats random selection (on real data it does not).

## Architecture

```
┌──────────────┐   REST/JSON   ┌──────────────────────────────┐   SQL   ┌──────────────┐
│ React + Vite │ ────────────► │ FastAPI backend              │ ──────► │ PostgreSQL 16│
│ (nginx)      │               │  api/        routes          │         └──────────────┘
└──────────────┘               │  importers/  CSV, Excel grid │
                               │  analysis/   pure functions  │  (step 4)
                               │  collectors/ one class/source│  (step 3)
                               │  APScheduler (result updates)│  (step 3)
                               └──────────────────────────────┘
```

| Layer | Responsibility |
|---|---|
| `app/validation.py` | The only place that decides whether numbers are legal: exactly K distinct integers in 1..N. Nothing guesses or auto-fills. |
| `app/importers/` | Pure parsers (`text_csv`, `excel_grid`), the grid exporter, and `service.py` which persists with the cross-check rule. |
| `app/analysis/` (step 4) | Pure functions over a list of draws, oldest to newest, so the backtest reuses them unchanged. |
| `app/collectors/` (step 3) | One class per source behind a common interface; polite, cached, cross-checked. |
| `app/models.py` | SQLAlchemy 2.x schema. Alembic migration `0001` mirrors it (`alembic check` is clean). |

### Database schema

| Table | Purpose |
|---|---|
| `games` | Rules per game: N, K, bonus flag/range, ticket price, currency. DB `CHECK`s enforce N 2-500, K 1-20, K < N. |
| `draws` | `game_id, draw_no, draw_date, numbers int[] (sorted), bonus, source`. Unique on `(game_id, draw_no)` and `(game_id, draw_date)`. |
| `import_logs` | One row per file import or collector run: source, added / skipped / rejected / conflicts, status. |
| `draw_conflicts` | Incoming draws that disagree with stored ones, held for manual review. |
| `backtests` | Parameters, status, progress and result JSON of background backtests. |

Design notes:

- `draw_date` and `draw_no` are individually nullable (at least one is required) so a text file without dates can still be analysed in file order, oldest to newest. A row with neither is rejected at storage time because it cannot be identified or de-duplicated.
- **Cross-check rule:** if any incoming draw disagrees with a stored draw, *nothing* from that batch is inserted; the disagreements go to `draw_conflicts` and the UI. This applies to file imports as well as the collector.
- **Never fabricate:** rows with a draw number but no numbers are reported as *missing* and left empty.

### Import formats

- **Plain CSV/text:** one draw per line; date as `dd/mm/yyyy` or `yyyy-mm-dd`; remove the date, take all standalone integers, skip the first S ("skip leading numbers", for draw-ID columns), take the next K. Lines with no standalone integer are headers (so `date,n1,n2` is a header, not a draw 1-2). When S >= 1 the first skipped integer is stored as the draw number.
- **Excel grid:** sheet `45` (or first sheet), header row with `Date` in A, `Draw` in C and 1..N from column E; each drawn number sits in its own column as its own value. Cell value must equal its column's number, and a row must have exactly K.
- **Grid export:** same layout (newest at the top, missing draw numbers kept as number-only rows), with the codencode.my wordmark in A2.

## Collector (automatic result updates)

`app/collectors/` has one class per source behind the `Collector` interface (`base.py`). The only source so far is **Minh Ngoc** for Vietlott Mega 6/45 (`minhngoc.py`).

How the source behaves (observed 2026-10-13):

- URL `.../dien-toan-vietlott/mega-6x45/DD-MM-YYYY.html`; each page lists that draw plus the 9 before it, newest first.
- A date with no published draw (future, or not a draw day) is **not a 404**. The site answers 200 with the *latest* page. The collector therefore checks that the page's newest draw date equals the date it asked for, and treats anything else as "not published yet".
- There is no `robots.txt` (404). The collector is polite anyway: one request per `COLLECTOR_MIN_INTERVAL_SECONDS` (default 5), a descriptive User-Agent, an on-disk page cache, bounded retries.

Run modes (`python -m app.collect --mode ...`, `POST /games/{code}/collect`):

| Mode | What it does |
|---|---|
| `latest` | fetch the page of the most recent scheduled draw date |
| `gaps` | for each run of missing draw numbers, start at the first stored draw above it and page back until covered |
| `auto` | `latest` + `gaps` (scheduler and "Update now") |
| `verify` | re-read a range of stored draws from the source and compare; inserts nothing |

Guarantees:

- **Cross-check:** every fetched draw that already exists is compared. Any mismatch => nothing from that batch is inserted, the conflict is stored in `draw_conflicts` (`GET /games/{code}/conflicts`) and the run is logged with status `conflict`.
- **No guessing:** a page whose layout differs (no result blocks, a block without 6 numbers, blocks out of order) stops the run with status `error` and inserts nothing. An unreachable source gives status `unreachable` (or a partial run that says which pages failed) and the gaps stay.
- **Schedule:** draw days Wed/Fri/Sun. The job runs at 21:00 Asia/Ho_Chi_Minh and, if that day's draw is still missing, retries hourly (max 12 attempts). A conflict or layout error is not retried; it needs a person.
- **One run per game at a time** (manual and scheduled runs share a lock; a second manual trigger gets 409).

```bash
cd backend
python -m app.collect --game vn_mega_645                        # latest + gap-fill
python -m app.collect --mode verify --from 1453 --to 1574       # compare stored history, insert nothing
```

Every run is recorded in `import_logs` (`GET /collect/logs`).

## Statistics engine

`app/analysis/` is pure Python over a list of draws (oldest to newest): no database, no clock, no randomness, so the backtest can call it on any prefix of the history unchanged.

| Quantity | Definition |
|---|---|
| appearances(p) | times a number is in the last p draws (p = 10, 20, 50, 100) and in all draws |
| frequency | appearances / min(p, draws) |
| draws since (gap) | 0 if in the latest draw; equals the draw count if never seen |
| all-time rank | 1 = most appearances; ties go to the lower number |
| hot | sum over p of `w_p * count_p(n) / max_k count_p(k)`; weights default 40/25/20/15, normalised to sum 1 |
| cold | `0.5 * (1 - hot) + 0.5 * gap / max gap` |
| combined | `m * hot + (1 - m) * cold`, hot share `m` default 50% |
| class | by hot score (ties to the lower number): top ceil(N/3) Hot, bottom ceil(N/3) Cold, rest Neutral |

Random expectation (`expectation.py`): a ticket of S numbers against a K-number draw is hypergeometric, mean `S*K/N` (`K^2/N` for a normal ticket), variance `S*(K/N)*((N-K)/N)*((N-S)/(N-1))`, and P(>=m matches) is summed exactly with integer arithmetic. For 6/45: mean 0.8, variance 0.6145, P(>=3) = 2.3834%.

`GET /games/{code}/stats?period=10|20|50|100|all&w10=&w20=&w50=&w100=&mix=` returns the table, the expectation block and the "at a glance" chips. `mix` is a percentage. Scores describe past behaviour and are not probabilities of winning; the response carries that note.

The tests compare the engine against **golden values produced by running the original prototype's own JavaScript** (`tests/fixtures/gen_prototype_golden.js`, `prototype_scores_golden.json`), at the full history, at four earlier prefixes, and with non-default weights and hot share.

> **Prototype bug, not reproduced:** the prototype's CSV parser reads the header `date,n1,...,n6` as a draw `1-2-3-4-5-6`, so it reports 123 draws and inflates all-time counts of numbers 1-6. Hot/cold/gap/class are unaffected at 122 draws (the stray draw falls outside the 100-draw window). The golden values are generated from the seed with the header removed (122 draws), and the importer here only treats standalone integers as numbers, so a header can never become a draw.

## Combination generator

`app/analysis/generator.py`. Every method is weighted sampling without replacement:

| Method | Weight per number |
|---|---|
| hot | hot² |
| cold | cold² |
| mixed | ceil(K/2) numbers by hot², the rest by cold², never overlapping |
| weighted | combined² |
| random | uniform (the baseline) |

User-facing generation uses `secrets.SystemRandom` (CSPRNG); backtests use `seeded_rng(seed)` so a run is reproducible. Weights are floored at 1e-6 so a combination always completes. 1-50 combinations are requested; duplicates are dropped and every one is validated (K distinct integers in 1..N). If a game cannot produce that many distinct combinations the result is **shorter and says so** (`shortfall`), it is never padded.

`POST /games/{code}/generate` body `{method, count}` (plus optional `w10..w100`, `mix` to follow the scoring table on screen).

## Bao (system) pick

`app/analysis/bao.py`, `POST /games/{code}/bao` with `{size, window, end_draw_no}`.

- Rank numbers by appearances in the last W draws up to and including the ending draw; ties by **most recent appearance first**, then lowest number. Numbers tied with the last one in the set but left out are listed as equal alternatives.
- Valid sizes: K-1 (the special "Bao 5" for a 6-number game) and K+1 .. 18.
- lines = C(S, K); cost = lines x ticket price; jackpot is "1 in C(N,K) / lines".
- Later draws: every draw after the ending draw with the hits from the set.
- Rule check: "top S of the last W" replayed on every draw that has W earlier draws, compared with the random expectation S x K / N.

### Bao 5 rule (verified 2026-10-13 against secondary sources)

Vietlott's own site returns 403 to automated requests, so the rule was cross-checked against vi.wikipedia, atrungroi.com and news explainers, which agree:

- the player picks **5** numbers; the system pairs them with **each of the other N-5 numbers**, so lines = N - 5 (**40** for 6/45, **50** for 6/55), priced at lines x 10,000 VND (400,000 / 500,000);
- if all 5 numbers are among the 6 drawn, exactly one line is the jackpot (the other N-6 lines match 5);
- hence the generic `C(S,K)` cannot be used (C(5,6) = 0), but the same "1 in C(N,K) / lines" formula holds: P = (N-5) / C(N,6).

Confirm with the operator before relying on it for anything involving money. Prize amounts per tier are not modelled.

### Reference result

With the seed, S=8, W=10, ending draw 1574: set `02 03 09 15 16 27 33 41`, equal alternatives `29 30 12 10 36 37 20 06 31 25`; rule check 1.03 hits/draw vs 1.07 random, 4 draws with 3+ hits over **112** draws (the "113" in the original brief is the prototype's header-row bug: 123 - 10). Tests also compare 96 size/window/ending-draw combinations against golden values produced by the prototype's own `baoSet` code.

## Walk-forward backtest

`app/analysis/backtest.py`, jobs in `app/jobs.py`, API in `app/api/backtests.py`.

For every draw `t >= warm-up` the scores are computed from draws `[0, t)` only, tickets are generated per method, and matches are counted against draw `t`. Tests prove draw `t` and everything after it is invisible when its tickets are made (the scoring function is spied on, and draws are altered after the fact).

| Option | Default |
|---|---|
| warm-up draws | 30 (minimum 10) |
| tickets per method per draw | 5 (1-50) |
| methods | hot, cold, mixed, weighted, random |
| weights / hot share | as the scoring table (40/25/20/15, 50%) |
| seed | random 32-bit, stored with the run so it can be reproduced |

Each method draws from its **own** RNG stream (seed + method name), so including or excluding a method never changes another method's tickets.

Per method: tickets, average matches, % vs the hypergeometric mean, 3+ rate next to the exact expected rate, `z = (mean - mu) / sqrt(sigma^2 / n)`, two-sided exact normal p-value (`erfc`), the cumulative-average curve, and the histogram of matches.

### Why "beats random" needs two tests

Tickets bought for the same draw are correlated (a hot method buys overlapping tickets), so the spec's ticket-level z is too optimistic for them. `scripts/calibrate_backtest.py` measured it on 1,200 genuinely random histories (nominal rate 1%):

| method | ticket-level p<.01 | per-draw p<.01 |
|---|---|---|
| hot | **3.7%** | 0.7% |
| cold | **3.2%** | 0.6% |
| mixed | 1.2% | 0.9% |
| weighted | 0.8% | 0.6% |
| random | 1.0% | 0.9% |

So the table shows the spec's ticket-level `z` / `p` **and** a per-draw t-test on the per-draw mean hits (which does not assume independent tickets). A method is only called "beats random" when both give p < 0.01 and it is above expectation. A method that passes only the ticket-level test is listed under `ticket_only` and the verdict says it is not counted. The random control is never flagged.

Verdict text (English and Chinese are both returned): if nothing beats random it says so plainly and calls it the expected result for a fair draw; if something does, it warns about multiple comparisons and correlated tickets and says it must repeat on new draws.

### Running it

`POST /games/{code}/backtests` returns `202 {id, status: "queued", seed}`. A background job (at most two at once) fills the `backtests` table; poll `GET /backtests/{id}` for `status` (queued / running / done / error), `progress` (0-1) and `result`. After a server restart any queued/running backtest or collector run is marked `error` ("interrupted by a server restart") instead of staying "running" forever.

### What it says about your data

On the 122 seed draws (92 tested draws, 5 tickets each, seed 20261013) no method beats random; averages are 0.77-0.83 against 0.80 expected, and the random control itself lands at 0.76. Across 12 other seeds the random control's average ranges 0.70-0.89, which is the noise any method has to clear.

## Exports

Every table and result on the dashboard can be downloaded (`app/api/exports.py`). CSV files are UTF-8 with a BOM so Excel opens them correctly; Excel files carry the codencode.my wordmark and, for scores and picks, the "not probabilities of winning" note.

| Endpoint | Contents |
|---|---|
| `GET /games/{code}/export/stats.{csv\|xlsx}?period=&w10=..&mix=` | the scoring table for the period and weights on screen, plus the per-window counts |
| `GET /games/{code}/export/draws.{csv\|xlsx}` | all stored draws. The `.xlsx` is the Excel grid layout the importer reads back (missing draw numbers kept as number-only rows); the `.csv` re-imports with "skip leading numbers = 1" |
| `GET /games/{code}/export/bao.{csv\|xlsx}?size=&window=&end_draw_no=` | the Bao set with appearances and whether each number is a sure-in or a tie cut; `.xlsx` adds lines, cost and odds |
| `POST /games/{code}/export/combos.{csv\|xlsx}` body `{method, combinations}` | the picks on screen. Generated picks are random and cannot be recomputed, so the server validates and echoes them (422 if any is not K distinct numbers in 1..N) |

A game with no stored draws answers `409` instead of producing an empty file.

## Frontend

`frontend/` is React 18 + Vite + TypeScript, TanStack Query for data, Recharts for the chart and react-i18next (Chinese by default, English toggle). The Royal Yellow look (gold ball gradient, Cinzel / Figtree / DM Mono / Noto Sans SC, 400 px mobile layout) is in `src/styles/theme.css`. Backtest verdict text comes from the API in both languages, and both p-value columns plus the `ticket_only` note are shown. Every screen that shows scores carries the disclaimer. To run it, see [Running it](#running-it).

## Docker

How to start it is under [Running it](#a-docker-compose-production-like). Three services: `db` (PostgreSQL 16, volume `pgdata`), `backend` (runs `alembic upgrade head`, loads `seed/mega645.csv` idempotently unless `SEED_ON_START=false`, then uvicorn) and `frontend` (nginx serving the build and proxying `/api/` to the backend). `/health` checks database reachability and is used for the container health checks. The collector's page cache lives in the `collector_cache` volume. The compose file was written without Docker available on the development machine, so run `docker compose config` and a first `up` before relying on it.

## Seed data

`seed/mega645.csv` (`date,n1,n2,n3,n4,n5,n6`) holds Mega 6/45 draws **1453-1574** (2 Jan to 11 Oct 2026, 122 draws) taken from the seed embedded in the original prototype.

Provenance, as verified on 2026-10-13:

- All 57 draws that carry numbers in `Mega 6-45 Vietnam.xlsx` agree exactly with the seed (date, numbers and draw number).
- The other 65 (1479-1542 and 1571) came from the prototype seed. On 2026-10-13 the collector fetched them live from Minh Ngoc into a database holding only the workbook's 57 draws: the result was identical to the seed for all 122 draws, and `verify` over 1453-1574 matched every stored draw with 0 conflicts.
- Dates are exactly the Wed/Fri/Sun schedule with no gaps, so draw numbers are assigned by position starting at 1453.

Docker and `dev_server.py` load it automatically. To load it by hand into any database:

```bash
cd backend
alembic upgrade head
python -m app.seed --csv ../seed/mega645.csv --game vn_mega_645 --first-draw-no 1453
```

`scripts/xlsx_to_seed_csv.py` converts a grid workbook to the same CSV format and lists any draw numbers it does not contain; it never interpolates.

## Build order

1. Architecture and schema with migrations ✅
2. Import pipeline (CSV, Excel grid, grid export) ✅
3. Collector with gap-fill, cross-check and scheduler ✅
4. Statistics engine ✅
5. Generator and Bao ✅
6. Backtest ✅
7. React dashboard with i18n and the Royal Yellow theme ✅
8. CSV and xlsx exports ✅
9. Docker Compose, deployment notes ✅ (not run here: no Docker on the dev machine)
