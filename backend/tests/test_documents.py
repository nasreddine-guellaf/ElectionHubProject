import hashlib

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_models import AuthAudit
from app.object_storage import LocalObjectStorage, StorageError, safe_key
from app.phase5_models import ReportDocument
from tests.test_domain import (  # noqa: F401
    as_role,
    domain_client,
    domain_engine,
    draft,
    path,
    payload,
)

PDF = b"%PDF-1.4\n% synthetic ElectionHub document\n%%EOF\n"


@pytest.fixture
def document_client(domain_client, tmp_path):  # noqa: F811
    domain_client.app.state.object_storage = LocalObjectStorage(tmp_path / "private-objects")
    return domain_client


def upload(client, revision, content=PDF, media_type="application/pdf", name="pv-demo.pdf"):
    return client.post(
        path(revision) + "/documents",
        data={"expected_version": revision["edit_version"]},
        files={"file": (name, content, media_type)},
    )


def test_private_document_round_trip_and_metadata(document_client, domain_engine):  # noqa: F811
    revision = draft(document_client)
    response = upload(document_client, revision)
    assert response.status_code == 201, response.text
    document = response.json()
    assert document["original_filename"] == "pv-demo.pdf"
    assert document["storage_provider"] == "LOCAL"
    assert document["processing_status"] == "STORED"
    assert document["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert "object_key" not in document

    endpoint = path(revision) + "/documents"
    assert document_client.get(endpoint).json() == [document]
    download = document_client.get(endpoint + f"/{document['id']}/content")
    assert download.status_code == 200
    assert download.content == PDF
    assert download.headers["x-content-type-options"] == "nosniff"

    with Session(domain_engine) as session:
        stored = session.scalar(select(ReportDocument))
        assert stored.size_bytes == len(PDF)
        assert session.scalar(select(AuthAudit).where(AuthAudit.action == "DOCUMENT_UPLOADED"))


def test_document_delete_removes_private_object(document_client):
    revision = draft(document_client)
    document = upload(document_client, revision).json()
    endpoint = path(revision) + f"/documents/{document['id']}"
    assert document_client.delete(endpoint).status_code == 204
    assert document_client.get(path(revision) + "/documents").json() == []
    assert document_client.get(endpoint + "/content").status_code == 404


@pytest.mark.parametrize(
    ("content", "media_type", "expected"),
    [
        (b"plain text", "text/plain", 415),
        (b"not really a PDF", "application/pdf", 422),
        (b"", "application/pdf", 422),
    ],
)
def test_document_type_and_signature_validation(document_client, content, media_type, expected):
    revision = draft(document_client)
    assert upload(document_client, revision, content, media_type).status_code == expected
    assert document_client.get(path(revision) + "/documents").json() == []


def test_document_size_and_filename_are_controlled(document_client):
    document_client.app.state.settings.object_upload_max_bytes = 1024
    revision = draft(document_client)
    assert upload(document_client, revision, b"%PDF-" + b"x" * 1024).status_code == 413
    created = upload(document_client, revision, name='../../pv-été".pdf')
    assert created.status_code == 201
    filename = created.json()["original_filename"]
    assert filename.endswith(".pdf")
    assert not {"/", "\\", '"'}.intersection(filename)
    assert ".." not in filename and len(filename) <= 255


def test_document_permissions_and_immutable_submitted_revision(document_client):
    revision = draft(document_client)
    created = upload(document_client, revision).json()
    base = path(revision)

    del document_client.headers["Authorization"]
    assert document_client.get(base + "/documents").status_code == 401
    as_role(document_client, "VALIDATOR")
    assert upload(document_client, revision).status_code == 403

    as_role(document_client, "AGENT")
    assert document_client.put(base + "/results", json=payload()).status_code == 200
    submitted = document_client.post(base + "/submit", json={"expected_version": 2}).json()
    assert upload(document_client, submitted).status_code == 409
    assert document_client.delete(base + f"/documents/{created['id']}").status_code == 409

    as_role(document_client, "VALIDATOR")
    assert document_client.get(base + "/documents").status_code == 200
    assert document_client.get(base + f"/documents/{created['id']}/content").content == PDF


def test_historical_revision_keeps_its_document(document_client):
    revision = draft(document_client)
    document = upload(document_client, revision).json()
    base = path(revision)
    assert document_client.put(base + "/results", json=payload()).status_code == 200
    assert document_client.post(base + "/submit", json={"expected_version": 2}).status_code == 200
    corrected = document_client.post(
        base + "/revise",
        json={"expected_version": 3, "reason": "Correction fictive avec document conservé"},
    )
    assert corrected.status_code == 201
    assert document_client.get(base + f"/documents/{document['id']}/content").content == PDF


def test_safe_storage_key_rejects_traversal(tmp_path):
    with pytest.raises(StorageError):
        safe_key("../secret")
    storage = LocalObjectStorage(tmp_path)
    with pytest.raises(StorageError):
        storage.put("/absolute", b"x", "application/pdf", {})
