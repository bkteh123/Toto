"""Scheduled result updates.

On each draw day at 21:00 Asia/Ho_Chi_Minh the job collects the latest results; if that
day's draw is still missing it retries hourly (bounded by MAX_ATTEMPTS). A conflict or a
layout error is NOT retried: it needs a human, and repeating it changes nothing.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.collectors.factory import game_lock, make_fetcher
from app.collectors.fetcher import Fetcher
from app.collectors.registry import collector_game_codes, get_collector
from app.collectors.runner import run_collect, vietnam_today
from app.config import Settings
from app.models import Draw, Game

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 12  # first run + 11 hourly retries
_DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def scheduled_collect(
    session_factory: sessionmaker[Session],
    game_code: str,
    attempt: int = 1,
    scheduler: BackgroundScheduler | None = None,
    fetcher_factory: Callable[[], Fetcher] = make_fetcher,
    now: dt.datetime | None = None,
) -> str:
    """Run one scheduled attempt. Returns 'done', 'retry', 'gave_up', 'busy' or a failure status."""
    collector = get_collector(game_code)
    if collector is None:
        return "no_collector"
    lock = game_lock(game_code)
    if not lock.acquire(blocking=False):
        log.info("collect for %s skipped: another run is in progress", game_code)
        return "busy"
    try:
        with session_factory() as session:
            game = session.scalar(select(Game).where(Game.code == game_code))
            if game is None:
                return "no_game"
            today = vietnam_today(now)
            result = run_collect(session, game, collector, fetcher_factory(), mode="auto", today=today)
            session.commit()
            expected = collector.latest_scheduled_on_or_before(today)
            have = (
                session.scalar(
                    select(Draw.id).where(Draw.game_id == game.id, Draw.draw_date == expected)
                )
                is not None
            )
    finally:
        lock.release()

    if have:
        return "done"
    if result.status not in ("ok", "unreachable"):
        return result.status  # conflict / error: needs a human
    if not collector.is_draw_day(today):
        return "done"  # manual or catch-up run on a non-draw day; nothing is due
    if attempt >= MAX_ATTEMPTS:
        log.warning("collect for %s gave up after %s attempts", game_code, attempt)
        return "gave_up"
    if scheduler is not None:
        tz = ZoneInfo(Settings().timezone)
        run_at = (now or dt.datetime.now(tz)) + dt.timedelta(hours=1)
        scheduler.add_job(
            scheduled_collect,
            DateTrigger(run_date=run_at),
            args=[session_factory, game_code, attempt + 1],
            kwargs={"scheduler": scheduler, "fetcher_factory": fetcher_factory},
            id=f"collect-retry-{game_code}",
            replace_existing=True,
        )
    return "retry"


def build_scheduler(
    session_factory: sessionmaker[Session],
    settings: Settings,
    fetcher_factory: Callable[[], Fetcher] = make_fetcher,
) -> BackgroundScheduler:
    tz = ZoneInfo(settings.timezone)
    sched = BackgroundScheduler(timezone=tz)
    for code in collector_game_codes():
        c = get_collector(code)
        assert c is not None
        sched.add_job(
            scheduled_collect,
            CronTrigger(
                day_of_week=",".join(_DAY_NAMES[d] for d in c.draw_weekdays),
                hour=c.first_run_hour,
                minute=0,
                timezone=tz,
            ),
            args=[session_factory, code, 1],
            kwargs={"scheduler": sched, "fetcher_factory": fetcher_factory},
            id=f"collect-{code}",
            misfire_grace_time=3600,
            coalesce=True,
        )
    return sched
