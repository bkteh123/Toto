import datetime as dt

from app.importers.text_csv import parse_text
from tests.conftest import MEGA, POWER

D = dt.date


def test_iso_and_dmy_dates_and_header_line():
    text = (
        "date,n1,n2,n3,n4,n5,n6\n"  # header: digits inside tokens must NOT count as numbers
        "2026-10-11,3,9,16,29,30,44\n"
        "09/10/2026,5,7,12,23,32,41\n"
    )
    r = parse_text(text, MEGA)
    assert r.headers_skipped == 1
    assert r.rejected == []
    # sorted oldest -> newest by date
    assert [d.draw_date for d in r.draws] == [D(2026, 10, 9), D(2026, 10, 11)]
    assert r.draws[1].numbers == [3, 9, 16, 29, 30, 44]
    assert r.ordering == "date"


def test_skip_leading_integers_and_draw_no():
    r = parse_text("1574,11/10/2026,3,9,16,29,30,44\n", MEGA, skip_leading=1)
    assert len(r.draws) == 1
    assert r.draws[0].draw_no == 1574
    assert r.draws[0].numbers == [3, 9, 16, 29, 30, 44]


def test_rejected_rows_are_counted_with_reasons():
    text = "\n".join(
        [
            "2026-01-02,1,2,3,4,5",  # only 5
            "2026-01-04,1,2,3,4,5,5",  # duplicate
            "2026-01-06,1,2,3,4,5,46",  # out of range
            "31/02/2026,1,2,3,4,5,6",  # impossible date
            "2026-01-08,1,2,3,4,5,6",  # ok
        ]
    )
    r = parse_text(text, MEGA)
    assert len(r.draws) == 1
    assert len(r.rejected) == 4
    reasons = " | ".join(x.reason for x in r.rejected)
    assert "need 0 to skip + 6" in reasons
    assert "distinct" in reasons
    assert "outside 1..45" in reasons
    assert "invalid date" in reasons


def test_no_dates_keeps_file_order_oldest_to_newest():
    r = parse_text("10 11 12 13 14 15\n1 2 3 4 5 6\n", MEGA)
    assert r.ordering == "file"
    assert [d.numbers[0] for d in r.draws] == [10, 1]


def test_mixed_dates_keeps_file_order():
    r = parse_text("2026-02-01 1 2 3 4 5 6\n7 8 9 10 11 12\n2026-01-01 13 14 15 16 17 18\n", MEGA)
    assert r.ordering == "file"
    assert [d.numbers[0] for d in r.draws] == [1, 7, 13]


def test_bonus_ball_and_extra_integers():
    r = parse_text("2026-01-02 1 2 3 4 5 6 7\n", POWER)
    assert r.draws[0].bonus == 7
    assert r.warnings == []
    r2 = parse_text("2026-01-02 1 2 3 4 5 6 7 8\n", POWER)  # two leftovers: ignored, flagged
    assert r2.draws[0].bonus is None
    assert len(r2.warnings) == 1
    r3 = parse_text("2026-01-02 1 2 3 4 5 6 7\n", MEGA)  # no bonus game: leftover flagged
    assert len(r3.draws) == 1 and len(r3.warnings) == 1


def test_blank_lines_are_ignored_and_not_headers():
    r = parse_text("\n\nDate, Numbers\n\n2026-01-02 1 2 3 4 5 6\n", MEGA)
    assert r.headers_skipped == 1
    assert len(r.draws) == 1
