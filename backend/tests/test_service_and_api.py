import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
import pytest

from app.importers.common import ParsedDraw
from app.importers.service import missing_draw_numbers, store_draws
from app.models import Draw, DrawConflict, Game, ImportLog
from tests.conftest import FIXTURES

D = dt.date


def mega(session) -> Game:
    return session.scalar(select(Game).where(Game.code == "vn_mega_645"))


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


# ---------- schema / presets ----------


def test_presets_seeded_and_idempotent(session):
    from app.games import seed_presets

    assert seed_presets(session) == 0
    codes = {g.code for g in session.scalars(select(Game))}
    assert codes == {"vn_mega_645", "vn_power_655", "my_power_toto_655", "generic_650"}
    g = mega(session)
    assert (g.max_number, g.pick_count, g.is_default) == (45, 6, True)
    power = session.scalar(select(Game).where(Game.code == "vn_power_655"))
    assert power.has_bonus and power.bonus_max == 55


def test_db_enforces_unique_draw_no_and_date(session):
    g = mega(session)
    session.add(Draw(game_id=g.id, draw_no=1, draw_date=D(2026, 1, 1), numbers=[1, 2, 3, 4, 5, 6], source="t"))
    session.commit()
    session.add(Draw(game_id=g.id, draw_no=1, draw_date=D(2026, 1, 2), numbers=[1, 2, 3, 4, 5, 7], source="t"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.add(Draw(game_id=g.id, draw_no=2, draw_date=D(2026, 1, 1), numbers=[1, 2, 3, 4, 5, 7], source="t"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


# ---------- cross-check rule ----------


def pd(no, date, nums):
    return ParsedDraw(numbers=nums, draw_no=no, draw_date=date, line_no=no)


def test_store_adds_then_skips_identical_on_reimport(session):
    g = mega(session)
    batch = [pd(1, D(2026, 1, 2), [1, 2, 3, 4, 5, 6]), pd(2, D(2026, 1, 4), [7, 8, 9, 10, 11, 12])]
    out = store_draws(session, g, batch, source="t")
    assert (out.status, out.added, out.skipped) == ("ok", 2, 0)
    again = store_draws(session, g, batch, source="t")
    assert (again.status, again.added, again.skipped) == ("ok", 0, 2)
    assert count(session, Draw) == 2


def test_conflict_inserts_nothing_and_is_logged(session):
    g = mega(session)
    store_draws(session, g, [pd(1, D(2026, 1, 2), [1, 2, 3, 4, 5, 6])], source="first")
    batch = [
        pd(2, D(2026, 1, 4), [7, 8, 9, 10, 11, 12]),  # new and fine
        pd(1, D(2026, 1, 2), [1, 2, 3, 4, 5, 9]),  # disagrees with stored draw 1
    ]
    out = store_draws(session, g, batch, source="second", kind="collector")
    assert out.status == "conflict"
    assert out.added == 0
    assert len(out.conflicts) == 1
    assert count(session, Draw) == 1  # draw 2 was NOT inserted either
    c = session.scalar(select(DrawConflict))
    assert (c.draw_no, c.existing_numbers, c.incoming_numbers, c.status) == (
        1, [1, 2, 3, 4, 5, 6], [1, 2, 3, 4, 5, 9], "open"
    )
    log = session.scalar(select(ImportLog).order_by(ImportLog.id.desc()))
    assert (log.status, log.added, log.conflicts, log.kind) == ("conflict", 0, 1, "collector")


def test_same_date_different_numbers_is_a_conflict(session):
    g = mega(session)
    store_draws(session, g, [pd(None, D(2026, 1, 2), [1, 2, 3, 4, 5, 6])], source="a")
    out = store_draws(session, g, [pd(None, D(2026, 1, 2), [1, 2, 3, 4, 5, 7])], source="b")
    assert out.status == "conflict"


def test_invalid_rows_are_rejected_not_fixed(session):
    g = mega(session)
    out = store_draws(
        session,
        g,
        [pd(1, D(2026, 1, 2), [1, 2, 3, 4, 5, 6]), pd(2, D(2026, 1, 4), [1, 2, 3, 4, 5, 99])],
        source="t",
    )
    assert out.added == 1
    assert len(out.rejected) == 1 and "outside 1..45" in out.rejected[0].reason


def test_missing_draw_numbers_between_min_and_max(session):
    g = mega(session)
    store_draws(session, g, [pd(n, D(2026, 1, n), [1, 2, 3, 4, 5, n + 6]) for n in (1, 2, 5, 8)], source="t")
    assert missing_draw_numbers(session, g) == [3, 4, 6, 7]


# ---------- REST API ----------


def test_api_games_list_and_create(client):
    games = client.get("/games").json()
    assert games[0]["code"] == "vn_mega_645" and games[0]["is_default"]
    ok = client.post(
        "/games",
        json={"code": "custom_5_30", "name": "Custom", "max_number": 30, "pick_count": 5,
              "ticket_price": "2.5", "currency": "USD"},
    )
    assert ok.status_code == 201
    assert client.post("/games", json={**ok.json(), "ticket_price": "2.5"}).status_code == 409
    for bad in (
        {"max_number": 501}, {"max_number": 5, "pick_count": 5}, {"pick_count": 21},
        {"has_bonus": True}, {"code": "Bad Code"},
    ):
        body = {"code": "x_y", "name": "n", "max_number": 30, "pick_count": 5,
                "ticket_price": "1", "currency": "U", **bad}
        assert client.post("/games", json=body).status_code == 422, bad


def test_api_import_grid_fixture_then_missing_and_list(client):
    with open(FIXTURES / "grid_sample.xlsx", "rb") as fh:
        r = client.post(
            "/games/vn_mega_645/draws/import",
            files={"file": ("grid_sample.xlsx", fh, "application/vnd.ms-excel")},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["format"], body["status"], body["added"], body["rejected_count"]) == ("grid", "ok", 5, 2)
    assert [m["draw_no"] for m in body["missing_rows"]] == [1004, 1002, 1001]

    miss = client.get("/games/vn_mega_645/draws/missing").json()
    assert miss["first_draw_no"] == 998 and miss["last_draw_no"] == 1006
    assert miss["missing"] == [999, 1001, 1002, 1004]

    page = client.get("/games/vn_mega_645/draws", params={"limit": 2}).json()
    assert page["total"] == 5
    assert [d["draw_no"] for d in page["items"]] == [1006, 1005]  # newest first


def test_api_import_text_with_skip_and_conflict(client):
    csv = "draw,date,n1,n2,n3,n4,n5,n6\n1574,2026-10-11,3,9,16,29,30,44\n1573,2026-10-09,5,7,12,23,32,41\n"
    r = client.post(
        "/games/vn_mega_645/draws/import",
        files={"file": ("x.csv", csv.encode(), "text/csv")},
        data={"skip_leading": "1"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 2 and r.json()["headers_skipped"] == 1

    bad = csv.replace("3,9,16,29,30,44", "3,9,16,29,30,45")
    r2 = client.post(
        "/games/vn_mega_645/draws/import",
        files={"file": ("x.csv", bad.encode(), "text/csv")},
        data={"skip_leading": "1"},
    )
    body = r2.json()
    assert body["status"] == "conflict" and body["added"] == 0 and len(body["conflicts"]) == 1
    assert body["conflicts"][0]["existing_numbers"] == [3, 9, 16, 29, 30, 44]


def test_api_unknown_game_and_bad_workbook(client):
    assert client.get("/games/nope/draws").status_code == 404
    r = client.post(
        "/games/vn_mega_645/draws/import",
        files={"file": ("junk.xlsx", b"not a workbook", "application/octet-stream")},
    )
    assert r.status_code == 422
