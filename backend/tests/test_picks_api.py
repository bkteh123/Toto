import random

import pytest
from sqlalchemy import select

import app.api.picks as picks
from app.models import Draw, Game
from tests.fakesite import load_seed


@pytest.fixture
def loaded(session):
    g = session.scalar(select(Game).where(Game.code == "vn_mega_645"))
    for d in load_seed():
        session.add(Draw(game_id=g.id, draw_no=d.draw_no, draw_date=d.date, numbers=d.numbers, source="t"))
    session.commit()


# ---------- generate ----------


def test_generate_returns_valid_distinct_combinations(client, loaded):
    r = client.post("/games/vn_mega_645/generate", json={"method": "weighted", "count": 8})
    assert r.status_code == 200, r.text
    body = r.json()
    combos = body["combinations"]
    assert len(combos) == 8 and body["shortfall"] == 0 and body["draw_count"] == 122
    assert len({tuple(c) for c in combos}) == 8
    for c in combos:
        assert len(c) == 6 and c == sorted(c) and len(set(c)) == 6 and all(1 <= x <= 45 for x in c)
    assert "not probabilities of winning" in body["note"]


def test_generate_uses_the_csprng_for_users(client, loaded, monkeypatch):
    calls = []

    def spy():
        calls.append(1)
        return random.Random(42)

    monkeypatch.setattr(picks, "system_rng", spy)
    a = client.post("/games/vn_mega_645/generate", json={"method": "hot", "count": 3}).json()
    b = client.post("/games/vn_mega_645/generate", json={"method": "hot", "count": 3}).json()
    assert len(calls) == 2
    assert a["combinations"] == b["combinations"]  # same injected seed => same output, proving the hook


def test_generate_follows_weights_and_mix(client, loaded, monkeypatch):
    monkeypatch.setattr(picks, "system_rng", lambda: random.Random(5))
    a = client.post("/games/vn_mega_645/generate", json={"method": "weighted", "count": 10}).json()
    monkeypatch.setattr(picks, "system_rng", lambda: random.Random(5))
    b = client.post("/games/vn_mega_645/generate",
                    json={"method": "weighted", "count": 10, "mix": 100, "w10": 1, "w20": 0, "w50": 0, "w100": 0}).json()
    assert a["combinations"] != b["combinations"]


@pytest.mark.parametrize(
    "body",
    [
        {"method": "lucky", "count": 5},
        {"method": "hot", "count": 0},
        {"method": "hot", "count": 51},
        {"method": "hot", "count": 5, "mix": 150},
        {"method": "hot", "count": 5, "w10": 0, "w20": 0, "w50": 0, "w100": 0},
    ],
)
def test_generate_rejects_bad_requests(client, loaded, body):
    assert client.post("/games/vn_mega_645/generate", json=body).status_code == 422


def test_generate_with_no_draws(client):
    assert client.post("/games/vn_mega_645/generate", json={"method": "hot", "count": 2}).status_code == 409
    r = client.post("/games/vn_mega_645/generate", json={"method": "random", "count": 2})
    assert r.status_code == 200 and len(r.json()["combinations"]) == 2  # the baseline needs no history
    assert client.post("/games/nope/generate", json={"method": "random", "count": 2}).status_code == 404


def test_generate_shortfall_on_a_tiny_custom_game(client):
    client.post("/games", json={"code": "tiny_6_7", "name": "Tiny", "max_number": 7, "pick_count": 6,
                                "ticket_price": "1", "currency": "U"})
    r = client.post("/games/tiny_6_7/generate", json={"method": "random", "count": 10}).json()
    assert len(r["combinations"]) == 7 and r["shortfall"] == 3


# ---------- bao ----------


def test_bao_reference_result(client, loaded):
    r = client.post("/games/vn_mega_645/bao", json={"size": 8, "window": 10, "end_draw_no": 1574})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["numbers"] == [2, 3, 9, 15, 16, 27, 33, 41]
    assert [t["number"] for t in b["tied_alternatives"]] == [29, 30, 12, 10, 36, 37, 20, 6, 31, 25]
    assert all(t["appearances"] == 2 for t in b["tied_alternatives"])
    assert (b["lines"], b["cost"], b["currency"]) == (28, 280000.0, "VND")
    assert b["jackpot_one_in"] == pytest.approx(290895.0)
    assert b["special_bao"] is False and b["rule_note"] is None
    assert b["end_draw_no"] == 1574 and b["later_draws"] == []
    rc = b["rule_check"]
    assert rc["draws_tested"] == 112
    assert rc["avg_hits"] == pytest.approx(1.0267857, abs=1e-6)
    assert rc["expected_hits"] == pytest.approx(1.0666667, abs=1e-6)
    assert rc["draws_with_3_plus"] == 4
    assert b["expected_hits"] == pytest.approx(8 * 6 / 45)


def test_bao_default_ending_draw_is_the_latest(client, loaded):
    a = client.post("/games/vn_mega_645/bao", json={"size": 8, "window": 10}).json()
    assert a["end_draw_no"] == 1574 and a["numbers"] == [2, 3, 9, 15, 16, 27, 33, 41]


def test_bao_earlier_ending_draw_lists_every_later_draw(client, loaded):
    b = client.post("/games/vn_mega_645/bao", json={"size": 8, "window": 10, "end_draw_no": 1560}).json()
    assert b["end_draw_no"] == 1560
    later = b["later_draws"]
    assert [d["draw_no"] for d in later] == list(range(1561, 1575))
    chosen = set(b["numbers"])
    for d in later:
        assert d["hits"] == sorted(chosen & set(d["numbers"]))
        assert d["jackpot"] == (len(d["hits"]) == 6)


def test_bao_5_special_case(client, loaded):
    b = client.post("/games/vn_mega_645/bao", json={"size": 5, "window": 10}).json()
    assert b["special_bao"] is True
    assert len(b["numbers"]) == 5
    assert (b["lines"], b["cost"]) == (40, 400000.0)  # 40 lines x 10,000 VND
    assert b["jackpot_one_in"] == pytest.approx(8_145_060 / 40)
    assert "40 lines" in b["rule_note"] and "all 5 of your numbers" in b["rule_note"]
    # "jackpot" on a later draw means all 5 of your numbers are in it
    b2 = client.post("/games/vn_mega_645/bao", json={"size": 5, "window": 10, "end_draw_no": 1500}).json()
    for d in b2["later_draws"]:
        assert d["jackpot"] == (len(d["hits"]) == 5)


@pytest.mark.parametrize(
    "body, status",
    [
        ({"size": 6, "window": 10}, 422),  # a 6-number "bao" is just a ticket
        ({"size": 4, "window": 10}, 422),
        ({"size": 19, "window": 10}, 422),
        ({"size": 8, "window": 10, "end_draw_no": 9999}, 422),  # not stored
        ({"size": 8, "window": 10, "end_draw_no": 1455}, 422),  # fewer than W draws up to it
        ({"size": 8, "window": 0}, 422),
    ],
)
def test_bao_rejects_bad_requests(client, loaded, body, status):
    assert client.post("/games/vn_mega_645/bao", json=body).status_code == status


def test_bao_without_draws_or_game(client):
    assert client.post("/games/vn_mega_645/bao", json={"size": 8, "window": 10}).status_code == 409
    assert client.post("/games/nope/bao", json={"size": 8, "window": 10}).status_code == 404
