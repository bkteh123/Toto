"""Combination generator (section 4).

Every method is weighted sampling WITHOUT replacement:

  hot       weight = hot^2
  cold      weight = cold^2
  mixed     ceil(K/2) numbers by hot^2, the rest by cold^2, never overlapping
  weighted  weight = combined^2
  random    uniform (the baseline)

User-facing generation uses a CSPRNG (`secrets.SystemRandom`); backtests use a seeded
PRNG so a run is reproducible. Weights are floored at 1e-6 so a zero weight can still be
drawn when nothing else is left; the generator therefore always completes K numbers.

These suggestions describe past behaviour; none of them changes the odds of winning.
"""

from __future__ import annotations

import math
import random
import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.analysis.scoring import NumberStat, ScoreTable
from app.validation import validate_numbers

METHODS = ("hot", "cold", "mixed", "weighted", "random")
WEIGHT_FLOOR = 1e-6
MAX_COUNT = 50
DEFAULT_MAX_TRIES = 5000


def system_rng() -> random.Random:
    """OS entropy; the only RNG used for combinations shown to a user."""
    return secrets.SystemRandom()


def seeded_rng(seed: int) -> random.Random:
    """Deterministic generator for backtests."""
    return random.Random(seed)


def _sample(
    rows: Sequence[NumberStat],
    weight: Callable[[NumberStat], float],
    k: int,
    rng: random.Random,
    taken: set[int],
) -> list[int]:
    pool = [r for r in rows if r.number not in taken]
    out: list[int] = []
    while len(out) < k and pool:
        ws = [max(WEIGHT_FLOOR, weight(r)) for r in pool]
        x = rng.random() * sum(ws)
        idx = len(pool) - 1
        acc = 0.0
        for i, w in enumerate(ws):
            acc += w
            if x < acc:
                idx = i
                break
        pick = pool.pop(idx).number
        out.append(pick)
        taken.add(pick)
    return out


def make_combination(table: ScoreTable, method: str, k: int, rng: random.Random) -> list[int]:
    """One combination of exactly K distinct numbers, sorted ascending."""
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS} (got {method!r})")
    if not (1 <= k < table.n):
        raise ValueError(f"need 1 <= K < N (got K={k}, N={table.n})")
    rows, taken = table.rows, set()
    if method == "hot":
        nums = _sample(rows, lambda r: r.hot**2, k, rng, taken)
    elif method == "cold":
        nums = _sample(rows, lambda r: r.cold**2, k, rng, taken)
    elif method == "weighted":
        nums = _sample(rows, lambda r: r.combined**2, k, rng, taken)
    elif method == "mixed":
        hot_part = math.ceil(k / 2)
        nums = _sample(rows, lambda r: r.hot**2, hot_part, rng, taken)
        nums += _sample(rows, lambda r: r.cold**2, k - hot_part, rng, taken)
    else:
        nums = _sample(rows, lambda r: 1.0, k, rng, taken)
    return validate_numbers(nums, table.n, k)  # sorted; raises if anything is off


@dataclass(frozen=True)
class GenerationResult:
    combinations: list[list[int]]
    requested: int
    tries: int

    @property
    def shortfall(self) -> int:
        return self.requested - len(self.combinations)


def generate_combinations(
    table: ScoreTable,
    method: str,
    count: int,
    k: int,
    rng: random.Random,
    max_tries: int = DEFAULT_MAX_TRIES,
) -> GenerationResult:
    """`count` DIFFERENT combinations (1..50). Fewer are returned, never padded, when the
    method cannot produce that many distinct ones within `max_tries`."""
    if not (isinstance(count, int) and 1 <= count <= MAX_COUNT):
        raise ValueError(f"count must be an integer between 1 and {MAX_COUNT} (got {count!r})")
    seen: set[tuple[int, ...]] = set()
    combos: list[list[int]] = []
    tries = 0
    while len(combos) < count and tries < max_tries:
        tries += 1
        c = make_combination(table, method, k, rng)
        key = tuple(c)
        if key not in seen:
            seen.add(key)
            combos.append(c)
    return GenerationResult(combos, count, tries)
