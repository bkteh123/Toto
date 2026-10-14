import itertools
from fractions import Fraction
from math import comb, isclose

import pytest

from app.analysis import (
    expected_appearances,
    hypergeom_pmf,
    match_distribution,
    match_mean,
    match_variance,
    prob_at_least,
)

TOTAL_645 = comb(45, 6)  # 8,145,060


def test_mega_645_headline_numbers():
    assert TOTAL_645 == 8_145_060
    assert match_mean(45, 6) == pytest.approx(0.8)  # K^2/N = 36/45
    # spec: variance = K*(K/N)*((N-K)/N)*((N-K)/(N-1))
    assert match_variance(45, 6) == pytest.approx(6 * (6 / 45) * (39 / 45) * (39 / 44))
    assert match_variance(45, 6) == pytest.approx(0.6145454545454545)
    assert prob_at_least(45, 6, 3) == pytest.approx(0.0238, abs=5e-5)  # "about 2.38%"


def test_exact_terms_for_645():
    # P(m) = C(6,m) * C(39,6-m) / C(45,6)
    expected = {
        0: Fraction(comb(39, 6), TOTAL_645),
        1: Fraction(6 * comb(39, 5), TOTAL_645),
        2: Fraction(15 * comb(39, 4), TOTAL_645),
        3: Fraction(20 * comb(39, 3), TOTAL_645),  # 182,780 / 8,145,060
        4: Fraction(15 * comb(39, 2), TOTAL_645),
        5: Fraction(6 * 39, TOTAL_645),
        6: Fraction(1, TOTAL_645),
    }
    assert expected[3] == Fraction(182_780, 8_145_060)
    assert sum(expected.values()) == 1
    for m, frac in expected.items():
        assert hypergeom_pmf(45, 6, 6, m) == float(frac)
    # P(>=3) is the sum of exact terms, not a float accumulation
    assert prob_at_least(45, 6, 3) == float(sum(expected[m] for m in (3, 4, 5, 6)))
    assert prob_at_least(45, 6, 3) == pytest.approx(0.023834078570323606, abs=1e-15)  # prototype value


def test_distribution_sums_to_one_and_reproduces_mean_and_variance():
    for n, k, s in [(45, 6, 6), (45, 6, 8), (55, 6, 6), (50, 6, 18), (30, 5, 5), (10, 3, 10), (20, 1, 1)]:
        dist = match_distribution(n, k, s)
        assert sum(dist) == pytest.approx(1.0, abs=1e-12)
        mean = sum(m * p for m, p in enumerate(dist))
        var = sum((m - mean) ** 2 * p for m, p in enumerate(dist))
        assert mean == pytest.approx(match_mean(n, k, s))
        assert var == pytest.approx(match_variance(n, k, s), abs=1e-12)


def test_matches_brute_force_enumeration_on_a_tiny_game():
    n, k, s = 8, 3, 4
    drawn = {1, 2, 3}
    counts = {}
    for ticket in itertools.combinations(range(1, n + 1), s):
        m = len(drawn & set(ticket))
        counts[m] = counts.get(m, 0) + 1
    total = comb(n, s)
    for m in range(min(k, s) + 1):
        assert hypergeom_pmf(n, k, s, m) == pytest.approx(counts.get(m, 0) / total)


def test_bao_set_expectation_matches_spec():
    # S numbers against a K-number draw: mean S*K/N. Spec reference: S=8 -> 1.07 for 6/45.
    assert match_mean(45, 6, 8) == pytest.approx(8 * 6 / 45)
    assert round(match_mean(45, 6, 8), 2) == 1.07


def test_at_least_edges():
    assert prob_at_least(45, 6, 0) == 1.0
    assert prob_at_least(45, 6, 7) == 0.0
    assert prob_at_least(45, 6, 6) == pytest.approx(1 / TOTAL_645)
    # you cannot match fewer than S+K-N numbers: 18 of 20 numbers vs a 6-draw always hits >= 4
    assert hypergeom_pmf(20, 6, 18, 3) == 0.0
    assert prob_at_least(20, 6, 4, s=18) == pytest.approx(1.0)


def test_expected_appearances():
    assert expected_appearances(10, 45, 6) == pytest.approx(10 * 6 / 45)
    assert expected_appearances(0, 45, 6) == 0.0
    assert isclose(expected_appearances(122, 45, 6), 122 * 6 / 45)


@pytest.mark.parametrize("args", [(45, 45), (45, 0), (5, 6), (45, 6, 46), (45, 6, 0)])
def test_bad_game_or_ticket_is_rejected(args):
    with pytest.raises(ValueError):
        match_distribution(*args)
