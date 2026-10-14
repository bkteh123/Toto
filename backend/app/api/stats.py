from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis import (
    DEFAULT_WEIGHTS,
    PERIODS,
    compute_scores,
    expected_appearances,
    match_mean,
    match_variance,
    prob_at_least,
)
from app.db import get_session
from app.models import Draw, Game

router = APIRouter()

NOTE = (
    "Scores describe how numbers behaved in past draws. They are not probabilities of "
    "winning: every draw is independent of the ones before it."
)


class NumberRow(BaseModel):
    number: int
    appearances: int  # in the requested period
    frequency: float
    gap: int
    rank: int
    hot: float
    cold: float
    combined: float
    cls: Literal["Hot", "Cold", "Neutral"]
    counts: dict[str, int]  # "10","20","50","100","all"


class Chip(BaseModel):
    number: int
    appearances: int
    gap: int


class Expectation(BaseModel):
    ticket_mean_matches: float
    ticket_variance: float
    p_at_least_3: float
    appearances_in_period: float  # period * K / N


class StatsResponse(BaseModel):
    game: str
    n: int
    k: int
    draw_count: int
    period: str
    span: int  # draws the period covers: min(period, draw_count)
    weights: list[float]  # normalised to sum 1, for the last 10/20/50/100 draws
    mix: float  # hot share 0..1
    expectation: Expectation
    rows: list[NumberRow]
    hottest_10: list[Chip]
    coldest: list[Chip]
    note: str


def load_draw_numbers(session: Session, game: Game) -> list[list[int]]:
    """All draws of a game, oldest first (date, then draw number, then insertion order)."""
    rows = session.scalars(
        select(Draw.numbers)
        .where(Draw.game_id == game.id)
        .order_by(Draw.draw_date.asc().nulls_first(), Draw.draw_no.asc().nulls_first(), Draw.id.asc())
    ).all()
    return [list(r) for r in rows]


@router.get("/games/{code}/stats", response_model=StatsResponse)
def game_stats(
    code: str,
    period: Literal["10", "20", "50", "100", "all"] = "10",
    w10: float = Query(DEFAULT_WEIGHTS[0], ge=0),
    w20: float = Query(DEFAULT_WEIGHTS[1], ge=0),
    w50: float = Query(DEFAULT_WEIGHTS[2], ge=0),
    w100: float = Query(DEFAULT_WEIGHTS[3], ge=0),
    mix: float = Query(50.0, ge=0, le=100, description="hot share in percent"),
    session: Session = Depends(get_session),
):
    game = session.scalar(select(Game).where(Game.code == code))
    if game is None:
        raise HTTPException(404, f"unknown game {code!r}")
    if w10 + w20 + w50 + w100 <= 0:
        raise HTTPException(422, "at least one weight must be greater than zero")

    n, k = game.max_number, game.pick_count
    draws = load_draw_numbers(session, game)
    table = compute_scores(draws, n, (w10, w20, w50, w100), mix / 100)
    per: str | int = "all" if period == "all" else int(period)
    span = table.span(per)

    rows = [
        NumberRow(
            number=r.number,
            appearances=r.appearances(per),
            frequency=table.frequency(r.number, per),
            gap=r.gap,
            rank=r.rank,
            hot=r.hot,
            cold=r.cold,
            combined=r.combined,
            cls=r.cls,  # type: ignore[arg-type]
            counts={**{str(p): r.counts[p] for p in PERIODS}, "all": r.total},
        )
        for r in table.rows
    ]
    chips = lambda stats: [Chip(number=s.number, appearances=s.counts[10], gap=s.gap) for s in stats]  # noqa: E731
    return StatsResponse(
        game=code,
        n=n,
        k=k,
        draw_count=table.draw_count,
        period=period,
        span=span,
        weights=list(table.weights),
        mix=table.mix,
        expectation=Expectation(
            ticket_mean_matches=match_mean(n, k),
            ticket_variance=match_variance(n, k),
            p_at_least_3=prob_at_least(n, k, 3),
            appearances_in_period=expected_appearances(span, n, k),
        ),
        rows=rows,
        hottest_10=chips(table.hottest(10, 8)),
        coldest=chips(table.coldest(8)),
        note=NOTE,
    )
