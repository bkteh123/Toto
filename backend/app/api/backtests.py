from __future__ import annotations

import datetime as dt
import secrets
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.analysis import DEFAULT_WEIGHTS, METHODS
from app.api.collect import session_factory_dep
from app.api.stats import NOTE
from app.db import get_session
from app.jobs import execute_backtest
from app.models import Backtest, Draw, Game

router = APIRouter()

MIN_WARMUP = 10
MIN_TESTED = 5


class BacktestRequest(BaseModel):
    warmup: int = Field(default=30, ge=MIN_WARMUP, le=1000)
    tickets: int = Field(default=5, ge=1, le=50, description="tickets per method per draw")
    methods: list[str] = Field(default_factory=lambda: list(METHODS))
    w10: float = Field(default=DEFAULT_WEIGHTS[0], ge=0)
    w20: float = Field(default=DEFAULT_WEIGHTS[1], ge=0)
    w50: float = Field(default=DEFAULT_WEIGHTS[2], ge=0)
    w100: float = Field(default=DEFAULT_WEIGHTS[3], ge=0)
    mix: float = Field(default=50.0, ge=0, le=100, description="hot share in percent")
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1, description="omit for a fresh random seed")

    @field_validator("methods")
    @classmethod
    def _methods(cls, v: list[str]) -> list[str]:
        bad = [m for m in v if m not in METHODS]
        if bad or not v:
            raise ValueError(f"methods must be a non-empty subset of {list(METHODS)}")
        return list(dict.fromkeys(v))


class BacktestAccepted(BaseModel):
    id: int
    status: str
    seed: int


class BacktestOut(BaseModel):
    id: int
    game: str
    status: str  # queued | running | done | error
    progress: float
    params: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    created_at: dt.datetime
    finished_at: dt.datetime | None
    note: str


@router.post("/games/{code}/backtests", response_model=BacktestAccepted, status_code=202)
def start_backtest(
    code: str,
    body: BacktestRequest,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    factory: sessionmaker[Session] = Depends(session_factory_dep),
):
    game = session.scalar(select(Game).where(Game.code == code))
    if game is None:
        raise HTTPException(404, f"unknown game {code!r}")
    if body.w10 + body.w20 + body.w50 + body.w100 <= 0:
        raise HTTPException(422, "at least one weight must be greater than zero")
    count = session.scalar(select(func.count()).select_from(Draw).where(Draw.game_id == game.id)) or 0
    if count < body.warmup + MIN_TESTED:
        raise HTTPException(
            422,
            f"a backtest needs at least {body.warmup + MIN_TESTED} draws (warm-up {body.warmup} + "
            f"{MIN_TESTED} to test); this game has {count}",
        )
    seed = body.seed if body.seed is not None else secrets.randbits(32)
    bt = Backtest(
        game_id=game.id,
        status="queued",
        progress=0.0,
        params={
            "warmup": body.warmup,
            "tickets": body.tickets,
            "methods": body.methods,
            "weights": [body.w10, body.w20, body.w50, body.w100],
            "mix": body.mix / 100,
            "seed": seed,
            "draws_at_start": count,
        },
    )
    session.add(bt)
    session.commit()
    background.add_task(execute_backtest, factory, bt.id)
    return BacktestAccepted(id=bt.id, status="queued", seed=seed)


@router.get("/backtests/{backtest_id}", response_model=BacktestOut)
def get_backtest(backtest_id: int, session: Session = Depends(get_session)):
    row = session.execute(
        select(Backtest, Game.code).join(Game, Game.id == Backtest.game_id).where(Backtest.id == backtest_id)
    ).first()
    if row is None:
        raise HTTPException(404, f"backtest {backtest_id} not found")
    bt, code = row
    session.refresh(bt)
    return BacktestOut(
        id=bt.id,
        game=code,
        status=bt.status,
        progress=bt.progress,
        params=bt.params,
        result=bt.result,
        error=bt.error,
        created_at=bt.created_at,
        finished_at=bt.finished_at,
        note=NOTE,
    )
