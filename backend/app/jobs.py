"""Background jobs: running a backtest, and cleaning up after a restart."""

from __future__ import annotations

import dataclasses
import datetime as dt
import threading
import time

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.backtest import BacktestResult, run_backtest
from app.models import Backtest, Draw, Game, ImportLog

# At most two backtests compute at once; the rest wait as 'queued'.
_SLOTS = threading.BoundedSemaphore(2)
PROGRESS_STEP = 0.02
PROGRESS_MIN_SECONDS = 0.5


def result_to_json(r: BacktestResult) -> dict:
    d = dataclasses.asdict(r)
    d.pop("tickets_log", None)
    for m in d["methods"]:
        m["histogram"] = {str(h): c for h, c in m["histogram"].items()}
        m["curve"] = [round(x, 6) for x in m["curve"]]
    return d


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def execute_backtest(factory: sessionmaker[Session], backtest_id: int) -> None:
    """Run one queued backtest to completion. Never raises; failures land in the row."""
    with _SLOTS:
        with factory() as session:
            bt = session.get(Backtest, backtest_id)
            if bt is None or bt.status not in ("queued",):
                return
            try:
                game = session.get(Game, bt.game_id)
                p = bt.params
                rows = session.execute(
                    select(Draw.draw_no, Draw.numbers)
                    .where(Draw.game_id == game.id)
                    .order_by(Draw.draw_date.asc().nulls_first(), Draw.draw_no.asc().nulls_first(), Draw.id.asc())
                ).all()
                numbers = [list(r.numbers) for r in rows]
                bt.status, bt.progress = "running", 0.0
                session.commit()

                last_commit = [0.0, time.monotonic()]

                def report(frac: float) -> None:
                    now = time.monotonic()
                    if frac >= 1.0 or (
                        frac - last_commit[0] >= PROGRESS_STEP and now - last_commit[1] >= PROGRESS_MIN_SECONDS
                    ):
                        bt.progress = min(frac, 0.999)
                        session.commit()
                        last_commit[0], last_commit[1] = frac, now

                result = run_backtest(
                    numbers,
                    game.max_number,
                    game.pick_count,
                    warmup=p["warmup"],
                    tickets=p["tickets"],
                    methods=p["methods"],
                    weights=p["weights"],
                    mix=p["mix"],
                    seed=p["seed"],
                    progress=report,
                )
                out = result_to_json(result)
                out["labels"] = [rows[i].draw_no for i in range(p["warmup"], len(rows))]
                out["history_draws"] = len(rows)
                bt.result, bt.progress, bt.status = out, 1.0, "done"
            except Exception as exc:  # recorded for the user; the job runner must not die
                session.rollback()
                bt = session.get(Backtest, backtest_id)
                bt.status, bt.error = "error", f"{type(exc).__name__}: {exc}"
            bt.finished_at = _now()
            session.commit()


def recover_interrupted_jobs(session: Session) -> dict[str, int]:
    """After a restart nothing is still running: mark leftovers as failed instead of
    leaving the UI waiting forever."""
    bt = session.execute(
        update(Backtest)
        .where(Backtest.status.in_(("queued", "running")))
        .values(status="error", error="interrupted by a server restart", finished_at=_now())
    ).rowcount
    logs = session.execute(
        update(ImportLog)
        .where(ImportLog.status == "running")
        .values(
            status="error",
            finished_at=_now(),
            detail={"error": "interrupted", "message": "interrupted by a server restart"},
        )
    ).rowcount
    session.flush()
    return {"backtests": bt, "import_logs": logs}
