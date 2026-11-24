import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config import Settings
from app.database import get_session
from app.main import create_app
from app.schemas import HealthRead


def test_health_checks_database_and_migration(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "schema_version": "0005_incidents",
        "environment": "test",
    }


def test_health_response_accepts_cloud_environment():
    response = HealthRead(schema_version="0005_incidents", environment="cloud")
    assert response.model_dump()["environment"] == "cloud"


def test_health_reports_cloud_environment(client):
    # Régression SEC-02 : en APP_ENV=cloud, /health ne doit pas échouer à la validation
    # de sa réponse (sinon le load balancer GCP verrait toutes les instances en panne).
    client.app.state.settings.app_env = "cloud"
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["environment"] == "cloud"


def test_list_returns_seeded_postgres_records(client):
    response = client.get("/api/v1/polling-stations")
    assert response.status_code == 200
    body = response.json()
    assert body["data_kind"] == "synthetic"
    assert body["total"] == 3
    assert [row["code"] for row in body["items"]] == ["DEMO-BV-001", "DEMO-BV-002", "DEMO-BV-003"]
    assert body["items"][0]["registered_voters"] == 600
    assert body["items"][0]["created_at"]


def test_pagination_and_detail(client):
    body = client.get("/api/v1/polling-stations?limit=1&offset=1").json()
    assert body["total"] == 3
    assert len(body["items"]) == 1
    assert body["items"][0]["code"] == "DEMO-BV-002"
    station = body["items"][0]
    assert client.get(f"/api/v1/polling-stations/{station['id']}").json() == station
    assert client.get("/api/v1/polling-stations?offset=10").json()["items"] == []


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "limit=abc"])
def test_invalid_pagination(client, query):
    assert client.get(f"/api/v1/polling-stations?{query}").status_code == 422


def test_missing_and_invalid_station(client):
    assert client.get(f"/api/v1/polling-stations/{uuid.uuid4()}").status_code == 404
    assert client.get("/api/v1/polling-stations/invalid").status_code == 422


def test_empty_database(db_engine):
    with TestClient(create_app(Settings(app_env="test"), engine=db_engine)) as client:
        assert client.get("/api/v1/polling-stations").json()["total"] == 0


def test_missing_schema_is_not_healthy(client, seeded_engine):
    with seeded_engine.begin() as connection:
        connection.execute(text("ALTER TABLE polling_stations RENAME TO unavailable_stations"))
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"detail": "Base de données indisponible."}


def test_wrong_migration_is_not_healthy(client, seeded_engine):
    with seeded_engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'obsolete'"))
    assert client.get("/health").status_code == 503


def test_database_failure_is_sanitized(client):
    def unavailable():
        raise OperationalError("secret SQL", {}, Exception("private-password"))

    client.app.dependency_overrides[get_session] = unavailable
    for path in ("/health", "/api/v1/polling-stations"):
        response = client.get(path)
        assert response.status_code == 503
        assert response.json() == {"detail": "Base de données indisponible."}
        assert "private-password" not in response.text
