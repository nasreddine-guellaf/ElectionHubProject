import hashlib

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth_models import AuthAudit
from app.object_storage import LocalObjectStorage
from app.phase5_models import IncidentAttachment, ReportIncident
from tests.test_domain import (  # noqa: F401
    as_role,
    domain_client,
    domain_engine,
    draft,
    path,
    payload,
)

JPEG = b"\xff\xd8\xff\xe0" + b"synthetic ElectionHub incident photo"


@pytest.fixture
def incident_client(domain_client, tmp_path):  # noqa: F811
    domain_client.app.state.object_storage = LocalObjectStorage(tmp_path / "private-objects")
    return domain_client


def create_incident(client, revision, category="MATERIAL", description=None):
    return client.post(
        path(revision) + "/incidents",
        json={
            "expected_version": revision["edit_version"],
            "category": category,
            "description": description or "Urne fictive endommagée pendant la préparation.",
        },
    )


def upload_photo(client, revision, incident_id, content=JPEG, media_type="image/jpeg"):
    return client.post(
        path(revision) + f"/incidents/{incident_id}/attachments",
        data={"expected_version": revision["edit_version"]},
        files={"file": ("incident-demo.jpg", content, media_type)},
    )


def test_incident_photo_round_trip_and_audit(incident_client, domain_engine):  # noqa: F811
    revision = draft(incident_client)
    created = create_incident(incident_client, revision)
    assert created.status_code == 201, created.text
    incident = created.json()
    assert incident["category"] == "MATERIAL"
    assert incident["attachments"] == []

    uploaded = upload_photo(incident_client, revision, incident["id"])
    assert uploaded.status_code == 201, uploaded.text
    photo = uploaded.json()
    assert photo["sha256"] == hashlib.sha256(JPEG).hexdigest()
    assert photo["storage_provider"] == "LOCAL"
    assert "object_key" not in photo

    endpoint = path(revision) + f"/incidents/{incident['id']}/attachments/{photo['id']}"
    download = incident_client.get(endpoint + "/content")
    assert download.status_code == 200
    assert download.content == JPEG
    assert download.headers["x-content-type-options"] == "nosniff"

    listed = incident_client.get(path(revision) + "/incidents").json()
    assert listed[0]["attachments"] == [photo]
    with Session(domain_engine) as session:
        assert session.scalar(select(func.count()).select_from(ReportIncident)) == 1
        assert session.scalar(select(func.count()).select_from(IncidentAttachment)) == 1
        actions = set(session.scalars(select(AuthAudit.action)).all())
        assert {"INCIDENT_REPORTED", "INCIDENT_PHOTO_UPLOADED"} <= actions


def test_incident_photo_delete_removes_private_object(incident_client):
    revision = draft(incident_client)
    incident = create_incident(incident_client, revision).json()
    photo = upload_photo(incident_client, revision, incident["id"]).json()
    endpoint = path(revision) + f"/incidents/{incident['id']}/attachments/{photo['id']}"

    assert incident_client.delete(endpoint).status_code == 204
    assert incident_client.get(endpoint + "/content").status_code == 404
    assert incident_client.get(path(revision) + "/incidents").json()[0]["attachments"] == []


@pytest.mark.parametrize(
    ("content", "media_type", "expected"),
    [
        (b"%PDF-1.4", "application/pdf", 415),
        (b"not a jpeg", "image/jpeg", 422),
        (b"", "image/png", 422),
    ],
)
def test_incident_photo_type_and_signature_validation(
    incident_client, content, media_type, expected
):
    revision = draft(incident_client)
    incident = create_incident(incident_client, revision).json()
    assert (
        upload_photo(incident_client, revision, incident["id"], content, media_type).status_code
        == expected
    )
    assert incident_client.get(path(revision) + "/incidents").json()[0]["attachments"] == []


def test_incident_inputs_size_and_stale_version_are_controlled(incident_client):
    revision = draft(incident_client)
    assert create_incident(incident_client, revision, description="court").status_code == 422
    assert create_incident(incident_client, revision, category="REAL_EVENT").status_code == 422
    stale = {**revision, "edit_version": revision["edit_version"] + 1}
    assert create_incident(incident_client, stale).status_code == 409

    incident = create_incident(incident_client, revision).json()
    incident_client.app.state.settings.object_upload_max_bytes = 1024
    oversized = b"\xff\xd8\xff" + b"x" * 1024
    assert upload_photo(incident_client, revision, incident["id"], oversized).status_code == 413


def test_incidents_follow_report_permissions_and_become_immutable(incident_client):
    revision = draft(incident_client)
    incident = create_incident(incident_client, revision).json()
    photo = upload_photo(incident_client, revision, incident["id"]).json()
    base = path(revision)

    del incident_client.headers["Authorization"]
    assert incident_client.get(base + "/incidents").status_code == 401
    as_role(incident_client, "VALIDATOR")
    assert incident_client.get(base + "/incidents").status_code == 404
    assert create_incident(incident_client, revision).status_code == 403

    as_role(incident_client, "AGENT")
    assert incident_client.put(base + "/results", json=payload()).status_code == 200
    submitted = incident_client.post(base + "/submit", json={"expected_version": 2}).json()
    assert create_incident(incident_client, submitted).status_code == 409
    assert upload_photo(incident_client, submitted, incident["id"]).status_code == 409
    endpoint = base + f"/incidents/{incident['id']}/attachments/{photo['id']}"
    assert incident_client.delete(endpoint).status_code == 409

    as_role(incident_client, "VALIDATOR")
    assert incident_client.get(base + "/incidents").status_code == 200
    assert incident_client.get(endpoint + "/content").content == JPEG
