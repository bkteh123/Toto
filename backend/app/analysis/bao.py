"""Bao (system) pick (section 5).

Take the S numbers that appeared most in the last W draws up to and including an ending
draw. Ties are broken by most recent appearance first, then lowest number. Numbers tied
with the last one in the set, but left out, are reported as equal alternatives.

Lines and odds
  S >= K     lines = C(S, K): every K-number combination of the set.
  S == K-1   "Bao 5" for a 6-number game. Vietlott pairs the 5 numbers with each of the
             other N-S numbers, so lines = N - S (40 for 6/45, 50 for 6/55). The jackpot is
             won when all S numbers are among the K drawn; exactly one line then matches.
  odds       the chance that one of the lines is the jackpot is lines / C(N, K), so the
             jackpot is "1 in C(N, K) / lines" for both cases.

A rule check replays "top S of the last W" on every draw that has W earlier draws and
compares the average hits with the random expectation S*K/N.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from math import comb

MAX_SIZE = 18


def valid_sizes(n: int, k: int) -> list[int]:
    """K-1 (the special "Bao K-1") and K+1..18, never more than N."""
    sizes = [k - 1] if k - 1 >= 1 else []
    sizes += list(range(k + 1, min(MAX_SIZE, n) + 1))
    return sizes


def line_count(n: int, k: int, size: int) -> int:
    if size == k - 1:
        return n - size
    if size >= k:
        return comb(size, k)
    raise ValueError(f"size {size} is not a valid bao size for K={k}")


def jackpot_one_in(n: int, k: int, size: int) -> float:
    """The jackpot is '1 in x' with x = C(N, K) / lines."""
    return comb(n, k) / line_count(n, k, size)


@dataclass(frozen=True)
class RuleCheck:
    window: int
    size: int
    draws_tested: int
    avg_hits: float
    expected_hits: float  # S * K / N
    draws_with_3_plus: int
    histogram: dict[int, int]  # hits -> number of draws


@dataclass(frozen=True)
class BaoSet:
    numbers: list[int]  # sorted
    counts: dict[int, int]  # appearances in the window, for every number 1..N
    window: int
    end_index: int  # index in `draws` of the ending draw (inclusive)
    cut_count: int  # appearances of the weakest number in the set
    sure_in: list[int]  # numbers with strictly more than cut_count appearances
    tied_alternatives: list[int]  # left-out numbers tied at cut_count, best-ranked first
    unseen_filler: bool  # True when the set had to include numbers never seen in the window


def rank_numbers(draws: Sequence[Sequence[int]], n: int, window: int) -> tuple[list[int], list[int], list[int]]:
    """All numbers ranked best-first for the last `window` draws of `draws`.

    Returns (ranked, counts, last_seen) with counts/last_seen indexed by number (index 0
    unused); last_seen is the index within the window, -1 if absent.
    """
    w = draws[-window:]
    counts = [0] * (n + 1)
    last = [-1] * (n + 1)
    for i, d in enumerate(w):
        for x in d:
            counts[x] += 1
            last[x] = i
    ranked = sorted(range(1, n + 1), key=lambda x: (-counts[x], -last[x], x))
    return ranked, counts, last


def bao_set(
    draws: Sequence[Sequence[int]],
    n: int,
    size: int,
    window: int,
    end_index: int | None = None,
) -> BaoSet:
    """Top `size` numbers of the last `window` draws ending at draws[end_index] (inclusive;
    default the latest). Needs at least `window` draws up to that point."""
    if not draws:
        raise ValueError("no draws")
    end = len(draws) - 1 if end_index is None else end_index
    if not (0 <= end < len(draws)):
        raise ValueError(f"end_index {end_index} is outside 0..{len(draws) - 1}")
    if window < 1:
        raise ValueError("window must be >= 1")
    if end + 1 < window:
        raise ValueError(f"only {end + 1} draw(s) up to the ending draw; window is {window}")
    if not (1 <= size <= n):
        raise ValueError(f"size must be between 1 and N={n}")

    ranked, counts, _ = rank_numbers(draws[: end + 1], n, window)
    chosen = ranked[:size]
    cut = counts[chosen[-1]]
    tied = [x for x in ranked[size:] if counts[x] == cut and cut > 0]
    return BaoSet(
        numbers=sorted(chosen),
        counts={x: counts[x] for x in range(1, n + 1)},
        window=window,
        end_index=end,
        cut_count=cut,
        sure_in=[x for x in sorted(chosen) if counts[x] > cut],
        tied_alternatives=tied,
        unseen_filler=cut == 0,
    )


def hits_in(numbers: Sequence[int], draw: Sequence[int]) -> list[int]:
    s = set(numbers)
    return [x for x in draw if x in s]


def rule_check(draws: Sequence[Sequence[int]], n: int, k: int, size: int, window: int) -> RuleCheck:
    """Replay the rule on every draw t (t >= window) using only draws[:t]."""
    hist: Counter[int] = Counter()
    total = 0
    tested = 0
    for t in range(window, len(draws)):
        picked = bao_set(draws[:t], n, size, window).numbers
        h = len(hits_in(picked, draws[t]))
        hist[h] += 1
        total += h
        tested += 1
    return RuleCheck(
        window=window,
        size=size,
        draws_tested=tested,
        avg_hits=total / tested if tested else 0.0,
        expected_hits=size * k / n,
        draws_with_3_plus=sum(c for h, c in hist.items() if h >= 3),
        histogram=dict(sorted(hist.items())),
    )
