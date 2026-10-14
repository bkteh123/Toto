from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.collectors.factory import game_lock, make_fetcher
from app.collectors.fetcher import Fetcher
from app.collectors.registry import get_collector
from app.collectors.runner import run_collect
from app.db import get_session, get_session_factory
from app.models import DrawConflict, Game, ImportLog

router = APIRouter()


# Overridable in tests (and later for deployment tweaks).
def session_factory_dep() -> sessionmaker[Session]:
    return get_session_factory()


def fetcher_factory_dep() -> Callable[[], Fetcher]:
    return make_fetcher


class CollectRequest(BaseModel):
    mode: Literal["auto", "latest", "gaps", "verify"] = "auto"
    from_draw_no: int | None = Field(default=None, ge=1)
    to_draw_no: int | None = Field(default=None, ge=1)
    refresh: bool = False


class CollectAccepted(BaseModel):
    log_id: int
    status: str


class LogOut(BaseModel):
    id: int
    game: str
    kind: str
    source: str
    status: str
    added: int
    skipped: int
    rejected: int
    conflicts: int
    started_at: dt.datetime
    finished_at: dt.datetime | None
    detail: dict[str, Any] | None


class ConflictOut(BaseModel):
    id: int
    draw_no: int | None
    draw_date: dt.date | None
    existing_numbers: list[int] | None
    incoming_numbers: list[int]
    reason: str
    source: str
    status: str
    import_log_id: int | None
    created_at: dt.datetime


def _background(
    factory: sessionmaker[Session],
    fetcher_factory: Callable[[], Fetcher],
    game_code: str,
    log_id: int,
    req: CollectRequest,
) -> None:
    lock = game_lock(game_code)
    try:
        with factory() as session:
            game = session.scalar(select(Game).where(Game.code == game_code))
            log = session.get(ImportLog, log_id)
            collector = get_collector(game_code)
            try:
                run_collect(
                    session, game, collector, fetcher_factory(), mode=req.mode,
                    from_no=req.from_draw_no, to_no=req.to_draw_no, refresh=req.refresh, log=log,
                )
            except Exception as exc:  # the run must never leave a log stuck on 'running'
                session.rollback()
                log = session.get(ImportLog, log_id)
                log.status = "error"
                log.detail = {"error": "unexpected failure", "message": f"{type(exc).__name__}: {exc}"}
                log.finished_at = dt.datetime.now(dt.timezone.utc)
            session.commit()
    finally:
        lock.release()


@router.post("/games/{code}/collect", response_model=CollectAccepted, status_code=202)
def trigger_collect(
    code: str,
    background: BackgroundTasks,
    req: CollectRequest | None = None,
    session: Session = Depends(get_session),
    factory: sessionmaker[Session] = Depends(session_factory_dep),
    fetcher_factory: Callable[[], Fetcher] = Depends(fetcher_factory_dep),
):
    req = req or CollectRequest()
    game = session.scalar(select(Game).where(Game.code == code))
    if game is None:
        raise HTTPException(404, f"unknown game {code!r}")
    if get_collector(code) is None:
        raise HTTPException(501, f"no result source is wired up for {code!r} yet; use file import")
    lock = game_lock(code)
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "an update for this game is already running")
    try:
        log = ImportLog(game_id=game.id, kind="collector", source="manual trigger", status="running")
        session.add(log)
        session.commit()
        background.add_task(_background, factory, fetcher_factory, code, log.id, req)
    except Exception:
        lock.release()
        raise
    return CollectAccepted(log_id=log.id, status="running")


@router.get("/collect/logs", response_model=list[LogOut])
def collect_logs(
    game: str | None = None,
    limit: int = Query(20, ge=1, le=200),
    session: Session = Depends(get_session),
):
    q = select(ImportLog, Game.code).join(Game, Game.id == ImportLog.game_id)
    if game:
        q = q.where(Game.code == game)
    rows = session.execute(q.order_by(ImportLog.id.desc()).limit(limit)).all()
    return [
        LogOut(
            id=l.id, game=code, kind=l.kind, source=l.source, status=l.status, added=l.added,
            skipped=l.skipped, rejected=l.rejected, conflicts=l.conflicts,
            started_at=l.started_at, finished_at=l.finished_at, detail=l.detail,
        )
        for l, code in rows
    ]


@router.get("/games/{code}/conflicts", response_model=list[ConflictOut])
def list_conflicts(
    code: str,
    status: Literal["open", "resolved", "all"] = "open",
    session: Session = Depends(get_session),
):
    game = session.scalar(select(Game).where(Game.code == code))
    if game is None:
        raise HTTPException(404, f"unknown game {code!r}")
    q = select(DrawConflict).where(DrawConflict.game_id == game.id)
    if status != "all":
        q = q.where(DrawConflict.status == status)
    return session.scalars(q.order_by(DrawConflict.id.desc())).all()
