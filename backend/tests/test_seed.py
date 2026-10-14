"""Integrity of seed/mega645.csv (taken from the prototype's embedded SEED)."""

import datetime as dt
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.importers.excel_grid import parse_grid
from app.importers.service import missing_draw_numbers, store_draws
from app.importers.text_csv import parse_text
from app.models import Draw, Game
from tests.conftest import MEGA

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seed" / "mega645.csv"
WORKBOOK = ROOT / "Mega 6-45 Vietnam.xlsx"

pytestmark = pytest.mark.skipif(not SEED.exists(), reason="seed/mega645.csv not present")


def test_seed_is_complete_wed_fri_sun_schedule():
    r = parse_text(SEED.read_text(encoding="utf-8"), MEGA)
    assert r.rejected == [] and r.headers_skipped == 1
    dates = [d.draw_date for d in r.draws]
    assert (len(dates), dates[0], dates[-1]) == (122, dt.date(2026, 1, 2), dt.date(2026, 10, 11))
    expected = [
        dates[0] + dt.timedelta(days=i)
        for i in range((dates[-1] - dates[0]).days + 1)
        if (dates[0] + dt.timedelta(days=i)).weekday() in (2, 4, 6)
    ]
    assert dates == expected  # no gap, no extra date: 1453..1574 are consecutive draws


@pytest.mark.skipif(not WORKBOOK.exists(), reason="workbook not present")
def test_seed_agrees_with_every_draw_in_the_workbook():
    seed = parse_text(SEED.read_text(encoding="utf-8"), MEGA)
    by_date = {d.draw_date: (1453 + i, d.numbers) for i, d in enumerate(seed.draws)}
    sheet = parse_grid(WORKBOOK, MEGA)
    assert len(sheet.draws) == 57
    for d in sheet.draws:
        assert by_date[d.draw_date] == (d.draw_no, d.numbers), d


def test_seed_loads_without_gaps(session):
    game = session.scalar(select(Game).where(Game.code == "vn_mega_645"))
    r = parse_text(SEED.read_text(encoding="utf-8"), MEGA)
    for i, d in enumerate(r.draws):
        d.draw_no = 1453 + i
    out = store_draws(session, game, r.draws, source="seed")
    assert (out.status, out.added) == ("ok", 122)
    assert missing_draw_numbers(session, game) == []
    assert session.scalar(select(func.count()).select_from(Draw)) == 122
    again = store_draws(session, game, r.draws, source="seed")
    assert (again.added, again.skipped) == (0, 122)  # idempotent
