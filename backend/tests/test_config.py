import pytest

from app.config import Settings


@pytest.mark.parametrize(
    "given, expected",
    [
        ("postgresql://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("postgres://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("postgresql+psycopg://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("sqlite://", "sqlite://"),
    ],
)
def test_database_url_gets_the_psycopg_driver(given, expected, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", given)
    assert Settings(_env_file=None).database_url == expected
