import uuid

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.config import ROOT
from app.models import PollingStation
from app.seed import seed_stations
from tests.conftest import alembic_config


def test_first_seed_reports_inserted_count(db_engine):
    with Session(db_engine) as session, session.begin():
        assert seed_stations(session, ROOT / "database/seeds/polling_stations.json") == 3


def test_seed_is_idempotent_and_preserves_existing_records(seeded_engine):
    with Session(seeded_engine) as session, session.begin():
        station = session.scalar(select(PollingStation).where(PollingStation.code == "DEMO-BV-001"))
        station.name = "Bureau fictif renommé"
    with Session(seeded_engine) as session, session.begin():
        assert seed_stations(session, ROOT / "database/seeds/polling_stations.json") == 0
        assert session.scalar(select(func.count()).select_from(PollingStation)) == 3
        station = session.scalar(select(PollingStation).where(PollingStation.code == "DEMO-BV-001"))
        assert station.name == "Bureau fictif renommé"


@pytest.mark.parametrize(
    "overrides",
    [
        {"registered_voters": -1},
        {"code": "DEMO-BV-001"},
        {"code": "  "},
        {"name": "  "},
    ],
)
def test_postgres_rejects_invalid_station(seeded_engine, overrides):
    values = {"id": uuid.uuid4(), "code": "DEMO-TEST", "name": "Fictif", "registered_voters": 10}
    values.update(overrides)
    with Session(seeded_engine) as session, pytest.raises(IntegrityError):
        with session.begin():
            session.add(PollingStation(**values))
            session.flush()


def test_migration_matches_models_and_round_trips(db_engine):
    with db_engine.begin() as connection:
        config = alembic_config(connection)
        command.check(config)
        command.downgrade(config, "base")
        assert "polling_stations" not in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        assert "polling_stations" in inspect(connection).get_table_names()
        command.check(config)
