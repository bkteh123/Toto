import datetime as dt

import pytest
from sqlalchemy import func, select

from app.collectors.minhngoc import MinhNgocMega645
from app.collectors.runner import run_collect
from app.importers.service import missing_draw_numbers
from app.models import Draw, DrawConflict, Game, ImportLog
from tests.fakesite import FakeSite, load_seed

C = MinhNgocMega645()
D = dt.date
SEED = load_seed()
GAP = set(range(1479, 1543)) | {1571}  # what the user's workbook is missing


def mega(session) -> Game:
    return session.scalar(select(Game).where(Game.code == "vn_mega_645"))


def store(session, draws, tamper=None):
    g = mega(session)
    for d in draws:
        nums = (tamper or {}).get(d.draw_no, d.numbers)
        session.add(Draw(game_id=g.id, draw_no=d.draw_no, draw_date=d.date, numbers=sorted(nums), source="test"))
    session.commit()


def n_draws(session):
    return session.scalar(select(func.count()).select_from(Draw))


def workbook_like():
    """Exactly the 57 draws that carry numbers in the user's workbook."""
    return [d for d in SEED if d.draw_no not in GAP]


def test_gap_fill_adds_the_missing_65_and_nothing_else(session):
    store(session, workbook_like())
    assert missing_draw_numbers(session, mega(session)) == sorted(GAP)
    site = FakeSite(SEED)
    res = run_collect(session, mega(session), C, site.fetcher(), mode="gaps", today=D(2026, 10, 13))
    session.commit()

    assert (res.status, res.added) == ("ok", 65)
    assert res.missing_after == []
    assert n_draws(session) == 122
    # 64-draw gap = 7 pages (10 per page), plus 1 page for the single missing draw 1571
    assert len(site.requests) == 8
    assert {p.status for p in res.pages} == {"ok"}
    # inserted rows carry the source, and are exactly the site's numbers
    row = session.scalar(select(Draw).where(Draw.draw_no == 1500))
    assert row.source == "minhngoc.net.vn"
    assert row.numbers == next(d.numbers for d in SEED if d.draw_no == 1500)


def test_cross_check_conflict_inserts_nothing_and_leaves_the_gap(session):
    # Stored draw 1572 sits on the page that fills gap 1571, and disagrees with the source.
    # Gap mode only fetches pages near gaps, so tampering elsewhere would never be seen.
    store(session, workbook_like(), tamper={1572: [1, 2, 3, 4, 5, 6]})
    before = n_draws(session)
    res = run_collect(session, mega(session), C, FakeSite(SEED).fetcher(), mode="gaps", today=D(2026, 10, 13))
    session.commit()

    assert res.status == "conflict"
    # nothing at all is inserted, not even the 64 other gap draws fetched cleanly in the same run
    assert res.added == 0 and n_draws(session) == before
    assert [(c.draw_no, c.existing_numbers) for c in res.conflicts] == [(1572, [1, 2, 3, 4, 5, 6])]
    assert 1571 in res.missing_after and 1500 in res.missing_after  # gaps untouched
    c = session.scalar(select(DrawConflict))
    assert (c.draw_no, c.status) == (1572, "open")
    log = session.scalar(select(ImportLog).where(ImportLog.kind == "collector"))
    assert (log.status, log.added, log.conflicts) == ("conflict", 0, 1)


def test_latest_not_published_yet_adds_nothing_and_says_so(session):
    store(session, SEED)
    site = FakeSite(SEED)
    # Wed 14 Oct 2026 is a draw day but the site has no page for it and serves the latest instead
    res = run_collect(session, mega(session), C, site.fetcher(), mode="latest", today=D(2026, 10, 14))
    assert res.status == "ok" and res.added == 0
    assert [p.status for p in res.pages] == ["not_published"]
    assert "newest draw is 1574" in res.pages[0].note


def test_latest_adds_the_new_draw(session):
    store(session, [d for d in SEED if d.draw_no <= 1573])
    res = run_collect(session, mega(session), C, FakeSite(SEED).fetcher(), mode="latest", today=D(2026, 10, 11))
    session.commit()
    assert (res.status, res.added, res.skipped) == ("ok", 1, 9)  # 1574 new; 9 earlier ones cross-checked
    assert session.scalar(select(Draw).where(Draw.draw_no == 1574)).numbers == [3, 9, 16, 29, 30, 44]


def test_latest_on_a_non_draw_day_targets_the_last_scheduled_draw(session):
    store(session, [d for d in SEED if d.draw_no <= 1573])
    site = FakeSite(SEED)
    res = run_collect(session, mega(session), C, site.fetcher(), mode="latest", today=D(2026, 10, 13))  # Tuesday
    assert res.added == 1
    assert site.requests == [C.page_url(D(2026, 10, 11))]


def test_source_down_reports_and_leaves_gap(session):
    store(session, workbook_like())
    res = run_collect(session, mega(session), C, FakeSite(SEED, down=True).fetcher(), mode="auto",
                      today=D(2026, 10, 13))
    session.commit()
    assert res.status == "unreachable" and res.added == 0
    assert n_draws(session) == 57 and res.missing_after == sorted(GAP)
    log = session.scalar(select(ImportLog).where(ImportLog.kind == "collector"))
    assert log.status == "unreachable"


def test_partial_outage_keeps_what_was_fetched_and_flags_the_rest(session):
    store(session, workbook_like())
    site = FakeSite(SEED, fail_after=3)  # 3 good pages, then 503 forever
    res = run_collect(session, mega(session), C, site.fetcher(retries=0), mode="gaps", today=D(2026, 10, 13))
    session.commit()
    assert res.status == "ok"
    assert 0 < res.added < 65
    assert "unreachable" in res.message
    assert any(p.status == "unreachable" for p in res.pages)
    assert set(res.missing_after) < GAP  # some gaps filled, the rest left as they were


def test_layout_change_stops_the_run_and_inserts_nothing(session):
    store(session, workbook_like())
    res = run_collect(session, mega(session), C, FakeSite(SEED, garbage=True).fetcher(), mode="auto",
                      today=D(2026, 10, 13))
    session.commit()
    assert res.status == "error"
    assert "layout differs" in res.message
    assert n_draws(session) == 57
    log = session.scalar(select(ImportLog).where(ImportLog.kind == "collector"))
    assert log.status == "error" and "Bảo trì" in log.detail["message"]


def test_verify_compares_stored_history_and_inserts_nothing(session):
    store(session, SEED)
    res = run_collect(session, mega(session), C, FakeSite(SEED).fetcher(), mode="verify",
                      from_no=1453, to_no=1574, today=D(2026, 10, 13))
    session.commit()
    assert (res.status, res.added) == ("ok", 0)
    assert res.skipped == 122  # every stored draw re-read from the source and matching
    assert n_draws(session) == 122


def test_verify_detects_a_wrong_stored_draw(session):
    store(session, SEED, tamper={1500: [40, 41, 42, 43, 44, 45]})
    res = run_collect(session, mega(session), C, FakeSite(SEED).fetcher(), mode="verify",
                      from_no=1453, to_no=1574, today=D(2026, 10, 13))
    assert res.status == "conflict"
    assert [c.draw_no for c in res.conflicts] == [1500]


def test_verify_never_inserts_even_for_draws_the_page_shows_that_are_not_stored(session):
    store(session, [d for d in SEED if d.draw_no >= 1560])
    res = run_collect(session, mega(session), C, FakeSite(SEED).fetcher(), mode="verify",
                      from_no=1560, to_no=1574, today=D(2026, 10, 13))
    session.commit()
    assert res.added == 0 and res.not_inserted > 0
    assert n_draws(session) == 15


def test_max_pages_bounds_a_run(session):
    store(session, workbook_like())
    site = FakeSite(SEED)
    res = run_collect(session, mega(session), C, site.fetcher(), mode="gaps", today=D(2026, 10, 13), max_pages=3)
    assert len(site.requests) == 3
    assert res.missing_after  # not everything was filled, and that is reported


def test_second_run_is_a_no_op(session):
    store(session, workbook_like())
    site = FakeSite(SEED)
    run_collect(session, mega(session), C, site.fetcher(), mode="gaps", today=D(2026, 10, 13))
    session.commit()
    site2 = FakeSite(SEED)
    res = run_collect(session, mega(session), C, site2.fetcher(), mode="auto", today=D(2026, 10, 11))
    assert res.added == 0 and res.missing_before == []
    assert len(site2.requests) == 1  # just the latest page; no gaps to chase


def test_wrong_collector_for_game_is_refused(session):
    power = session.scalar(select(Game).where(Game.code == "vn_power_655"))
    with pytest.raises(ValueError, match="is for vn_mega_645"):
        run_collect(session, power, C, FakeSite(SEED).fetcher())
