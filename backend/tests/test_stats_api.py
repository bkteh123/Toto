import json

import pytest
from sqlalchemy import select

from app.models import Draw, Game
from tests.conftest import FIXTURES
from tests.fakesite import load_seed

GOLDEN = json.loads((FIXTURES / "prototype_scores_golden.json").read_text(encoding="utf-8"))


@pytest.fixture
def loaded(session):
    g = session.scalar(select(Game).where(Game.code == "vn_mega_645"))
    for d in load_seed():
        session.add(Draw(game_id=g.id, draw_no=d.draw_no, draw_date=d.date, numbers=d.numbers, source="t"))
    session.commit()


def test_stats_default_matches_prototype_golden(client, loaded):
    r = client.get("/games/vn_mega_645/stats")
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["n"], body["k"], body["draw_count"], body["period"], body["span"]) == (45, 6, 122, "10", 10)
    assert body["weights"] == pytest.approx([0.4, 0.25, 0.2, 0.15])
    assert body["mix"] == pytest.approx(0.5)
    assert "not probabilities of winning" in body["note"]
    assert len(body["rows"]) == 45

    for row, g in zip(body["rows"], GOLDEN["ending"]):
        assert row["number"] == g["n"]
        assert row["counts"] == g["cnt"]
        assert (row["gap"], row["rank"], row["cls"]) == (g["gap"], g["rank"], g["cls"])
        assert row["hot"] == pytest.approx(g["hot"], abs=1e-12)
        assert row["cold"] == pytest.approx(g["cold"], abs=1e-12)
        assert row["combined"] == pytest.approx(g["comb"], abs=1e-12)
        assert row["appearances"] == g["cnt"]["10"]
        assert row["frequency"] == pytest.approx(g["cnt"]["10"] / 10)

    e = body["expectation"]
    assert e["ticket_mean_matches"] == pytest.approx(0.8)
    assert e["p_at_least_3"] == pytest.approx(0.0238, abs=5e-5)
    assert e["appearances_in_period"] == pytest.approx(10 * 6 / 45)
    assert len(body["hottest_10"]) == 8 and len(body["coldest"]) == 8


def test_stats_period_weights_and_mix_parameters(client, loaded):
    r = client.get(
        "/games/vn_mega_645/stats",
        params={"period": "all", "w10": 1, "w20": 1, "w50": 1, "w100": 1, "mix": 30},
    ).json()
    assert r["span"] == 122 and r["mix"] == pytest.approx(0.3)
    assert r["weights"] == pytest.approx([0.25] * 4)
    for row, g in zip(r["rows"], GOLDEN["alt"]["rows"]):
        assert row["combined"] == pytest.approx(g["comb"], abs=1e-12)
        assert row["appearances"] == g["cnt"]["all"]
    assert r["expectation"]["appearances_in_period"] == pytest.approx(122 * 6 / 45)


@pytest.mark.parametrize(
    "params",
    [
        {"period": "7"},
        {"w10": -1},
        {"w10": 0, "w20": 0, "w50": 0, "w100": 0},
        {"mix": 101},
        {"mix": -1},
    ],
)
def test_stats_rejects_bad_parameters(client, loaded, params):
    assert client.get("/games/vn_mega_645/stats", params=params).status_code == 422


def test_stats_unknown_game_and_empty_game(client):
    assert client.get("/games/nope/stats").status_code == 404
    r = client.get("/games/vn_mega_645/stats")  # no draws stored
    assert r.status_code == 200
    body = r.json()
    assert body["draw_count"] == 0 and body["span"] == 0
    assert all(x["appearances"] == 0 and x["gap"] == 0 for x in body["rows"])
