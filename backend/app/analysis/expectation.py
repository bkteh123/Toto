"""What a random selection is expected to do (section 3.2).

A ticket of S numbers against a draw of K numbers out of N: the number of matches is
hypergeometric. For a normal ticket S == K, giving mean K^2/N.
"""

from __future__ import annotations

from math import comb


def expected_appearances(window: int, n: int, k: int) -> float:
    """Expected appearances of any one number in `window` draws: window * K / N."""
    if window < 0:
        raise ValueError("window must be >= 0")
    _check(n, k)
    return window * k / n


def _check(n: int, k: int, s: int | None = None) -> int:
    if not (isinstance(n, int) and isinstance(k, int)) or not (1 <= k < n):
        raise ValueError(f"need integers 1 <= K < N (got K={k}, N={n})")
    s = k if s is None else s
    if not (isinstance(s, int) and 1 <= s <= n):
        raise ValueError(f"ticket size S must be an integer in 1..N (got S={s}, N={n})")
    return s


def hypergeom_pmf(n: int, k: int, s: int, m: int) -> float:
    """P(exactly m of the K drawn numbers are among a ticket of S numbers), exact."""
    s = _check(n, k, s)
    if m < max(0, s + k - n) or m > min(s, k):
        return 0.0
    return comb(k, m) * comb(n - k, s - m) / comb(n, s)


def match_distribution(n: int, k: int, s: int | None = None) -> list[float]:
    """[P(0 matches), P(1), ..., P(min(S, K))]. Sums to 1."""
    s = _check(n, k, s)
    return [hypergeom_pmf(n, k, s, m) for m in range(min(s, k) + 1)]


def match_mean(n: int, k: int, s: int | None = None) -> float:
    """Expected matches: S*K/N (K^2/N for a normal ticket)."""
    s = _check(n, k, s)
    return s * k / n


def match_variance(n: int, k: int, s: int | None = None) -> float:
    """S * (K/N) * ((N-K)/N) * ((N-S)/(N-1)); for S == K this is the spec's formula
    K * (K/N) * ((N-K)/N) * ((N-K)/(N-1))."""
    s = _check(n, k, s)
    return s * (k / n) * ((n - k) / n) * ((n - s) / (n - 1))


def prob_at_least(n: int, k: int, min_matches: int, s: int | None = None) -> float:
    """P(matches >= min_matches), summed exactly from hypergeometric terms.

    Integer arithmetic until the final division, so there is no accumulated float error.
    """
    s = _check(n, k, s)
    if min_matches <= 0:
        return 1.0
    top = min(s, k)
    if min_matches > top:
        return 0.0
    lo = max(min_matches, s + k - n, 0)
    numerator = sum(comb(k, m) * comb(n - k, s - m) for m in range(lo, top + 1))
    return numerator / comb(n, s)
