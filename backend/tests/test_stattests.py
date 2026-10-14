import math

import pytest

from app.analysis.stattests import normal_two_sided_p, student_t_two_sided_p


def test_normal_two_sided_p_known_values():
    assert normal_two_sided_p(0.0) == 1.0
    assert normal_two_sided_p(1.959963984540054) == pytest.approx(0.05, abs=1e-12)
    assert normal_two_sided_p(2.5758293035489) == pytest.approx(0.01, abs=1e-12)
    assert normal_two_sided_p(-2.5758293035489) == normal_two_sided_p(2.5758293035489)
    assert normal_two_sided_p(8.0) < 1e-14


@pytest.mark.parametrize(
    "t,df,p",
    [
        (12.706204736, 1, 0.05),  # standard critical values
        (4.302652730, 2, 0.05),
        (2.570581836, 5, 0.05),
        (2.228138852, 10, 0.05),
        (3.169272667, 10, 0.01),
        (2.042272456, 30, 0.05),
        (1.983971519, 100, 0.05),
    ],
)
def test_student_t_two_sided_p_against_critical_values(t, df, p):
    assert student_t_two_sided_p(t, df) == pytest.approx(p, abs=1e-7)


def test_student_t_closed_forms_and_limits():
    # df=1 is Cauchy: p = 1 - (2/pi) * atan(t);  df=2: p = 1 - t / sqrt(t^2 + 2)
    for t in (0.3, 1.0, 3.0, 10.0):
        assert student_t_two_sided_p(t, 1) == pytest.approx(1 - 2 / math.pi * math.atan(t), abs=1e-12)
        assert student_t_two_sided_p(t, 2) == pytest.approx(1 - t / math.sqrt(t * t + 2), abs=1e-12)
    # df=4 has a closed-form CDF: 1/2 + (3/8) * u * (1 - t^2 / (12 (1 + t^2/4))),  u = t / sqrt(1 + t^2/4)
    for t in (0.5, 1.5, 2.776445105, 6.0):
        s = 1 + t * t / 4
        cdf = 0.5 + 0.375 * (t / math.sqrt(s)) * (1 - t * t / (12 * s))
        assert student_t_two_sided_p(t, 4) == pytest.approx(2 * (1 - cdf), abs=1e-12)
    assert student_t_two_sided_p(0.0, 7) == 1.0
    assert student_t_two_sided_p(-2.0, 12) == student_t_two_sided_p(2.0, 12)
    # a big df approaches the normal
    assert student_t_two_sided_p(1.96, 1_000_000) == pytest.approx(normal_two_sided_p(1.96), abs=1e-5)
    with pytest.raises(ValueError):
        student_t_two_sided_p(1.0, 0)
