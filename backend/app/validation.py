"""Strict draw/combination validation. Nothing here guesses, pads or auto-fills."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from app.models import Game


class DrawValidationError(ValueError):
    """Raised when a set of numbers is not a legal draw/combination for the game."""


@dataclass(frozen=True)
class GameSpec:
    """The rules of a game, decoupled from the database so pure code can use them."""

    code: str
    n: int  # highest number
    k: int  # numbers drawn
    has_bonus: bool = False
    bonus_max: int | None = None
    ticket_price: float = 0.0
    currency: str = ""
    name: str = ""

    @classmethod
    def from_model(cls, g: Game) -> GameSpec:
        return cls(
            code=g.code,
            n=g.max_number,
            k=g.pick_count,
            has_bonus=g.has_bonus,
            bonus_max=g.bonus_max,
            ticket_price=float(g.ticket_price),
            currency=g.currency,
            name=g.name,
        )


def validate_game_rules(n: int, k: int) -> None:
    if not (2 <= n <= 500):
        raise DrawValidationError(f"highest number N must be between 2 and 500 (got {n})")
    if not (1 <= k <= 20):
        raise DrawValidationError(f"numbers drawn K must be between 1 and 20 (got {k})")
    if k >= n:
        raise DrawValidationError(f"K must be smaller than N (got K={k}, N={n})")


def validate_numbers(numbers: Iterable[object], n: int, k: int) -> list[int]:
    """Return the numbers sorted ascending, or raise.

    Exactly K distinct integers in 1..N. Floats, bools and strings are rejected: a parser
    that wants to accept "07" must convert it explicitly before calling this.
    """
    values = list(numbers)
    if len(values) != k:
        raise DrawValidationError(f"expected exactly {k} numbers, got {len(values)}")
    ints: list[int] = []
    for v in values:
        if isinstance(v, bool) or not isinstance(v, int):
            raise DrawValidationError(f"{v!r} is not an integer")
        ints.append(v)
    for v in ints:
        if not (1 <= v <= n):
            raise DrawValidationError(f"{v} is outside 1..{n}")
    if len(set(ints)) != len(ints):
        dupes = sorted({v for v in ints if ints.count(v) > 1})
        raise DrawValidationError(f"numbers must be distinct (repeated: {dupes})")
    return sorted(ints)


def validate_bonus(bonus: object, spec: GameSpec, numbers: Sequence[int]) -> int | None:
    if bonus is None:
        return None
    if not spec.has_bonus or spec.bonus_max is None:
        raise DrawValidationError(f"game {spec.code} has no bonus ball")
    if isinstance(bonus, bool) or not isinstance(bonus, int):
        raise DrawValidationError(f"bonus {bonus!r} is not an integer")
    if not (1 <= bonus <= spec.bonus_max):
        raise DrawValidationError(f"bonus {bonus} is outside 1..{spec.bonus_max}")
    # Same pool as the main numbers (e.g. Power 6/55): the bonus is drawn without replacement.
    if spec.bonus_max == spec.n and bonus in numbers:
        raise DrawValidationError(f"bonus {bonus} repeats a main number")
    return bonus


def validate_draw(
    numbers: Iterable[object], spec: GameSpec, bonus: object = None
) -> tuple[list[int], int | None]:
    nums = validate_numbers(numbers, spec.n, spec.k)
    return nums, validate_bonus(bonus, spec, nums)
