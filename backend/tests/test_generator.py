import itertools
import random
import secrets
from collections import Counter

import pytest

from app.analysis import (
    METHODS,
    NumberStat,
    ScoreTable,
    compute_scores,
    generate_combinations,
    make_combination,
    seeded_rng,
    system_rng,
)
from tests.fakesite import load_seed

HISTORY = [d.numbers for d in load_seed()]
REAL = compute_scores(HISTORY, 45)


def crafted(n, hot, cold, combined=None):
    """A ScoreTable with exact, hand-chosen scores."""
    rows = tuple(
        NumberStat(
            number=x, counts={}, total=0, gap=0, rank=x,
            hot=hot(x), cold=cold(x), combined=(combined or (lambda y: 0.5))(x), cls="Neutral",
        )
        for x in range(1, n + 1)
    )
    return ScoreTable(n=n, draw_count=1, weights=(0.25,) * 4, mix=0.5, rows=rows)


# ---------- validity ----------


@pytest.mark.parametrize("method", METHODS)
def test_every_method_gives_k_distinct_sorted_in_range(method):
    rng = seeded_rng(7)
    for _ in range(300):
        c = make_combination(REAL, method, 6, rng)
        assert len(c) == 6 and c == sorted(c) and len(set(c)) == 6 and all(1 <= x <= 45 for x in c)


@pytest.mark.parametrize("method", METHODS)
def test_requested_count_of_distinct_combinations(method):
    res = generate_combinations(REAL, method, 50, 6, seeded_rng(1))
    assert len(res.combinations) == 50 and res.shortfall == 0
    assert len({tuple(c) for c in res.combinations}) == 50


def test_count_bounds_and_unknown_method():
    for bad in (0, 51, -1):
        with pytest.raises(ValueError, match="between 1 and 50"):
            generate_combinations(REAL, "hot", bad, 6, seeded_rng(1))
    with pytest.raises(ValueError, match="method"):
        make_combination(REAL, "lucky", 6, seeded_rng(1))
    with pytest.raises(ValueError):
        make_combination(REAL, "hot", 45, seeded_rng(1))  # K must be < N


def test_shortfall_is_reported_not_padded():
    tiny = compute_scores([[1, 2, 3, 4, 5, 6]], 7)  # 6/7 has only 7 distinct combinations
    res = generate_combinations(tiny, "random", 10, 6, seeded_rng(3))
    assert len(res.combinations) == 7
    assert res.shortfall == 3
    assert len({tuple(c) for c in res.combinations}) == 7


# ---------- RNG ----------


def test_system_rng_is_a_csprng_and_seeded_is_reproducible():
    assert isinstance(system_rng(), secrets.SystemRandom)
    a = generate_combinations(REAL, "weighted", 10, 6, seeded_rng(123)).combinations
    b = generate_combinations(REAL, "weighted", 10, 6, seeded_rng(123)).combinations
    c = generate_combinations(REAL, "weighted", 10, 6, seeded_rng(124)).combinations
    assert a == b
    assert a != c
    assert isinstance(seeded_rng(1), random.Random) and not isinstance(seeded_rng(1), secrets.SystemRandom)


def test_two_system_rng_runs_differ():
    a = generate_combinations(REAL, "random", 20, 6, system_rng()).combinations
    b = generate_combinations(REAL, "random", 20, 6, system_rng()).combinations
    assert a != b  # 20 distinct draws from 8M combinations colliding exactly is impossible in practice


# ---------- the sampling itself ----------


def inclusion_probabilities(weights, k):
    """Exact P(number i is in the sample) for sequential sampling without replacement."""
    n = len(weights)
    probs = [0.0] * n

    def rec(chosen, p):
        if len(chosen) == k:
            for i in chosen:
                probs[i] += p
            return
        rest = [i for i in range(n) if i not in chosen]
        total = sum(weights[i] for i in rest)
        for i in rest:
            rec(chosen + (i,), p * weights[i] / total)

    rec((), 1.0)
    return probs


def test_hot_method_samples_proportionally_to_hot_squared():
    hots = [1.0, 0.8, 0.5, 0.3, 0.1]
    table = crafted(5, hot=lambda x: hots[x - 1], cold=lambda x: 0.5)
    expected = inclusion_probabilities([h * h for h in hots], k=2)
    rng, trials = seeded_rng(2026), 40_000
    seen = Counter()
    for _ in range(trials):
        seen.update(make_combination(table, "hot", 2, rng))
    for i, p in enumerate(expected, start=1):
        assert seen[i] / trials == pytest.approx(p, abs=0.012), f"number {i}"


def test_cold_and_weighted_use_their_own_scores():
    colds = [0.1, 0.1, 0.1, 0.9, 0.9]
    table = crafted(5, hot=lambda x: 0.5, cold=lambda x: colds[x - 1], combined=lambda x: [1, 1, 0.2, 0.2, 0.2][x - 1])
    rng = seeded_rng(5)
    cold_hits = Counter(x for _ in range(5000) for x in make_combination(table, "cold", 1, rng))
    assert cold_hits[4] + cold_hits[5] > 0.9 * 5000  # 0.81 vs 0.01 weights
    weighted = Counter(x for _ in range(5000) for x in make_combination(table, "weighted", 1, rng))
    assert weighted[1] + weighted[2] > 0.9 * 5000


def test_random_is_uniform():
    rng, trials = seeded_rng(99), 20_000
    seen = Counter()
    for _ in range(trials):
        seen.update(make_combination(REAL, "random", 6, rng))
    expected = trials * 6 / 45  # 2666.7
    sd = (trials * (6 / 45) * (1 - 6 / 45)) ** 0.5  # ~48
    assert all(abs(seen[x] - expected) < 5 * sd for x in range(1, 46))


def test_mixed_takes_ceil_half_by_hot_and_the_rest_by_cold_without_overlap():
    # hot concentrates on 1..3, cold on 10..12 (squared weights 1.0 vs 1e-6 floor elsewhere)
    t = crafted(20, hot=lambda x: 1.0 if x <= 3 else 0.0, cold=lambda x: 1.0 if 10 <= x <= 12 else 0.0)
    rng = seeded_rng(11)
    assert make_combination(t, "mixed", 6, rng) == [1, 2, 3, 10, 11, 12]  # 3 hot + 3 cold
    five = make_combination(t, "mixed", 5, rng)  # ceil(5/2) = 3 hot, 2 cold
    assert {1, 2, 3} <= set(five) and len(set(five) & {10, 11, 12}) == 2 and len(set(five)) == 5


def test_mixed_never_overlaps_even_when_hot_and_cold_favour_the_same_numbers():
    t = crafted(12, hot=lambda x: 1.0 if x <= 4 else 0.0, cold=lambda x: 1.0 if x <= 4 else 0.0)
    rng = seeded_rng(21)
    for _ in range(200):
        c = make_combination(t, "mixed", 6, rng)
        assert len(set(c)) == 6
        assert {1, 2, 3, 4} <= set(c)  # 3 by hot, then the cold part takes the remaining favourite


def test_zero_weights_still_complete_the_combination():
    t = crafted(10, hot=lambda x: 0.0, cold=lambda x: 0.0, combined=lambda x: 0.0)
    for m in ("hot", "cold", "weighted", "mixed"):
        assert len(make_combination(t, m, 6, seeded_rng(1))) == 6


def test_exhaustive_small_game_every_combination_reachable():
    t = compute_scores([[1, 2, 3], [2, 3, 4]], 6)
    got = {tuple(make_combination(t, "random", 3, seeded_rng(s))) for s in range(400)}
    assert got == set(itertools.combinations(range(1, 7), 3))
