"""Combination generator and Bao endpoints."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis import DEFAULT_WEIGHTS, compute_scores, match_mean, prob_at_least
from app.analysis.bao import (
    bao_set,
    hits_in,
    jackpot_one_in,
    line_count,
    rule_check,
    valid_sizes,
)
from app.analysis.generator import (
    MAX_COUNT,
    METHODS,
    generate_combinations,
    system_rng,
)
from app.api.stats import NOTE
from app.db import get_session
from app.models import Draw, Game

router = APIRouter()


def _game(session: Session, code: str) -> Game:
    game = session.scalar(select(Game).where(Game.code == code))
    if game is None:
        raise HTTPException(404, f"unknown game {code!r}")
    return game


def _ordered_draws(session: Session, game: Game) -> list[Draw]:
    return list(
        session.scalars(
            select(Draw)
            .where(Draw.game_id == game.id)
            .order_by(Draw.draw_date.asc().nulls_first(), Draw.draw_no.asc().nulls_first(), Draw.id.asc())
        )
    )


# ---------------------------------------------------------------- generator


class GenerateRequest(BaseModel):
    method: Literal["hot", "cold", "mixed", "weighted", "random"]
    count: int = Field(default=5, ge=1, le=MAX_COUNT)
    # Same knobs as /stats so the suggestions follow the scoring table on screen.
    w10: float = Field(default=DEFAULT_WEIGHTS[0], ge=0)
    w20: float = Field(default=DEFAULT_WEIGHTS[1], ge=0)
    w50: float = Field(default=DEFAULT_WEIGHTS[2], ge=0)
    w100: float = Field(default=DEFAULT_WEIGHTS[3], ge=0)
    mix: float = Field(default=50.0, ge=0, le=100, description="hot share in percent")


class GenerateResponse(BaseModel):
    game: str
    method: str
    requested: int
    combinations: list[list[int]]
    shortfall: int  # requested minus returned (distinct combinations only, never padded)
    draw_count: int
    note: str


@router.post("/games/{code}/generate", response_model=GenerateResponse)
def generate(code: str, body: GenerateRequest, session: Session = Depends(get_session)):
    game = _game(session, code)
    if body.w10 + body.w20 + body.w50 + body.w100 <= 0:
        raise HTTPException(422, "at least one weight must be greater than zero")
    draws = [list(d.numbers) for d in _ordered_draws(session, game)]
    if body.method != "random" and not draws:
        raise HTTPException(409, "no draws are stored for this game; import or collect results first")

    table = compute_scores(
        draws, game.max_number, (body.w10, body.w20, body.w50, body.w100), body.mix / 100
    )
    result = generate_combinations(
        table, body.method, body.count, game.pick_count, system_rng()  # CSPRNG for users
    )
    return GenerateResponse(
        game=code,
        method=body.method,
        requested=body.count,
        combinations=result.combinations,
        shortfall=result.shortfall,
        draw_count=len(draws),
        note=NOTE + " Random picks are the baseline: no method here changes the odds.",
    )


# ---------------------------------------------------------------- bao


class BaoRequest(BaseModel):
    size: int = Field(ge=1, le=18)
    window: int = Field(default=10, ge=1, le=500)
    end_draw_no: int | None = Field(default=None, ge=1)


class TiedOut(BaseModel):
    number: int
    appearances: int


class LaterDraw(BaseModel):
    draw_no: int | None
    draw_date: dt.date | None
    numbers: list[int]
    hits: list[int]
    jackpot: bool  # a line of the set matches every drawn number (or all S numbers for Bao K-1)


class RuleCheckOut(BaseModel):
    draws_tested: int
    avg_hits: float
    expected_hits: float
    draws_with_3_plus: int
    histogram: dict[str, int]


class BaoResponse(BaseModel):
    game: str
    size: int
    window: int
    end_draw_no: int | None
    end_draw_date: dt.date | None
    special_bao: bool  # size == K-1, e.g. "Bao 5" for a 6-number game
    numbers: list[int]
    counts: dict[str, int]  # appearances for the numbers in the set
    cut_count: int
    sure_in: list[int]
    tied_alternatives: list[TiedOut]
    unseen_filler: bool
    lines: int
    ticket_price: float
    currency: str
    cost: float
    jackpot_one_in: float
    expected_hits: float
    p_at_least_3_hits: float
    later_draws: list[LaterDraw]
    rule_check: RuleCheckOut | None
    rule_note: str | None
    note: str


@router.post("/games/{code}/bao", response_model=BaoResponse)
def bao(code: str, body: BaoRequest, session: Session = Depends(get_session)):
    game = _game(session, code)
    n, k = game.max_number, game.pick_count
    sizes = valid_sizes(n, k)
    if body.size not in sizes:
        raise HTTPException(422, f"size must be one of {sizes} for a {k}/{n} game")

    rows = _ordered_draws(session, game)
    if not rows:
        raise HTTPException(409, "no draws are stored for this game; import or collect results first")
    numbers = [list(d.numbers) for d in rows]

    end_index = len(rows) - 1
    if body.end_draw_no is not None:
        matches = [i for i, d in enumerate(rows) if d.draw_no == body.end_draw_no]
        if not matches:
            raise HTTPException(422, f"draw {body.end_draw_no} is not stored for this game")
        end_index = matches[0]
    if end_index + 1 < body.window:
        raise HTTPException(
            422, f"only {end_index + 1} draw(s) up to the ending draw; shorten the window ({body.window})"
        )

    b = bao_set(numbers, n, body.size, body.window, end_index)
    lines = line_count(n, k, body.size)
    price = float(game.ticket_price)
    special = body.size == k - 1

    later: list[LaterDraw] = []
    for d in rows[end_index + 1 :]:
        h = hits_in(b.numbers, d.numbers)
        later.append(
            LaterDraw(
                draw_no=d.draw_no,
                draw_date=d.draw_date,
                numbers=list(d.numbers),
                hits=sorted(h),
                jackpot=len(h) == (body.size if special else k),
            )
        )

    rc = rule_check(numbers, n, k, body.size, body.window)
    end = rows[end_index]
    return BaoResponse(
        game=code,
        size=body.size,
        window=body.window,
        end_draw_no=end.draw_no,
        end_draw_date=end.draw_date,
        special_bao=special,
        numbers=b.numbers,
        counts={str(x): b.counts[x] for x in b.numbers},
        cut_count=b.cut_count,
        sure_in=b.sure_in,
        tied_alternatives=[TiedOut(number=x, appearances=b.counts[x]) for x in b.tied_alternatives],
        unseen_filler=b.unseen_filler,
        lines=lines,
        ticket_price=price,
        currency=game.currency,
        cost=lines * price,
        jackpot_one_in=jackpot_one_in(n, k, body.size),
        expected_hits=match_mean(n, k, body.size),
        p_at_least_3_hits=prob_at_least(n, k, 3, body.size),
        later_draws=later,
        rule_check=RuleCheckOut(
            draws_tested=rc.draws_tested,
            avg_hits=rc.avg_hits,
            expected_hits=rc.expected_hits,
            draws_with_3_plus=rc.draws_with_3_plus,
            histogram={str(h): c for h, c in rc.histogram.items()},
        )
        if rc.draws_tested
        else None,
        rule_note=(
            f"Bao {body.size} pairs your {body.size} numbers with each of the other {n - body.size} "
            f"numbers, giving {lines} lines. The jackpot is won when all {body.size} of your numbers "
            f"are among the {k} drawn; then exactly one line matches. (Rule checked against secondary "
            "sources; confirm with the operator before relying on it.)"
            if special
            else None
        ),
        note=NOTE
        + " Picking the most frequent numbers of a recent window has no known edge over any other set.",
    )
