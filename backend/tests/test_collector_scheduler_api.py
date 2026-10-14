import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.api.collect import fetcher_factory_dep, session_factory_dep
from app.collectors.factory import game_lock
from app.config import Settings
from app.db import get_session
from app.main import create_app
from app.models import Draw, Game, ImportLog
from app.scheduler import MAX_ATTEMPTS, build_scheduler, scheduled_collect
from tests.fakesite import FakeSite, load_seed

SEED = load_seed()
VN = ZoneInfo("Asia/Ho_Chi_Minh")


class StubScheduler:
    def __init__(self):
        self.jobs = []

    def add_job(self, func, trigger, **kw):
        self.jobs.append((func, trigger, kw))


@pytest.fixture
def factory(engine, session):
    return sessionmaker(bind=engine, expire_on_commit=False)


def store(session, draws, tamper=None):
    g = session.scalar(select(Game).where(Game.code == "vn_mega_645"))
    for d in draws:
        session.add(Draw(game_id=g.id, draw_no=d.draw_no, draw_date=d.date,
                         numbers=sorted((tamper or {}).get(d.draw_no, d.numbers)), source="test"))
    session.commit()


# ---------- scheduler ----------


def test_build_scheduler_fires_wed_fri_sun_at_21h_vietnam_time():
    sched = build_scheduler(sessionmaker(), Settings(), fetcher_factory=lambda: None)
    job = sched.get_job("collect-vn_mega_645")
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["day_of_week"] == "wed,fri,sun"
    assert (fields["hour"], fields["minute"]) == ("21", "0")
    assert str(job.trigger.timezone) == "Asia/Ho_Chi_Minh"
    nxt = job.trigger.get_next_fire_time(None, dt.datetime(2026, 10, 13, 12, 0, tzinfo=VN))
    assert (nxt.date(), nxt.hour, nxt.strftime("%a")) == (dt.date(2026, 10, 14), 21, "Wed")


def test_scheduled_run_published_draw_is_done(session, factory):
    store(session, [d for d in SEED if d.draw_no <= 1573])
    now = dt.datetime(2026, 10, 11, 21, 0, tzinfo=VN)  # Sunday 21:00, draw 1574 is out
    stub = StubScheduler()
    out = scheduled_collect(factory, "vn_mega_645", 1, scheduler=stub,
                            fetcher_factory=lambda: FakeSite(SEED).fetcher(), now=now)
    assert out == "done" and stub.jobs == []
    assert session.scalar(select(Draw).where(Draw.draw_no == 1574)) is not None


def test_scheduled_run_retries_hourly_until_the_draw_appears(session, factory):
    store(session, SEED)  # the site has nothing for Wed 14 Oct yet
    now = dt.datetime(2026, 10, 14, 21, 0, tzinfo=VN)
    stub = StubScheduler()
    out = scheduled_collect(factory, "vn_mega_645", 1, scheduler=stub,
                            fetcher_factory=lambda: FakeSite(SEED).fetcher(), now=now)
    assert out == "retry"
    (func, trigger, kw), = stub.jobs
    assert trigger.run_date == now + dt.timedelta(hours=1)
    assert kw["args"][2] == 2  # next attempt number


def test_scheduled_run_gives_up_after_max_attempts(session, factory):
    store(session, SEED)
    now = dt.datetime(2026, 10, 14, 21, 0, tzinfo=VN)
    stub = StubScheduler()
    out = scheduled_collect(factory, "vn_mega_645", MAX_ATTEMPTS, scheduler=stub,
                            fetcher_factory=lambda: FakeSite(SEED).fetcher(), now=now)
    assert out == "gave_up" and stub.jobs == []


def test_conflict_is_not_retried(session, factory):
    store(session, [d for d in SEED if d.draw_no <= 1573], tamper={1570: [1, 2, 3, 4, 5, 6]})
    now = dt.datetime(2026, 10, 11, 21, 0, tzinfo=VN)
    stub = StubScheduler()
    out = scheduled_collect(factory, "vn_mega_645", 1, scheduler=stub,
                            fetcher_factory=lambda: FakeSite(SEED).fetcher(), now=now)
    assert out == "conflict" and stub.jobs == []


def test_scheduled_run_skips_when_another_run_holds_the_lock(session, factory):
    lock = game_lock("vn_mega_645")
    assert lock.acquire(blocking=False)
    try:
        out = scheduled_collect(factory, "vn_mega_645", 1, fetcher_factory=lambda: FakeSite(SEED).fetcher())
        assert out == "busy"
    finally:
        lock.release()


# ---------- REST API ----------


@pytest.fixture
def api(session, factory):
    app = create_app()
    site = FakeSite(SEED)

    def _session():  # a fresh session per request, like production
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[session_factory_dep] = lambda: factory
    app.dependency_overrides[fetcher_factory_dep] = lambda: (lambda: site.fetcher())
    return TestClient(app), site


def test_manual_collect_fills_gaps_and_logs(session, api):
    client, site = api
    gap = set(range(1479, 1543)) | {1571}
    store(session, [d for d in SEED if d.draw_no not in gap])

    r = client.post("/games/vn_mega_645/collect", json={"mode": "gaps"})
    assert r.status_code == 202 and r.json()["status"] == "running"

    logs = client.get("/collect/logs", params={"game": "vn_mega_645"}).json()
    top = logs[0]
    assert top["id"] == r.json()["log_id"]
    assert (top["status"], top["added"], top["kind"]) == ("ok", 65, "collector")
    assert top["detail"]["missing_after"] == []
    assert client.get("/games/vn_mega_645/draws/missing").json()["missing"] == []


def test_manual_collect_conflict_is_listed_for_review(session, api):
    client, _ = api
    store(session, [d for d in SEED if d.draw_no != 1571], tamper={1569: [1, 2, 3, 4, 5, 6]})
    assert client.post("/games/vn_mega_645/collect", json={"mode": "gaps"}).status_code == 202
    top = client.get("/collect/logs").json()[0]
    assert (top["status"], top["added"], top["conflicts"]) == ("conflict", 0, 1)
    conflicts = client.get("/games/vn_mega_645/conflicts").json()
    assert [(c["draw_no"], c["existing_numbers"]) for c in conflicts] == [(1569, [1, 2, 3, 4, 5, 6])]
    assert conflicts[0]["incoming_numbers"] == [2, 9, 24, 27, 30, 33]


def test_collect_default_body_and_unknown_or_unsupported_game(session, api):
    client, _ = api
    store(session, SEED)
    assert client.post("/games/vn_mega_645/collect").status_code == 202  # body is optional
    assert client.post("/games/nope/collect").status_code == 404
    r = client.post("/games/vn_power_655/collect")
    assert r.status_code == 501 and "file import" in r.json()["detail"]


def test_collect_rejects_concurrent_runs(session, api):
    client, _ = api
    lock = game_lock("vn_mega_645")
    assert lock.acquire(blocking=False)
    try:
        assert client.post("/games/vn_mega_645/collect").status_code == 409
    finally:
        lock.release()


def test_collect_never_leaves_a_log_stuck_on_running(session, api):
    client, site = api
    store(session, SEED)
    site.down = True
    client.post("/games/vn_mega_645/collect", json={"mode": "latest"})
    log = session.scalar(select(ImportLog).order_by(ImportLog.id.desc()))
    session.refresh(log)
    assert log.status == "unreachable"
    assert not game_lock("vn_mega_645").locked()
