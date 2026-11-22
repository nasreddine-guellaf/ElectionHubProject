from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_models import AuthAudit
from app.domain_models import ElectionStation
from tests.test_domain import ELECTION, STATION, as_role
from tests.test_domain import domain_client as domain_client
from tests.test_domain import domain_engine as domain_engine


@pytest.mark.parametrize("role", ["AGENT", "VALIDATOR"])
def test_station_writes_require_admin(domain_client, role):
    as_role(domain_client, role)
    payload = {"code": "DEMO-BV-NEW", "name": "Bureau fictif", "registered_voters": 100}
    assert domain_client.post("/api/v1/polling-stations", json=payload).status_code == 403
    assert domain_client.put(f"/api/v1/polling-stations/{STATION}", json=payload).status_code == 403
    assert domain_client.delete(f"/api/v1/polling-stations/{STATION}").status_code == 403


def test_admin_station_lifecycle_and_audit(domain_client, domain_engine):
    as_role(domain_client, "ADMIN")
    payload = {"code": "DEMO-BV-NEW", "name": "Bureau fictif", "registered_voters": 100}
    response = domain_client.post("/api/v1/polling-stations", json=payload)
    assert response.status_code == 201
    station_id = response.json()["id"]
    assert domain_client.post("/api/v1/polling-stations", json=payload).status_code == 409
    payload["name"] = "Bureau fictif renommé"
    assert (
        domain_client.put(f"/api/v1/polling-stations/{station_id}", json=payload).status_code == 200
    )
    assert (
        domain_client.get(f"/api/v1/polling-stations/{station_id}").json()["name"]
        == payload["name"]
    )
    assert domain_client.delete(f"/api/v1/polling-stations/{station_id}").status_code == 204
    assert domain_client.get(f"/api/v1/polling-stations/{station_id}").status_code == 404
    with Session(domain_engine) as session:
        actions = set(
            session.scalars(select(AuthAudit.action).where(AuthAudit.resource == station_id))
        )
        assert actions == {"STATION_CREATED", "STATION_UPDATED", "STATION_DELETED"}


def test_station_validation_and_election_snapshot_preserved(domain_client, domain_engine):
    as_role(domain_client, "ADMIN")
    payload = {"code": "DEMO-BV-001", "name": "Bureau fictif renommé", "registered_voters": 123}
    assert domain_client.put(f"/api/v1/polling-stations/{STATION}", json=payload).status_code == 200
    with Session(domain_engine) as session:
        assert (
            session.get(ElectionStation, (UUID(ELECTION), UUID(STATION))).registered_voters == 600
        )
    assert domain_client.delete(f"/api/v1/polling-stations/{STATION}").status_code == 409
    payload["registered_voters"] = -1
    assert domain_client.post("/api/v1/polling-stations", json=payload).status_code == 422
    payload["registered_voters"] = 100
    payload["code"] = "REAL-DATA"
    assert domain_client.post("/api/v1/polling-stations", json=payload).status_code == 422
