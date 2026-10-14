import copy
import json
import math

import pytest

from app.analysis import DEFAULT_WEIGHTS, PERIODS, compute_scores, normalize_weights
from tests.conftest import FIXTURES
from tests.fakesite import load_seed

GOLDEN = json.loads((FIXTURES / "prototype_scores_golden.json").read_text(encoding="utf-8"))
HISTORY = [d.numbers for d in load_seed()]  # 122 real draws, oldest first


# ---------- hand-computed example ----------
#
# N=10, K=3, five draws. Every window (10/20/50/100) covers all five, so with weights
# summing to 1:  hot = appearances / 4 (the maximum is 4, for number 1).
SMALL = [[1, 2, 3], [1, 4, 5], [1, 2, 6], [7, 8, 9], [1, 2, 10]]


@pytest.fixture(scope="module")
def small():
    return compute_scores(SMALL, 10)


def test_counts_and_totals(small):
    totals = {r.number: r.total for r in small.rows}
    assert totals == {1: 4, 2: 3, 3: 1, 4: 1, 5: 1, 6: 1, 7: 1, 8: 1, 9: 1, 10: 1}
    for r in small.rows:
        assert all(r.counts[p] == r.total for p in PERIODS)  # fewer than 10 draws: every window = all


def test_gap_is_draws_since_last_seen(small):
    gaps = {r.number: r.gap for r in small.rows}
    # 0 when in the latest draw; 1 if in the one before; ...
    assert gaps == {1: 0, 2: 0, 3: 4, 4: 3, 5: 3, 6: 2, 7: 1, 8: 1, 9: 1, 10: 0}


def test_gap_of_a_never_seen_number_is_the_draw_count():
    t = compute_scores([[1, 2], [1, 3]], 5)
    assert {r.number: r.gap for r in t.rows}[4] == 2
    assert {r.number: r.gap for r in t.rows}[5] == 2


def test_hot_cold_combined_by_hand(small):
    r = {x.number: x for x in small.rows}
    assert r[1].hot == pytest.approx(1.0)
    assert r[2].hot == pytest.approx(0.75)
    assert r[3].hot == pytest.approx(0.25)
    # cold = 0.5*(1-hot) + 0.5*gap/maxgap, maxgap = 4
    assert r[1].cold == pytest.approx(0.0)
    assert r[2].cold == pytest.approx(0.125)
    assert r[3].cold == pytest.approx(0.875)
    assert r[4].cold == pytest.approx(0.75)
    assert r[6].cold == pytest.approx(0.625)
    assert r[10].cold == pytest.approx(0.375)
    # combined = 0.5*hot + 0.5*cold (default mix 50%)
    assert r[1].combined == pytest.approx(0.5)
    assert r[3].combined == pytest.approx(0.5625)


def test_rank_and_class(small):
    assert [r.rank for r in small.rows] == list(range(1, 11))  # ties go to the lower number
    classes = {r.number: r.cls for r in small.rows}
    # ceil(10/3) = 4 Hot (highest hot, ties lower number), 4 Cold, 2 Neutral
    assert [n for n, c in classes.items() if c == "Hot"] == [1, 2, 3, 4]
    assert [n for n, c in classes.items() if c == "Neutral"] == [5, 6]
    assert [n for n, c in classes.items() if c == "Cold"] == [7, 8, 9, 10]


def test_windows_are_the_last_p_draws():
    # draws: number 1 only in the two OLDEST of 12 draws -> outside the last 10
    draws = [[1, 2], [1, 3]] + [[2, 3]] * 10
    t = compute_scores(draws, 5)
    r1, r2 = t.rows[0], t.rows[1]
    assert r1.counts[10] == 0 and r1.counts[20] == 2 and r1.total == 2
    assert r2.counts[10] == 10 and r2.total == 11
    assert r1.gap == 12 - 1 - 1  # last seen in draw index 1
    assert t.span(10) == 10 and t.span(100) == 12 and t.span("all") == 12
    assert t.frequency(2, 10) == pytest.approx(1.0)
    assert t.frequency(2, "all") == pytest.approx(11 / 12)


def test_window_boundary_exact():
    # 100 draws then one more: the oldest falls out of the 100-window but stays in "all"
    draws = [[1, 2]] + [[3, 4]] * 100
    t = compute_scores(draws, 6)
    assert t.rows[0].counts[100] == 0 and t.rows[0].total == 1
    assert t.rows[2].counts[100] == 100


def test_mix_extremes_and_weight_normalisation(small):
    only_hot = compute_scores(SMALL, 10, mix=1.0)
    only_cold = compute_scores(SMALL, 10, mix=0.0)
    for a, h, c in zip(small.rows, only_hot.rows, only_cold.rows):
        assert h.combined == pytest.approx(a.hot)
        assert c.combined == pytest.approx(a.cold)
    assert normalize_weights((40, 25, 20, 15)) == pytest.approx((0.4, 0.25, 0.2, 0.15))
    assert normalize_weights((1, 1, 1, 1)) == pytest.approx((0.25,) * 4)
    assert sum(normalize_weights((3, 0, 0, 9))) == pytest.approx(1.0)
    # weights are scale-free
    a = compute_scores(HISTORY, 45, (40, 25, 20, 15))
    b = compute_scores(HISTORY, 45, (4, 2.5, 2, 1.5))
    assert [r.hot for r in a.rows] == pytest.approx([r.hot for r in b.rows])


def test_hot_uses_each_windows_own_maximum():
    # window 10: number 2 appears 10 times (max=10); window 100: number 1 appears 90 (max=90)
    draws = [[1, 9]] * 90 + [[2, 9]] * 10  # N=9... number 9 is in every draw
    t = compute_scores(draws, 9, (1, 0, 0, 1))
    r = {x.number: x for x in t.rows}
    # n=2: w10 -> 10/10 = 1 ; w100 -> 10/100 = 0.1  => 0.5*1 + 0.5*0.1
    assert r[2].hot == pytest.approx(0.55)
    # n=1: w10 -> 0 ; w100 -> 90/100 = 0.9 => 0.45
    assert r[1].hot == pytest.approx(0.45)
    assert r[9].hot == pytest.approx(1.0)


def test_empty_history_is_all_zero_not_an_error():
    t = compute_scores([], 45)
    assert t.draw_count == 0
    assert all(r.total == 0 and r.gap == 0 and r.hot == 0.0 for r in t.rows)
    assert t.frequency(1, 10) == 0.0


def test_inputs_are_validated_and_not_mutated():
    draws = [[3, 1, 2], [5, 4, 3]]
    snapshot = copy.deepcopy(draws)
    compute_scores(draws, 6)
    assert draws == snapshot
    with pytest.raises(ValueError, match="not an integer in 1..6"):
        compute_scores([[1, 2, 7]], 6)
    with pytest.raises(ValueError):
        compute_scores([[1, 2, 0]], 6)
    with pytest.raises(ValueError):
        compute_scores([[1, 2, True]], 6)
    for bad in [(0, 0, 0, 0), (-1, 1, 1, 1), (1, 1, 1), (float("nan"), 1, 1, 1), (1, 1, 1, "x")]:
        with pytest.raises(ValueError):
            normalize_weights(bad)  # type: ignore[arg-type]
    for bad_mix in (-0.1, 1.1, float("nan")):
        with pytest.raises(ValueError, match="mix"):
            compute_scores(draws, 6, mix=bad_mix)


def test_hottest_and_coldest_chips():
    t = compute_scores(SMALL, 10)
    assert [r.number for r in t.hottest(10, 3)] == [1, 2, 3]  # 4,1,1 -> ties to the lower number
    assert [r.number for r in t.coldest(3)] == [3, 4, 5]  # gaps 4,3,3


# ---------- real data: invariants ----------


def test_real_history_invariants():
    t = compute_scores(HISTORY, 45)
    assert t.draw_count == 122
    assert sum(r.total for r in t.rows) == 6 * 122
    for p in PERIODS:
        assert sum(r.counts[p] for r in t.rows) == 6 * min(p, 122)
    assert {r.rank for r in t.rows} == set(range(1, 46))
    assert all(0.0 <= r.hot <= 1.0 + 1e-12 for r in t.rows)
    assert all(0.0 <= r.cold <= 1.0 + 1e-12 for r in t.rows)
    counts = {c: sum(1 for r in t.rows if r.cls == c) for c in ("Hot", "Neutral", "Cold")}
    assert counts == {"Hot": 15, "Neutral": 15, "Cold": 15}
    assert sum(t.weights) == pytest.approx(1.0)
    assert t.weights == pytest.approx([w / 100 for w in DEFAULT_WEIGHTS])
    assert max(r.gap for r in t.rows) < 122  # every number was seen at least once


# ---------- golden values from the ORIGINAL prototype's own code ----------


def _assert_matches(rows, golden):
    assert len(rows) == len(golden) == 45
    for r, g in zip(rows, golden):
        ctx = f"number {g['n']}"
        assert r.number == g["n"], ctx
        assert {str(p): r.counts[p] for p in PERIODS} | {"all": r.total} == g["cnt"], ctx
        assert r.gap == g["gap"], ctx
        assert r.rank == g["rank"], ctx
        assert r.cls == g["cls"], ctx
        for ours, theirs in ((r.hot, g["hot"]), (r.cold, g["cold"]), (r.combined, g["comb"])):
            assert math.isclose(ours, theirs, rel_tol=0, abs_tol=1e-12), ctx


def test_golden_prototype_at_latest_draw():
    assert GOLDEN["draws"] == len(HISTORY) == 122
    _assert_matches(compute_scores(HISTORY, 45).rows, GOLDEN["ending"])


@pytest.mark.parametrize("t", [100, 60, 40, 12])
def test_golden_prototype_at_earlier_prefixes(t):
    _assert_matches(compute_scores(HISTORY[:t], 45).rows, GOLDEN["prefix"][str(t)])


def test_golden_prototype_with_equal_weights_and_30pct_hot_share():
    alt = GOLDEN["alt"]
    t = compute_scores(HISTORY, 45, alt["weights"], alt["mix"])
    _assert_matches(t.rows, alt["rows"])


def test_golden_hypergeometric_agrees_with_prototype():
    from app.analysis import match_mean, match_variance, prob_at_least

    h = GOLDEN["hyper"]
    assert match_mean(45, 6) == pytest.approx(h["mean"])
    assert match_variance(45, 6) == pytest.approx(h["variance"])
    assert prob_at_least(45, 6, 3) == pytest.approx(h["p3"], abs=1e-12)
