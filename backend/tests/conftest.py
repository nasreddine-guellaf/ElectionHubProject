import uuid

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from alembic import command
from app.config import ROOT, Settings
from app.database import create_db_engine
from app.main import create_app
from app.seed import seed_stations


def alembic_config(connection) -> Config:
    config = Config(str(ROOT / "backend/alembic.ini"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture
def db_engine():
    settings = Settings(app_env="test")
    admin_engine = create_db_engine(settings)
    # Identifiant généré, jamais fourni par l'utilisateur. Aucun DROP de base existante.
    schema = f"test_{uuid.uuid4().hex}"
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    except SQLAlchemyError:
        admin_engine.dispose()
        pytest.fail(
            "PostgreSQL indisponible : démarrer docker compose up -d --wait db.", pytrace=False
        )
    engine = create_engine(
        settings.database_url,
        connect_args={"options": f"-csearch_path={schema}", "connect_timeout": 3},
        hide_parameters=True,
    )
    try:
        with engine.begin() as connection:
            command.upgrade(alembic_config(connection), "head")
        yield engine
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


@pytest.fixture
def seeded_engine(db_engine):
    with Session(db_engine) as session, session.begin():
        seed_stations(session, ROOT / "database/seeds/polling_stations.json")
    return db_engine


@pytest.fixture
def client(seeded_engine):
    with TestClient(create_app(Settings(app_env="test"), engine=seeded_engine)) as client:
        yield client
