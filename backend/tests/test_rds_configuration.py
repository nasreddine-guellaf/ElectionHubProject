from pathlib import Path

import certifi

from app import database
from app.config import Settings


def test_engine_forwards_verified_tls_and_bounded_pool(monkeypatch):
    captured = {}
    sentinel = object()

    def fake_create_engine(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(database, "create_engine", fake_create_engine)
    settings = Settings(
        _env_file=None,
        app_env="cloud",
        postgres_password="test-only-long-password",
        postgres_host="electionhub.example.eu-north-1.rds.amazonaws.com",
        postgres_sslmode="verify-full",
        postgres_sslrootcert=certifi.where(),
        postgres_connect_timeout_seconds=7,
        postgres_pool_size=4,
        postgres_max_overflow=2,
        postgres_pool_timeout_seconds=9,
        postgres_pool_recycle_seconds=240,
    )

    assert database.create_db_engine(settings) is sentinel
    assert captured["url"] == settings.database_url
    assert captured["pool_pre_ping"] is True
    assert captured["pool_size"] == 4
    assert captured["max_overflow"] == 2
    assert captured["pool_timeout"] == 9
    assert captured["pool_recycle"] == 240
    assert captured["hide_parameters"] is True
    assert captured["connect_args"] == {
        "connect_timeout": 7,
        "sslmode": "verify-full",
        "sslrootcert": str(Path(certifi.where()).resolve()),
    }


def test_local_engine_preserves_non_tls_postgres_workflow(monkeypatch):
    captured = {}

    def fake_create_engine(_url, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(database, "create_engine", fake_create_engine)
    settings = Settings(_env_file=None, postgres_password="test-only-long-password")

    database.create_db_engine(settings)

    assert captured["connect_args"] == {
        "connect_timeout": 3,
        "sslmode": "disable",
    }
    assert captured["pool_size"] == 5
    assert captured["max_overflow"] == 5
