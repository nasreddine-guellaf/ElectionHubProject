import hashlib
import io
import json
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

import pytest

from app import lambda_pv, lambda_pv_demo


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
            assert normalized.endswith("RETURNING provider_event_id")
            return Result(None if self.duplicate else {"provider_event_id": parameters[1]})
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


def test_insert_conflict_wins_over_the_initial_duplicate_check(monkeypatch):
    document_id, content, key, document = fixture_data()
    connection = FakeConnection(document)
    execute = connection.execute

    def race(query, parameters=None):
        if query.lstrip().startswith("INSERT INTO object_events"):
            connection.duplicate = True
        return execute(query, parameters)

    monkeypatch.setattr(connection, "execute", race)
    assert (
        lambda_pv.process_record(
            s3_record("private-bucket", key),
            "private-bucket",
            FakeS3(content, document_id),
            connection,
        )
        == "duplicate"
    )
    assert not any(sql.startswith("UPDATE") for sql, _ in connection.statements)


@pytest.mark.parametrize("tamper", ["content", "metadata", "digest"])
def test_permanent_integrity_failure_is_recorded(tamper):
    document_id, content, key, document = fixture_data()
    s3 = FakeS3(content + (b"tampered" if tamper == "content" else b""), document_id)
    if tamper == "metadata":
        s3.document_id = uuid4()
    if tamper == "digest":
        s3.content = b"X" + content[1:]
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


def test_missing_object_metadata_is_an_integrity_failure():
    _, content, key, document = fixture_data()
    s3 = FakeS3(content, document_id=None)
    body = Body(content)
    s3.get_object = lambda **kwargs: {"Body": body}
    connection = FakeConnection(document)
    assert (
        lambda_pv.process_record(s3_record("private-bucket", key), "private-bucket", s3, connection)
        == "failed"
    )
    assert body.closed
    assert any("processing_status = 'FAILED'" in sql for sql, _ in connection.statements)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda row: row.update(eventSource="other"),
        lambda row: row.update(eventName="ObjectRemoved:Delete"),
        lambda row: row["s3"]["bucket"].update(name="wrong-bucket"),
        lambda row: row["s3"]["object"].update(key="reports%2Finvalid.pdf"),
        lambda row: row.update(s3=[]),
        lambda row: row["s3"].update(bucket=True),
        lambda row: row["s3"].update(object="invalid"),
        lambda row: row["s3"]["object"].pop("sequencer"),
        lambda row: row["s3"]["object"].update(versionId=[]),
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


@pytest.mark.parametrize("event", [None, {}, {"Records": []}, {"Records": [None]}])
def test_malformed_batches_are_rejected_before_creating_clients(monkeypatch, event):
    monkeypatch.setenv("S3_BUCKET", "private-bucket")
    monkeypatch.setattr(lambda_pv.boto3, "client", lambda *args, **kw: pytest.fail("client called"))
    with pytest.raises(ValueError):
        lambda_pv.lambda_handler(event, None)


def test_unversioned_s3_reads_omit_version_parameter():
    document_id, content, key, document = fixture_data()
    s3 = FakeS3(content, document_id)
    record = s3_record("private-bucket", key, version_id=None)
    assert lambda_pv.process_record(record, "private-bucket", s3, FakeConnection(document)) == (
        "processed"
    )
    assert s3.calls == [{"Bucket": "private-bucket", "Key": key}]
    assert (
        lambda_pv.parse_record(record, "private-bucket").event_id
        != lambda_pv.parse_record(s3_record("private-bucket", key), "private-bucket").event_id
    )


def test_retry_after_metadata_and_s3_failures(monkeypatch):
    document_id, content, key, document = fixture_data()
    connection = FakeConnection(None)
    s3 = FakeS3(content, document_id)
    get_object = s3.get_object
    record = s3_record("private-bucket", key)

    with pytest.raises(lambda_pv.RetriableEventError):
        lambda_pv.process_record(record, "private-bucket", s3, connection)
    assert s3.calls == []

    def unavailable(**arguments):
        raise TimeoutError("synthetic S3 failure")

    connection.document = document
    monkeypatch.setattr(s3, "get_object", unavailable)
    with pytest.raises(TimeoutError):
        lambda_pv.process_record(record, "private-bucket", s3, connection)
    assert not any(sql.startswith("INSERT") for sql, _ in connection.statements)

    monkeypatch.setattr(s3, "get_object", get_object)
    assert lambda_pv.process_record(record, "private-bucket", s3, connection) == "processed"


def test_synthetic_smoke_counts_duplicate_delivery():
    fixture = Path(__file__).resolve().parents[2] / "infra/aws-account-b/events/pv.json"
    event = json.loads(fixture.read_text(encoding="utf-8"))
    assert lambda_pv_demo.lambda_handler(event, None) == {
        "processed": 1,
        "duplicate": 1,
        "failed": 0,
    }


@pytest.mark.parametrize("bucket", ["private-bucket", "other-bucket"])
def test_s3_destination_probe_never_opens_dependencies(monkeypatch, bucket):
    event = {"Service": "Amazon S3", "Event": "s3:TestEvent", "Bucket": bucket}
    monkeypatch.setenv("S3_BUCKET", "private-bucket")

    def unexpected_call(*args, **kwargs):
        pytest.fail("S3 test notification opened a dependency")

    monkeypatch.setattr(lambda_pv.boto3, "client", unexpected_call)
    monkeypatch.setattr(lambda_pv, "database_connection", unexpected_call)
    if bucket == "private-bucket":
        assert lambda_pv.lambda_handler(event, None) == {
            "processed": 0,
            "duplicate": 0,
            "failed": 0,
        }
    else:
        with pytest.raises(ValueError, match="Unexpected S3 test event"):
            lambda_pv.lambda_handler(event, None)
