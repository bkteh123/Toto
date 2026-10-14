"""One collector run: plan which pages to fetch, fetch them politely, then store the whole
batch through the cross-check rule (any mismatch => nothing from the batch is inserted).

Modes
  latest  the page of the most recent scheduled draw date (picks up new draws)
  gaps    walk back from the first stored draw above every missing draw number
  auto    latest + gaps (what the scheduler and the "Update now" button use)
  verify  re-fetch pages covering a range of stored draws and compare; inserts nothing new
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.base import Collector, PageLayoutError, SourceUnreachable
from app.collectors.fetcher import FetchResult, Fetcher
from app.config import get_settings
from app.importers.common import ParsedDraw
from app.importers.service import ConflictInfo, missing_draw_numbers, store_draws
from app.models import Draw, Game, ImportLog

MODES = ("auto", "latest", "gaps", "verify")
HISTORIC_TTL = 7 * 24 * 3600.0


@dataclass
class PageReport:
    date: str
    url: str
    status: str  # 'ok' | 'cache' | 'not_published' | 'unexpected' | 'unreachable' | 'layout'
    draws: int = 0
    note: str = ""


@dataclass
class CollectResult:
    log_id: int | None
    status: str
    added: int = 0
    skipped: int = 0
    not_inserted: int = 0
    rejected: int = 0
    conflicts: list[ConflictInfo] = field(default_factory=list)
    pages: list[PageReport] = field(default_factory=list)
    missing_before: list[int] = field(default_factory=list)
    missing_after: list[int] = field(default_factory=list)
    message: str = ""


def vietnam_today(now: dt.datetime | None = None) -> dt.date:
    tz = ZoneInfo(get_settings().timezone)
    return (now.astimezone(tz) if now else dt.datetime.now(tz)).date()


def _runs(numbers: list[int]) -> list[tuple[int, int]]:
    """Contiguous runs of integers, newest run first: [1,2,3,7,8] -> [(7,8),(1,3)]."""
    out: list[tuple[int, int]] = []
    for n in sorted(numbers):
        if out and n == out[-1][1] + 1:
            out[-1] = (out[-1][0], n)
        else:
            out.append((n, n))
    return out[::-1]


class _Run:
    """Page acquisition state for a single collector run."""

    def __init__(self, collector: Collector, fetcher: Fetcher, today: dt.date, max_pages: int, refresh: bool):
        self.collector, self.fetcher, self.today = collector, fetcher, today
        self.max_pages, self.refresh = max_pages, refresh
        self.pages: list[PageReport] = []
        self.by_date: dict[dt.date, list[ParsedDraw] | None] = {}
        self.draws: list[ParsedDraw] = []
        self.unreachable = False

    @property
    def budget_left(self) -> bool:
        return sum(1 for p in self.pages if p.status in ("ok", "cache", "not_published", "unexpected")) < self.max_pages

    def page(self, date: dt.date, fresh: bool = False) -> list[ParsedDraw] | None:
        """Draws on the page for `date`, or None when the page is not what was asked for."""
        if date in self.by_date:
            return self.by_date[date]
        url = self.collector.page_url(date)

        def cacheable(res: FetchResult) -> bool:
            try:
                parsed = self.collector.parse_page(res.text)
            except PageLayoutError:
                return False
            return parsed[0].draw_date == date

        ttl = 0 if (fresh or self.refresh) else HISTORIC_TTL
        try:
            res = self.fetcher.get(url, ttl=ttl, cache_if=cacheable)
        except SourceUnreachable as exc:
            self.pages.append(PageReport(date.isoformat(), url, "unreachable", note=str(exc)))
            self.unreachable = True
            self.by_date[date] = None
            return None
        try:
            parsed = self.collector.parse_page(res.text)
        except PageLayoutError as exc:
            self.pages.append(PageReport(date.isoformat(), url, "layout", note=str(exc)))
            raise
        if parsed[0].draw_date != date:
            # The site answers 200 with the latest page for dates it has nothing for.
            status = "not_published" if date > parsed[0].draw_date else "unexpected"
            self.pages.append(
                PageReport(
                    date.isoformat(), url, status,
                    note=f"asked for {date}, page's newest draw is {parsed[0].draw_no} on {parsed[0].draw_date}",
                )
            )
            self.by_date[date] = None
            return None
        self.pages.append(
            PageReport(date.isoformat(), url, "cache" if res.from_cache else "ok", draws=len(parsed))
        )
        self.by_date[date] = parsed
        self.draws.extend(parsed)
        return parsed

    def walk_back(self, lowest_wanted: int, anchor_date: dt.date) -> None:
        """Fetch the anchor's page, then page back by draw date until `lowest_wanted` is covered."""
        date = anchor_date
        expected: int | None = None  # draw number the next page must start with
        while self.budget_left and not self.unreachable:
            draws = self.page(date)
            if draws is None:
                return
            if expected is not None and draws[0].draw_no != expected:
                # Real data, but the schedule assumption broke (e.g. a skipped draw day).
                self.pages.append(
                    PageReport(
                        date.isoformat(), self.collector.page_url(date), "unexpected",
                        note=f"expected the page to start at draw {expected}, it starts at {draws[0].draw_no}; "
                        "stopped walking back here",
                    )
                )
                return
            oldest = draws[-1]
            if oldest.draw_no <= lowest_wanted:
                return
            expected = oldest.draw_no - 1
            date = self.collector.previous_scheduled(oldest.draw_date)


def run_collect(
    session: Session,
    game: Game,
    collector: Collector,
    fetcher: Fetcher,
    mode: str = "auto",
    today: dt.date | None = None,
    from_no: int | None = None,
    to_no: int | None = None,
    max_pages: int = 40,
    refresh: bool = False,
    log: ImportLog | None = None,
) -> CollectResult:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if game.code != collector.game_code:
        raise ValueError(f"collector {collector.source_name} is for {collector.game_code}, not {game.code}")
    today = today or vietnam_today()
    source = collector.source_name
    if log is None:
        log = ImportLog(game_id=game.id, kind="collector", source=source, status="running")
        session.add(log)
        session.flush()

    missing_before = missing_draw_numbers(session, game)
    run = _Run(collector, fetcher, today, max_pages, refresh)
    stored = {
        no: d
        for no, d in session.execute(
            select(Draw.draw_no, Draw.draw_date).where(Draw.game_id == game.id, Draw.draw_no.is_not(None))
        )
    }

    def anchor_for(upper: int) -> dt.date | None:
        """Date of the lowest stored draw numbered >= upper that has a date."""
        cands = sorted(n for n, d in stored.items() if n >= upper and d is not None)
        return stored[cands[0]] if cands else None

    plan_notes: list[str] = []
    try:
        if mode in ("auto", "latest"):
            run.page(collector.latest_scheduled_on_or_before(today), fresh=True)
        if mode in ("auto", "gaps") and not run.unreachable:
            for a, b in _runs(missing_before):
                anchor = anchor_for(b)
                if anchor is None:
                    plan_notes.append(f"no stored draw above {b} to anchor a walk for {a}-{b}")
                    continue
                run.walk_back(a, anchor)
        if mode == "verify" and stored:
            lo = from_no if from_no is not None else min(stored)
            hi = to_no if to_no is not None else max(stored)
            anchor = anchor_for(hi)
            if anchor is None:
                plan_notes.append(f"no stored draw >= {hi} to anchor verification")
            else:
                run.walk_back(lo, anchor)
    except PageLayoutError as exc:
        log.status = "error"
        log.detail = {"error": "page layout differs", "message": str(exc), "pages": [asdict(p) for p in run.pages]}
        log.finished_at = dt.datetime.now(dt.timezone.utc)
        session.flush()
        return CollectResult(
            log.id, "error", pages=run.pages, missing_before=missing_before, missing_after=missing_before,
            message=f"Page layout differs from what the collector expects; nothing was inserted. {exc}",
        )

    if not run.draws and run.unreachable:
        log.status = "unreachable"
        log.detail = {"pages": [asdict(p) for p in run.pages], "notes": plan_notes}
        log.finished_at = dt.datetime.now(dt.timezone.utc)
        session.flush()
        return CollectResult(
            log.id, "unreachable", pages=run.pages, missing_before=missing_before, missing_after=missing_before,
            message=f"{source} is unreachable; no draws were added and the gaps are unchanged.",
        )

    detail = {
        "mode": mode,
        "today": today.isoformat(),
        "pages": [asdict(p) for p in run.pages],
        "notes": plan_notes,
        "missing_before": missing_before,
    }
    out = store_draws(
        session, game, run.draws, source=source, kind="collector",
        detail=detail, log=log, insert_new=(mode != "verify"),
    )
    missing_after = missing_draw_numbers(session, game)
    log.detail = {**detail, "missing_after": missing_after, "unreachable": run.unreachable}
    session.flush()

    if out.status == "conflict":
        msg = (f"{len(out.conflicts)} fetched draw(s) disagree with stored data. Nothing was inserted; "
               "review the conflicts.")
    else:
        msg = f"Added {out.added}, {out.skipped} already stored and matching."
        if mode == "verify":
            msg = f"Verified {out.skipped} stored draw(s) match {source}; {out.not_inserted} not stored (not inserted)."
        if run.unreachable:
            msg += " Some pages were unreachable; those gaps were left as they are."
    return CollectResult(
        log.id, out.status, added=out.added, skipped=out.skipped, not_inserted=out.not_inserted,
        rejected=len(out.rejected), conflicts=out.conflicts, pages=run.pages,
        missing_before=missing_before, missing_after=missing_after, message=msg,
    )
