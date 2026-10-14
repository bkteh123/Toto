import os
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.db import get_session  # noqa: E402
from app.games import seed_presets  # noqa: E402
from app.main import create_app  # noqa: E402
from app.validation import GameSpec  # noqa: E402

MEGA = GameSpec(code="vn_mega_645", n=45, k=6, ticket_price=10000, currency="VND", name="Vietlott Mega 6/45")
POWER = GameSpec(code="vn_power_655", n=55, k=6, has_bonus=True, bonus_max=55)
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def pg_url(tmp_path_factory):
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        yield url
        return
    try:
        import pgserver
    except ImportError:  # pragma: no cover
        pytest.skip("set TEST_DATABASE_URL or `pip install pgserver` to run database tests")
    srv = pgserver.get_server(tmp_path_factory.mktemp("pg") / "data", cleanup_mode="stop")
    yield srv.get_uri().replace("postgresql://", "postgresql+psycopg://")
    srv.cleanup()


@pytest.fixture(scope="session")
def engine(pg_url):
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", pg_url)
    command.upgrade(cfg, "head")  # exercises the real migrations
    eng = create_engine(pg_url)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    with engine.begin() as conn:
        conn.execute(
            text("TRUNCATE draw_conflicts, import_logs, backtests, draws, games RESTART IDENTITY CASCADE")
        )
    with Session(engine, expire_on_commit=False) as s:
        seed_presets(s)
        s.commit()
        yield s


@pytest.fixture
def client(session):
    app = create_app()

    def _session():
        yield session

    app.dependency_overrides[get_session] = _session
    return TestClient(app)  # no `with`: lifespan (default-DB seeding) is intentionally skipped
