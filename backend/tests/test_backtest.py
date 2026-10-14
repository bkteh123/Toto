import math
import random

import pytest

import app.analysis.backtest as bt
from app.analysis import compute_scores, make_combination, match_mean, match_variance, prob_at_least
from app.analysis.backtest import METHOD_NAMES_EN, MethodResult, _verdict, method_rng, run_backtest
from app.analysis.stattests import normal_two_sided_p
from tests.fakesite import load_seed

HISTORY = [d.numbers for d in load_seed()]  # 122 real draws
N, K = 45, 6
ALL = ["hot", "cold", "mixed", "weighted", "random"]


def junk_draws(count, seed):
    rng = random.Random(seed)
    return [sorted(rng.sample(range(1, N + 1), K)) for _ in range(count)]


# ---------- no look-ahead ----------


def test_scores_for_draw_t_are_computed_from_exactly_the_earlier_draws(monkeypatch):
    seen = []
    real = bt.compute_scores

    def spy(draws, n, weights, mix):
        seen.append([list(d) for d in draws])
        return real(draws, n, weights, mix)

    monkeypatch.setattr(bt, "compute_scores", spy)
    run_backtest(HISTORY, N, K, warmup=30, tickets=1, methods=["hot"])
    assert len(seen) == 122 - 30
    for i, got in enumerate(seen):
        t = 30 + i
        assert got == HISTORY[:t]  # draws 0..t-1: draw t (and everything after it) is invisible


def test_changing_draw_t_cannot_change_the_tickets_bought_for_draw_t():
    t = 70
    altered = [list(d) for d in HISTORY]
    altered[t] = [40, 41, 42, 43, 44, 45]
    a = run_backtest(HISTORY, N, K, warmup=30, tickets=3, methods=ALL, seed=9, record_tickets=True)
    b = run_backtest(altered, N, K, warmup=30, tickets=3, methods=ALL, seed=9, record_tickets=True)
    step = t - 30
    for m in ALL:
        assert a.tickets_log[m][: step + 1] == b.tickets_log[m][: step + 1]  # up to and including draw t
    # ... while the draws AFTER t are allowed to differ, i.e. the log is sensitive to history
    assert any(a.tickets_log[m][step + 1 :] != b.tickets_log[m][step + 1 :] for m in ALL)


def test_changing_every_draw_from_t0_onward_leaves_all_earlier_tickets_alone():
    t0 = 80
    altered = [list(d) for d in HISTORY[:t0]] + junk_draws(122 - t0, seed=5)
    a = run_backtest(HISTORY, N, K, warmup=30, tickets=4, methods=ALL, seed=3, record_tickets=True)
    b = run_backtest(altered, N, K, warmup=30, tickets=4, methods=ALL, seed=3, record_tickets=True)
    for m in ALL:
        assert a.tickets_log[m][: t0 - 30 + 1] == b.tickets_log[m][: t0 - 30 + 1]
        assert len(a.tickets_log[m]) == len(b.tickets_log[m]) == 92


def test_matches_are_counted_against_the_draw_being_predicted():
    """Independent re-derivation of the loop, using only the public helpers."""
    seed, tickets, warmup = 2026, 3, 30
    res = run_backtest(HISTORY, N, K, warmup=warmup, tickets=tickets, methods=["hot", "random"], seed=seed)
    for mr in res.methods:
        rng = method_rng(seed, mr.method)
        total = 0
        for t in range(warmup, len(HISTORY)):
            table = compute_scores(HISTORY[:t], N)
            for _ in range(tickets):
                c = make_combination(table, mr.method, K, rng)
                total += len(set(c) & set(HISTORY[t]))
        assert mr.avg_matches * mr.tickets == pytest.approx(total)


# ---------- structure and statistics ----------


@pytest.fixture(scope="module")
def real_run():
    return run_backtest(HISTORY, N, K, warmup=30, tickets=5, methods=ALL, seed=20261013)


def test_counts_and_expectation(real_run):
    r = real_run
    assert (r.tested_draws, r.tickets_per_draw, r.warmup) == (92, 5, 30)
    assert r.expected_mean == pytest.approx(0.8)
    assert r.expected_variance == pytest.approx(match_variance(N, K))
    assert r.expected_ge3 == pytest.approx(prob_at_least(N, K, 3))
    assert [m.method for m in r.methods] == ALL
    for m in r.methods:
        assert m.tickets == 92 * 5 == 460
        assert sum(m.histogram.values()) == 460
        assert set(m.histogram) == set(range(K + 1))
        assert sum(h * c for h, c in m.histogram.items()) == pytest.approx(m.avg_matches * m.tickets)
        assert m.rate_ge3 == pytest.approx(sum(c for h, c in m.histogram.items() if h >= 3) / 460)
        assert len(m.curve) == 92 and m.curve[-1] == pytest.approx(m.avg_matches)


def test_statistics_follow_the_spec_formulas(real_run):
    mu, var = real_run.expected_mean, real_run.expected_variance
    for m in real_run.methods:
        z = (m.avg_matches - mu) / math.sqrt(var / m.tickets)
        assert m.z == pytest.approx(z)
        assert m.p_value == pytest.approx(normal_two_sided_p(z))
        assert m.pct_vs_expected == pytest.approx((m.avg_matches / mu - 1) * 100)
        assert m.expected_ge3 == pytest.approx(0.023834078570323606)
        assert m.p_by_draw is not None and 0 < m.p_by_draw <= 1


def test_reproducible_by_seed_and_methods_do_not_affect_each_other():
    a = run_backtest(HISTORY, N, K, methods=ALL, seed=77)
    b = run_backtest(HISTORY, N, K, methods=ALL, seed=77)
    c = run_backtest(HISTORY, N, K, methods=ALL, seed=78)
    assert [m.histogram for m in a.methods] == [m.histogram for m in b.methods]
    assert [m.histogram for m in a.methods] != [m.histogram for m in c.methods]
    solo = run_backtest(HISTORY, N, K, methods=["hot"], seed=77)
    assert solo.methods[0].histogram == a.methods[0].histogram  # same tickets whatever else is run
    assert solo.methods[0].curve == a.methods[0].curve


def test_snapshot_for_the_documented_seed(real_run):
    """Determinism guard: the exact tickets for seed 20261013 must not drift silently."""
    got = {m.method: sum(h * c for h, c in m.histogram.items()) for m in real_run.methods}
    assert got == SNAPSHOT_HITS


# Total matches over 460 tickets per method (seed 20261013, 122 real draws, warm-up 30, 5 tickets).
# Recorded from the implementation, so this guards determinism, not correctness (the
# independent re-count above covers that). Expected under pure luck: 0.8 * 460 = 368.
SNAPSHOT_HITS: dict[str, int] = {"hot": 356, "cold": 381, "mixed": 366, "weighted": 354, "random": 350}


def test_random_method_is_calibrated_under_the_null():
    """On draws that really are random, ~1% of 'random' backtests should show p < 0.01."""
    flagged = 0
    runs = 200
    for s in range(runs):
        h = junk_draws(60, seed=1000 + s)
        r = run_backtest(h, N, K, warmup=30, tickets=5, methods=["random"], seed=s)
        flagged += r.methods[0].p_value < 0.01
    assert flagged <= 6  # expected 2; P(>6 | Binomial(200, .01)) ~ 0.5%


# ---------- power: the machinery can see a real effect ----------


def planted_history(draws, lucky=9, from_lucky=4, seed=1):
    """Every draw takes `from_lucky` numbers from a fixed lucky set: a real, persistent bias."""
    rng = random.Random(seed)
    out = []
    for _ in range(draws):
        pick = set(rng.sample(range(1, lucky + 1), from_lucky))
        rest = [x for x in range(lucky + 1, N + 1)]
        pick |= set(rng.sample(rest, K - from_lucky))
        out.append(sorted(pick))
    return out


def test_a_planted_bias_is_detected_and_reported_with_the_warnings():
    r = run_backtest(planted_history(250), N, K, warmup=30, tickets=5, methods=ALL, seed=4)
    by = {m.method: m for m in r.methods}
    for name in ("hot", "weighted"):
        assert by[name].beats_random and by[name].p_value < 0.01
        assert by[name].p_by_draw < 0.01  # the per-draw check agrees on a real effect
        assert by[name].avg_matches > r.expected_mean * 1.2  # clearly above the 0.8 expectation
    assert not by["random"].beats_random  # the control never "wins"
    v = r.verdict
    assert v.kind == "some_significant" and "hot" in v.significant
    assert "multiple comparisons" in v.text_en and "correlated" in v.text_en
    assert "repeats on new" in v.text_en
    assert "多重比较" in v.text_zh and "相关" in v.text_zh


def test_no_effect_gives_the_plain_null_verdict():
    r = run_backtest(junk_draws(150, seed=31), N, K, warmup=30, tickets=5, methods=ALL, seed=12)
    assert r.verdict.kind == "none_significant"
    assert r.verdict.significant == []
    assert r.verdict.text_en.startswith("No method beats random with p < 0.01")
    assert "fair draw" in r.verdict.text_en
    assert "公平开奖" in r.verdict.text_zh


# ---------- verdict wording, by construction ----------


def mr(method, *, ticket=False, beats=False, below=False):
    return MethodResult(
        method=method, tickets=100, avg_matches=0.8, pct_vs_expected=0.0, rate_ge3=0.02, expected_ge3=0.0238,
        z=0.0, p_value=0.5, p_by_draw=0.5, histogram={}, curve=[],
        ticket_flag=ticket or beats, beats_random=beats, below_random=below,
    )


def test_verdict_variants():
    only_control = _verdict([mr("random")])
    assert only_control.kind == "no_method"

    won = _verdict([mr("hot", beats=True), mr("cold"), mr("random")])
    assert won.kind == "some_significant" and won.significant == ["hot"] and won.ticket_only == []
    assert won.methods_compared == 2
    assert "passed only the ticket-level test" not in won.text_en

    # passes the spec's ticket-level test only: reported, but NOT a win
    lenient = _verdict([mr("hot", ticket=True), mr("random")])
    assert lenient.kind == "none_significant" and lenient.significant == []
    assert lenient.ticket_only == ["hot"]
    assert lenient.text_en.startswith("No method beats random with p < 0.01")
    assert "Hot passed only the ticket-level test" in lenient.text_en
    assert "too optimistic" in lenient.text_en and "按注检验" in lenient.text_zh

    below = _verdict([mr("cold", below=True), mr("hot"), mr("random")])
    assert below.kind == "none_significant" and below.below == ["cold"]
    assert "below random" in below.text_en and METHOD_NAMES_EN["cold"] in below.text_en


def test_a_ticket_level_fluke_on_random_draws_is_not_called_a_win():
    """A real case found by scripts/calibrate_backtest.py: on a purely random history Hot
    scores 0.93 vs 0.80 expected. The spec's ticket-level test says p = 0.004 ("beats random");
    the per-draw test says p = 0.03. Tickets bought for one draw are correlated, so only the
    second is trusted."""
    rng = random.Random(500028)
    history = [sorted(rng.sample(range(1, N + 1), K)) for _ in range(90)]
    r = run_backtest(history, N, K, warmup=30, tickets=5, methods=["hot", "random"], seed=7)
    hot = r.methods[0]
    assert hot.avg_matches == pytest.approx(0.93, abs=0.005)
    assert hot.p_value < 0.01 <= hot.p_by_draw  # lenient test passes, per-draw test does not
    assert hot.ticket_flag and not hot.beats_random
    assert r.verdict.kind == "none_significant"
    assert r.verdict.significant == [] and r.verdict.ticket_only == ["hot"]
    assert r.verdict.text_en.startswith("No method beats random")
    assert "passed only the ticket-level test" in r.verdict.text_en


def test_beats_random_requires_both_tests_and_never_applies_to_the_control():
    # Planted effect: both tests agree.
    r = run_backtest(planted_history(250), N, K, warmup=30, tickets=5, methods=ALL, seed=4)
    for m in r.methods:
        if m.method == "random":
            assert not (m.ticket_flag or m.beats_random or m.below_random)
        elif m.beats_random:
            assert m.p_value < 0.01 and m.p_by_draw < 0.01 and m.avg_matches > r.expected_mean
        if m.beats_random:
            assert m.ticket_flag  # a win implies the spec's own test also passed

# ---------- input validation ----------


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(methods=[]),
        dict(methods=["lucky"]),
        dict(warmup=0),
        dict(warmup=122),  # nothing left to test
        dict(tickets=0),
        dict(tickets=51),
    ],
)
def test_bad_inputs_are_rejected(kwargs):
    with pytest.raises(ValueError):
        run_backtest(HISTORY, N, K, **kwargs)


def test_progress_reports_completion():
    marks = []
    run_backtest(HISTORY, N, K, warmup=100, tickets=1, methods=["random"], progress=marks.append)
    assert len(marks) == 22 and marks[-1] == 1.0 and marks == sorted(marks)


def test_duplicate_methods_are_collapsed():
    r = run_backtest(HISTORY, N, K, warmup=100, tickets=1, methods=["hot", "hot", "random"])
    assert [m.method for m in r.methods] == ["hot", "random"]
    assert match_mean(N, K) == pytest.approx(r.expected_mean)
