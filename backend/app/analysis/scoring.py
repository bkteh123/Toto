"""Per-number statistics and scores (section 3.1).

Definitions, for N numbers and T draws (oldest -> newest):

  appearances(p)  times n appears in the last p draws (all draws if T < p), and in all draws
  frequency(p)    appearances(p) / min(p, T)
  gap             draws since last seen: 0 if n is in the latest draw; T if never seen
  all-time rank   1 = most appearances overall; ties go to the lower number
  hot             sum over p in {10,20,50,100} of w_p * appearances_p(n) / max_k appearances_p(k)
  cold            0.5 * (1 - hot) + 0.5 * gap / max gap
  combined        mix * hot + (1 - mix) * cold
  class           by hot score, ties to the lower number: top third Hot, bottom third Cold

`max` terms are floored at 1 so an empty or all-zero window gives 0 rather than dividing
by zero. These scores rank past behaviour only.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

PERIODS: tuple[int, ...] = (10, 20, 50, 100)
DEFAULT_WEIGHTS: tuple[float, ...] = (40.0, 25.0, 20.0, 15.0)
DEFAULT_MIX = 0.5

Period = int | str  # one of PERIODS, or "all"


def normalize_weights(weights: Sequence[float]) -> tuple[float, ...]:
    """Scale the four period weights to sum to 1. Rejects negatives, NaN and all-zero."""
    if len(weights) != len(PERIODS):
        raise ValueError(f"need {len(PERIODS)} weights (for the last {PERIODS} draws)")
    for w in weights:
        if isinstance(w, bool) or not isinstance(w, (int, float)) or not math.isfinite(w):
            raise ValueError(f"weight {w!r} is not a finite number")
        if w < 0:
            raise ValueError("weights must not be negative")
    total = float(sum(weights))
    if total <= 0:
        raise ValueError("at least one weight must be greater than zero")
    return tuple(w / total for w in weights)


@dataclass(frozen=True)
class NumberStat:
    number: int
    counts: Mapping[int, int]  # period -> appearances in the last `period` draws
    total: int  # appearances in all draws
    gap: int
    rank: int
    hot: float
    cold: float
    combined: float
    cls: str  # 'Hot' | 'Cold' | 'Neutral'

    def appearances(self, period: Period) -> int:
        return self.total if period == "all" else self.counts[int(period)]


@dataclass(frozen=True)
class ScoreTable:
    n: int  # highest number
    draw_count: int
    weights: tuple[float, ...]  # normalised, aligned with PERIODS
    mix: float  # hot share, 0..1
    rows: tuple[NumberStat, ...]  # ordered by number 1..N

    def span(self, period: Period) -> int:
        """Number of draws a period actually covers (min(p, T))."""
        return self.draw_count if period == "all" else min(int(period), self.draw_count)

    def frequency(self, number: int, period: Period) -> float:
        span = self.span(period)
        return self.rows[number - 1].appearances(period) / span if span else 0.0

    def hottest(self, period: Period = 10, top: int = 8) -> list[NumberStat]:
        """Most appearances in the period; ties to the lower number."""
        return sorted(self.rows, key=lambda r: (-r.appearances(period), r.number))[:top]

    def coldest(self, top: int = 8) -> list[NumberStat]:
        """Longest unseen first; ties to the lower number."""
        return sorted(self.rows, key=lambda r: (-r.gap, r.number))[:top]


def _validate(draws: Sequence[Sequence[int]], n: int) -> None:
    if not isinstance(n, int) or n < 2:
        raise ValueError(f"N must be an integer >= 2 (got {n!r})")
    for i, d in enumerate(draws):
        for v in d:
            if isinstance(v, bool) or not isinstance(v, int) or not (1 <= v <= n):
                raise ValueError(f"draw {i}: {v!r} is not an integer in 1..{n}")


def compute_scores(
    draws: Sequence[Sequence[int]],
    n: int,
    weights: Sequence[float] = DEFAULT_WEIGHTS,
    mix: float = DEFAULT_MIX,
) -> ScoreTable:
    """Statistics for every number 1..n from `draws` (oldest first). Never mutates input."""
    if not (isinstance(mix, (int, float)) and math.isfinite(mix) and 0 <= mix <= 1):
        raise ValueError(f"mix must be between 0 and 1 (got {mix!r})")
    w = normalize_weights(weights)
    _validate(draws, n)
    t = len(draws)

    window_counts = {p: [0] * (n + 1) for p in PERIODS}
    total = [0] * (n + 1)
    last = [-1] * (n + 1)  # index of the most recent draw containing the number
    for i, d in enumerate(draws):
        age = t - i  # 1 for the newest draw
        for num in d:
            total[num] += 1
            last[num] = i
            for p in PERIODS:
                if age <= p:
                    window_counts[p][num] += 1

    max_count = {p: max(1, max(window_counts[p][1:])) for p in PERIODS}
    gaps = [0] + [t if last[x] < 0 else t - 1 - last[x] for x in range(1, n + 1)]
    max_gap = max(1, max(gaps[1:]))

    hot = [0.0] * (n + 1)
    for x in range(1, n + 1):
        hot[x] = sum(w[i] * window_counts[p][x] / max_count[p] for i, p in enumerate(PERIODS))
    cold = [0.0] + [0.5 * (1 - hot[x]) + 0.5 * gaps[x] / max_gap for x in range(1, n + 1)]
    combined = [0.0] + [mix * hot[x] + (1 - mix) * cold[x] for x in range(1, n + 1)]

    by_total = sorted(range(1, n + 1), key=lambda x: (-total[x], x))
    rank = {x: i + 1 for i, x in enumerate(by_total)}

    third = math.ceil(n / 3)
    by_hot = sorted(range(1, n + 1), key=lambda x: (-hot[x], x))
    cls: dict[int, str] = {}
    for i, x in enumerate(by_hot):
        cls[x] = "Hot" if i < third else "Cold" if i >= n - third else "Neutral"

    rows = tuple(
        NumberStat(
            number=x,
            counts={p: window_counts[p][x] for p in PERIODS},
            total=total[x],
            gap=gaps[x],
            rank=rank[x],
            hot=hot[x],
            cold=cold[x],
            combined=combined[x],
            cls=cls[x],
        )
        for x in range(1, n + 1)
    )
    return ScoreTable(n=n, draw_count=t, weights=w, mix=float(mix), rows=rows)

