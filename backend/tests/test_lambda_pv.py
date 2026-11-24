import hashlib
import io
from contextlib import nullcontext
from uuid import uuid4

import pytest

from app import lambda_pv


class Body(io.BytesIO):
    pass


class FakeS3:
    def __init__(self, content: bytes, document_id):
        self.content = content
        self.document_id = document_id
        self.calls = []

    def get_object(self, **arguments):
        self.calls.append(arguments)
        return {
            "Body": Body(self.content),
            "Metadata": {"document-id": str(self.document_id)},
        }


class Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, document, duplicate=False):
        self.document = document
        self.duplicate = duplicate
        self.statements = []

    def execute(self, query, parameters=None):
        normalized = " ".join(query.split())
        self.statements.append((normalized, parameters))
        if normalized.startswith("SELECT 1 FROM object_events"):
            return Result({"?column?": 1} if self.duplicate else None)
        if normalized.startswith("SELECT id, object_key"):
            return Result(self.document)
        if normalized.startswith("INSERT INTO object_events"):
            return Result(None if self.duplicate else {"id": uuid4()})
        return Result(None)

    def transaction(self):
        return nullcontext()


def s3_record(bucket, key, *, sequencer="0001", version_id="version-1"):
    return {
        "eventSource": "aws:s3",
        "eventName": "ObjectCreated:Put",
        "s3": {
            "bucket": {"name": bucket},
            "object": {
                "key": key.replace("/", "%2F"),
                "sequencer": sequencer,
                "versionId": version_id,
            },
        },
    }


def fixture_data():
    document_id = uuid4()
    report_id = uuid4()
    content = b"%PDF-1.4\nElectionHub\n%%EOF\n"
    key = f"reports/{report_id}/revisions/1/{document_id}.pdf"
    document = {
        "id": document_id,
        "object_key": key,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    return document_id, content, key, document


def test_processes_valid_object_once():
    document_id, content, key, document = fixture_data()
    connection = FakeConnection(document)
    s3 = FakeS3(content, document_id)

    result = lambda_pv.process_record(
        s3_record("private-bucket", key), "private-bucket", s3, connection
    )

    assert result == "processed"
    assert s3.calls == [{"Bucket": "private-bucket", "Key": key, "VersionId": "version-1"}]
    assert any("processing_status = 'PROCESSED'" in sql for sql, _ in connection.statements)


def test_duplicate_event_does_not_download_or_update():
    document_id, content, key, document = fixture_data()
    connection = FakeConnection(document, duplicate=True)
    s3 = FakeS3(content, document_id)

    assert (
        lambda_pv.process_record(s3_record("private-bucket", key), "private-bucket", s3, connection)
        == "duplicate"
    )
    assert s3.calls == []
    assert not any(sql.startswith("UPDATE") for sql, _ in connection.statements)


@pytest.mark.parametrize("tamper", ["content", "metadata"])
def test_permanent_integrity_failure_is_recorded(tamper):
    document_id, content, key, document = fixture_data()
    s3 = FakeS3(content + (b"tampered" if tamper == "content" else b""), document_id)
    if tamper == "metadata":
        s3.document_id = uuid4()
    connection = FakeConnection(document)

    assert (
        lambda_pv.process_record(s3_record("private-bucket", key), "private-bucket", s3, connection)
        == "failed"
    )
    assert any("processing_status = 'FAILED'" in sql for sql, _ in connection.statements)


def test_missing_database_metadata_requests_retry():
    document_id, content, key, _ = fixture_data()
    with pytest.raises(lambda_pv.RetriableEventError):
        lambda_pv.process_record(
            s3_record("private-bucket", key),
            "private-bucket",
            FakeS3(content, document_id),
            FakeConnection(None),
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda row: row.update(eventSource="other"),
        lambda row: row.update(eventName="ObjectRemoved:Delete"),
        lambda row: row["s3"]["bucket"].update(name="wrong-bucket"),
        lambda row: row["s3"]["object"].update(key="reports%2Finvalid.pdf"),
    ],
)
def test_rejects_untrusted_event_shape(mutation):
    _, _, key, _ = fixture_data()
    record = s3_record("private-bucket", key)
    mutation(record)
    with pytest.raises(ValueError):
        lambda_pv.parse_record(record, "private-bucket")


def test_handler_counts_batch_results(monkeypatch):
    document_id, content, key, document = fixture_data()
    connection = FakeConnection(document)
    s3 = FakeS3(content, document_id)
    monkeypatch.setenv("S3_BUCKET", "private-bucket")
    monkeypatch.setenv("AWS_REGION", "eu-north-1")
    monkeypatch.setattr(lambda_pv, "database_connection", lambda: nullcontext(connection))
    monkeypatch.setattr(lambda_pv.boto3, "client", lambda *args, **kwargs: s3)

    result = lambda_pv.lambda_handler({"Records": [s3_record("private-bucket", key)]}, None)

    assert result == {"processed": 1, "duplicate": 0, "failed": 0}
