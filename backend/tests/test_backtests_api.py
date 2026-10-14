import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

import app.jobs as jobs
from app.api.collect import session_factory_dep
from app.db import get_session
from app.jobs import execute_backtest, recover_interrupted_jobs
from app.main import create_app
from app.models import Backtest, Draw, Game, ImportLog
from tests.fakesite import load_seed

SEED = load_seed()


@pytest.fixture
def factory(engine, session):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def api(factory):
    app = create_app()

    def _session():  # fresh session per request, like production
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[session_factory_dep] = lambda: factory
    return TestClient(app)


@pytest.fixture
def loaded(session):
    g = session.scalar(select(Game).where(Game.code == "vn_mega_645"))
    for d in SEED:
        session.add(Draw(game_id=g.id, draw_no=d.draw_no, draw_date=d.date, numbers=d.numbers, source="t"))
    session.commit()


def test_backtest_job_runs_and_stores_the_result(api, loaded):
    r = api.post("/games/vn_mega_645/backtests", json={"seed": 1})
    assert r.status_code == 202, r.text
    accepted = r.json()
    assert accepted["status"] == "queued" and accepted["seed"] == 1

    body = api.get(f"/backtests/{accepted['id']}").json()  # the job already ran (sync background tasks)
    assert body["status"] == "done" and body["progress"] == 1.0 and body["error"] is None
    assert body["params"] == {
        "warmup": 30, "tickets": 5, "methods": ["hot", "cold", "mixed", "weighted", "random"],
        "weights": [40.0, 25.0, 20.0, 15.0], "mix": 0.5, "seed": 1, "draws_at_start": 122,
    }
    res = body["result"]
    assert res["tested_draws"] == 92 and res["history_draws"] == 122
    assert res["labels"] == list(range(1483, 1575))  # draw numbers 1483..1574 were tested
    assert res["expected_mean"] == pytest.approx(0.8)
    assert [m["method"] for m in res["methods"]] == ["hot", "cold", "mixed", "weighted", "random"]
    for m in res["methods"]:
        assert m["tickets"] == 460 and len(m["curve"]) == 92
        assert sum(m["histogram"].values()) == 460
        assert 0 <= m["p_value"] <= 1 and m["p_by_draw"] is not None
    assert res["verdict"]["kind"] in ("none_significant", "some_significant")
    assert "not probabilities of winning" in body["note"]
    assert body["finished_at"] is not None and body["game"] == "vn_mega_645"


def test_same_seed_same_result_and_default_seed_is_returned(api, loaded):
    a = api.post("/games/vn_mega_645/backtests", json={"seed": 5, "tickets": 2}).json()
    b = api.post("/games/vn_mega_645/backtests", json={"seed": 5, "tickets": 2}).json()
    ra = api.get(f"/backtests/{a['id']}").json()["result"]["methods"]
    rb = api.get(f"/backtests/{b['id']}").json()["result"]["methods"]
    assert ra == rb

    c = api.post("/games/vn_mega_645/backtests", json={"tickets": 2}).json()  # no seed: a fresh one
    assert isinstance(c["seed"], int) and 0 <= c["seed"] < 2**32
    assert api.get(f"/backtests/{c['id']}").json()["params"]["seed"] == c["seed"]


def test_subset_of_methods_and_custom_settings(api, loaded):
    r = api.post(
        "/games/vn_mega_645/backtests",
        json={"seed": 2, "warmup": 100, "tickets": 1, "methods": ["hot", "random", "hot"],
              "w10": 1, "w20": 1, "w50": 1, "w100": 1, "mix": 30},
    ).json()
    body = api.get(f"/backtests/{r['id']}").json()
    assert body["params"]["methods"] == ["hot", "random"]
    assert body["params"]["weights"] == [1, 1, 1, 1] and body["params"]["mix"] == pytest.approx(0.3)
    assert body["result"]["tested_draws"] == 22


@pytest.mark.parametrize(
    "body",
    [
        {"warmup": 5},
        {"warmup": 1001},
        {"tickets": 0},
        {"tickets": 51},
        {"methods": []},
        {"methods": ["lucky"]},
        {"mix": 101},
        {"w10": 0, "w20": 0, "w50": 0, "w100": 0},
        {"seed": -1},
        {"warmup": 120},  # leaves fewer than 5 draws to test
    ],
)
def test_bad_requests_are_rejected_up_front(api, loaded, body):
    assert api.post("/games/vn_mega_645/backtests", json=body).status_code == 422


def test_unknown_game_unknown_backtest_and_no_history(api):
    assert api.post("/games/nope/backtests", json={}).status_code == 404
    assert api.get("/backtests/999999").status_code == 404
    r = api.post("/games/vn_mega_645/backtests", json={})  # no draws stored yet
    assert r.status_code == 422 and "at least 35 draws" in r.json()["detail"]


def test_a_failing_job_is_recorded_not_lost(api, loaded, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("scoring exploded")

    monkeypatch.setattr(jobs, "run_backtest", boom)
    r = api.post("/games/vn_mega_645/backtests", json={"seed": 1}).json()
    body = api.get(f"/backtests/{r['id']}").json()
    assert body["status"] == "error"
    assert "RuntimeError: scoring exploded" in body["error"]
    assert body["result"] is None and body["finished_at"] is not None


def test_progress_is_reported_while_running(loaded, factory, session, monkeypatch):
    g = session.scalar(select(Game).where(Game.code == "vn_mega_645"))
    bt = Backtest(game_id=g.id, status="queued", progress=0.0, params={
        "warmup": 30, "tickets": 1, "methods": ["random"], "weights": [40, 25, 20, 15], "mix": 0.5,
        "seed": 3, "draws_at_start": 122,
    })
    session.add(bt)
    session.commit()

    observed = []
    real = jobs.run_backtest

    def spying(*args, progress=None, **kw):
        def wrapped(f):
            progress(f)
            with factory() as s:  # what a polling client would see right now
                observed.append(s.get(Backtest, bt.id).progress)
        return real(*args, progress=wrapped, **kw)

    monkeypatch.setattr(jobs, "PROGRESS_MIN_SECONDS", 0.0)
    monkeypatch.setattr(jobs, "run_backtest", spying)
    execute_backtest(factory, bt.id)

    assert observed == sorted(observed)  # never goes backwards
    # throttled to ~2% steps, so the first polls may still read 0, but the bar really moves
    assert observed[0] == 0.0 and any(0 < x < 1 for x in observed)
    assert len({round(x, 2) for x in observed}) > 5
    assert max(observed[:-1]) <= 0.999  # 1.0 is reserved for the finished state
    with factory() as s:
        done = s.get(Backtest, bt.id)
        assert (done.status, done.progress) == ("done", 1.0)


def test_only_queued_jobs_are_executed(loaded, factory, session):
    g = session.scalar(select(Game).where(Game.code == "vn_mega_645"))
    bt = Backtest(game_id=g.id, status="done", progress=1.0, params={}, result={"keep": True})
    session.add(bt)
    session.commit()
    execute_backtest(factory, bt.id)  # must not re-run or touch a finished job
    with factory() as s:
        assert s.get(Backtest, bt.id).result == {"keep": True}


def test_restart_recovery_fails_interrupted_jobs_instead_of_leaving_them_running(session):
    g = session.scalar(select(Game).where(Game.code == "vn_mega_645"))
    session.add_all([
        Backtest(game_id=g.id, status="queued", params={}),
        Backtest(game_id=g.id, status="running", progress=0.4, params={}),
        Backtest(game_id=g.id, status="done", progress=1.0, params={}, result={"ok": 1}),
        ImportLog(game_id=g.id, kind="collector", source="x", status="running"),
        ImportLog(game_id=g.id, kind="collector", source="x", status="ok"),
    ])
    session.commit()

    counts = recover_interrupted_jobs(session)
    session.commit()
    assert counts == {"backtests": 2, "import_logs": 1}
    statuses = sorted(b.status for b in session.scalars(select(Backtest)))
    assert statuses == ["done", "error", "error"]
    err = session.scalar(select(Backtest).where(Backtest.status == "error"))
    assert "restart" in err.error and isinstance(err.finished_at, dt.datetime)
    assert sorted(l.status for l in session.scalars(select(ImportLog))) == ["error", "ok"]
