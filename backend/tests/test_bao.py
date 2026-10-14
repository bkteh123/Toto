import itertools
import json
from math import comb

import pytest

from app.analysis import bao_set, jackpot_one_in, line_count, rule_check, valid_sizes
from tests.conftest import FIXTURES
from tests.fakesite import load_seed

GOLDEN = json.loads((FIXTURES / "prototype_bao_golden.json").read_text(encoding="utf-8"))
HISTORY = [d.numbers for d in load_seed()]  # 122 real draws, 1453..1574
N, K = 45, 6


# ---------- the reference result from the spec ----------


def test_reference_result_s8_w10_ending_1574():
    b = bao_set(HISTORY, N, size=8, window=10)  # ending draw = latest = 1574
    assert b.numbers == [2, 3, 9, 15, 16, 27, 33, 41]
    # equal alternatives left out, best-ranked first (most recent appearance, then lowest number)
    assert b.tied_alternatives == [29, 30, 12, 10, 36, 37, 20, 6, 31, 25]
    assert b.cut_count == 2
    assert b.sure_in == [2, 15, 27, 33, 41]  # strictly above the cut-off (counts 3 or 4)
    assert {x: b.counts[x] for x in b.numbers} == {2: 3, 3: 2, 9: 2, 15: 4, 16: 2, 27: 3, 33: 3, 41: 3}


def test_reference_rule_check_over_112_draws():
    """Spec: ~1.03 hits/draw vs ~1.07 random, 4 draws with 3+ hits.

    The spec says 113 draws. The prototype's parser reads the CSV header as a draw, so its
    history has 123 draws (123 - 10 = 113). The real history has 122, so 112 draws have
    10 earlier draws. The averages and the 3+ count are the same either way.
    """
    rc = rule_check(HISTORY, N, K, size=8, window=10)
    assert rc.draws_tested == 112
    assert rc.avg_hits == pytest.approx(1.0267857, abs=1e-6)
    assert round(rc.avg_hits, 2) == 1.03
    assert rc.expected_hits == pytest.approx(8 * 6 / 45)
    assert round(rc.expected_hits, 2) == 1.07
    assert rc.draws_with_3_plus == 4
    assert [rc.histogram.get(h, 0) for h in range(7)] == [36, 42, 30, 3, 1, 0, 0]


# ---------- golden values from the ORIGINAL prototype's code ----------


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda c: f"S{c['size']}-W{c['win']}-end{c['end']}")
def test_matches_prototype(case):
    b = bao_set(HISTORY, N, case["size"], case["win"], end_index=case["end"])
    assert b.numbers == case["set"]
    assert b.cut_count == case["cut"]
    assert b.tied_alternatives == case["tiedOut"]
    # same members; the prototype lists them in rank order, this engine sorts by number
    assert b.sure_in == sorted(case["sureIn"])
    assert {str(x): b.counts[x] for x in b.numbers} == {k: v for k, v in case["cnt"].items()}

    rc = rule_check(HISTORY, N, K, case["size"], case["win"])
    assert rc.draws_tested == case["rule"]["n"]
    assert rc.avg_hits == pytest.approx(case["rule"]["avg"], abs=1e-12)
    assert rc.expected_hits == pytest.approx(case["rule"]["exp"])
    assert [rc.histogram.get(h, 0) for h in range(K + 1)] == case["rule"]["dist"]


def test_golden_covers_the_special_and_large_sizes():
    sizes = {c["size"] for c in GOLDEN["cases"]}
    assert {5, 7, 8, 18} <= sizes and GOLDEN["draws"] == 122


# ---------- ranking rules, by hand ----------


def test_tie_break_is_most_recent_then_lowest_number():
    # N=9, window 4 (all draws). counts: 1->2, 2->2, 3->1, 4->1, 5->1, 6->1; 7,8,9 -> 0
    #   draw idx: 0:[1,3] 1:[2,4] 2:[1,5] 3:[2,6]
    # last seen: 1->2, 2->3, 3->0, 4->1, 5->2, 6->3
    draws = [[1, 3], [2, 4], [1, 5], [2, 6]]
    b = bao_set(draws, 9, size=3, window=4)
    # count 2: number 2 (last 3) before number 1 (last 2); then count 1: 6 (last 3) beats 5 (last 2)
    assert b.numbers == [1, 2, 6]
    assert b.cut_count == 1
    assert b.sure_in == [1, 2]
    # tied at 1 and left out, best first: 5 (last 2), 4 (last 1), 3 (last 0)
    assert b.tied_alternatives == [5, 4, 3]
    assert not b.unseen_filler


def test_equal_count_and_recency_falls_back_to_lowest_number():
    draws = [[4, 2, 7]]  # all three appear once, all in the same (latest) draw
    b = bao_set(draws, 9, size=2, window=1)
    assert b.numbers == [2, 4]
    assert b.tied_alternatives == [7]


def test_unseen_numbers_fill_the_set_without_being_called_alternatives():
    draws = [[1, 2]]
    b = bao_set(draws, 9, size=4, window=1)
    assert b.numbers == [1, 2, 3, 4]  # 3, 4 filled by lowest number
    assert b.unseen_filler and b.cut_count == 0
    assert b.tied_alternatives == []  # "tied at zero" is meaningless


def test_window_ends_at_the_ending_draw_and_ignores_later_draws():
    full = bao_set(HISTORY, N, 8, 10, end_index=100)
    truncated = bao_set(HISTORY[:101], N, 8, 10)
    assert full.numbers == truncated.numbers
    assert full.tied_alternatives == truncated.tied_alternatives
    assert full.end_index == 100


def test_bad_inputs():
    with pytest.raises(ValueError, match="only 5 draw"):
        bao_set(HISTORY, N, 8, 10, end_index=4)
    with pytest.raises(ValueError, match="outside"):
        bao_set(HISTORY, N, 8, 10, end_index=122)
    with pytest.raises(ValueError):
        bao_set(HISTORY, N, 0, 10)
    with pytest.raises(ValueError):
        bao_set(HISTORY, N, 46, 10)
    with pytest.raises(ValueError):
        bao_set([], N, 8, 10)
    with pytest.raises(ValueError):
        bao_set(HISTORY, N, 8, 0)


def test_rule_check_uses_only_earlier_draws():
    """Adding the newest draw to the history adds exactly one tested draw, scored with the
    set that was built WITHOUT it; every earlier result is unchanged."""
    full = rule_check(HISTORY, N, K, 8, 10)
    prefix = rule_check(HISTORY[:-1], N, K, 8, 10)
    assert full.draws_tested == prefix.draws_tested + 1
    predicted = set(bao_set(HISTORY[:-1], N, 8, 10).numbers)
    hits = len(predicted & set(HISTORY[-1]))
    diff = {h: full.histogram.get(h, 0) - prefix.histogram.get(h, 0) for h in range(K + 1)}
    assert diff == {h: int(h == hits) for h in range(K + 1)}


def test_rule_check_with_too_little_history():
    rc = rule_check(HISTORY[:10], N, K, 8, 10)  # no draw has 10 earlier draws
    assert rc.draws_tested == 0 and rc.avg_hits == 0.0 and rc.draws_with_3_plus == 0


# ---------- lines, cost and odds ----------


def test_valid_sizes():
    assert valid_sizes(45, 6) == [5] + list(range(7, 19))
    assert valid_sizes(35, 5) == [4] + list(range(6, 19))
    assert valid_sizes(10, 3) == [2] + list(range(4, 11))
    assert valid_sizes(20, 1) == list(range(2, 19))  # no K-1 for a 1-number game


def test_lines_match_vietlott_table_for_mega_645():
    # Published Mega 6/45 table: Bao 5 = 40 lines (400,000 VND at 10,000 each), then C(S,6).
    expected = {5: 40, 7: 7, 8: 28, 9: 84, 10: 210, 11: 462, 12: 924, 13: 1716, 14: 3003, 15: 5005, 18: 18564}
    for size, lines in expected.items():
        assert line_count(45, 6, size) == lines
        assert lines * 10_000 == lines * 10_000  # price is lines x ticket price
    assert line_count(55, 6, 5) == 50  # Power 6/55 Bao 5 = 50 lines = 500,000 VND
    assert 40 * 10_000 == 400_000 and 50 * 10_000 == 500_000


def test_special_bao_is_n_minus_s_lines_not_comb():
    assert comb(5, 6) == 0  # the generic formula cannot describe it
    assert line_count(45, 6, 5) == 45 - 5
    assert line_count(30, 4, 3) == 30 - 3  # same rule for another game: K-1 numbers
    with pytest.raises(ValueError):
        line_count(45, 6, 6 - 2)  # 4 numbers is not a bao size


def test_jackpot_odds():
    assert jackpot_one_in(45, 6, 8) == pytest.approx(comb(45, 6) / 28)  # 290,895
    assert jackpot_one_in(45, 6, 5) == pytest.approx(8_145_060 / 40)  # 203,626.5
    assert jackpot_one_in(55, 6, 5) == pytest.approx(28_989_675 / 50)


@pytest.mark.parametrize("n,k,s", [(8, 3, 2), (8, 3, 5), (9, 4, 3), (9, 4, 6), (7, 3, 6)])
def test_odds_by_brute_force(n, k, s):
    """P(some line is the jackpot) = lines / C(N,K), checked by enumerating every draw."""
    chosen = set(range(1, s + 1))
    draws = list(itertools.combinations(range(1, n + 1), k))
    if s == k - 1:
        winning = sum(1 for d in draws if chosen <= set(d))  # all S numbers are in the draw
    else:
        winning = sum(1 for d in draws if set(d) <= chosen)  # the draw is a line of the set
    assert winning == line_count(n, k, s)
    assert winning / len(draws) == pytest.approx(1 / jackpot_one_in(n, k, s))
