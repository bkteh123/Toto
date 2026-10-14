import pytest

from app.validation import (
    DrawValidationError,
    GameSpec,
    validate_bonus,
    validate_draw,
    validate_game_rules,
    validate_numbers,
)


def test_valid_numbers_are_sorted():
    assert validate_numbers([44, 3, 9, 16, 30, 29], 45, 6) == [3, 9, 16, 29, 30, 44]


@pytest.mark.parametrize(
    "numbers, fragment",
    [
        ([1, 2, 3, 4, 5], "exactly 6"),
        ([1, 2, 3, 4, 5, 6, 7], "exactly 6"),
        ([1, 2, 3, 4, 5, 46], "outside 1..45"),
        ([0, 2, 3, 4, 5, 6], "outside 1..45"),
        ([1, 1, 3, 4, 5, 6], "distinct"),
        ([1, 2, 3, 4, 5, 6.0], "not an integer"),
        ([1, 2, 3, 4, 5, "6"], "not an integer"),
        ([1, 2, 3, 4, 5, True], "not an integer"),
    ],
)
def test_invalid_numbers_are_rejected(numbers, fragment):
    with pytest.raises(DrawValidationError, match=fragment):
        validate_numbers(numbers, 45, 6)


def test_bonus_rules():
    power = GameSpec("vn_power_655", 55, 6, has_bonus=True, bonus_max=55)
    mega = GameSpec("vn_mega_645", 45, 6)
    nums = [1, 2, 3, 4, 5, 6]
    assert validate_bonus(7, power, nums) == 7
    assert validate_bonus(None, mega, nums) is None
    with pytest.raises(DrawValidationError, match="no bonus"):
        validate_bonus(7, mega, nums)
    with pytest.raises(DrawValidationError, match="outside"):
        validate_bonus(56, power, nums)
    with pytest.raises(DrawValidationError, match="repeats"):
        validate_bonus(3, power, nums)


def test_validate_draw_combines_both():
    power = GameSpec("vn_power_655", 55, 6, has_bonus=True, bonus_max=55)
    assert validate_draw([6, 5, 4, 3, 2, 1], power, 9) == ([1, 2, 3, 4, 5, 6], 9)


@pytest.mark.parametrize("n,k", [(1, 1), (501, 6), (45, 0), (45, 21), (6, 6), (5, 6)])
def test_game_rule_bounds(n, k):
    with pytest.raises(DrawValidationError):
        validate_game_rules(n, k)


def test_game_rule_bounds_accept_limits():
    validate_game_rules(2, 1)
    validate_game_rules(500, 20)
