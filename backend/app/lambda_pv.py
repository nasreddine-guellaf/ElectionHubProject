"""Idempotent S3 ObjectCreated processor for private PV documents.

The Lambda uses RDS IAM authentication and never receives a database password.
It validates the immutable object against metadata already committed by the API,
then records the provider event and processing result in one database transaction.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus
from uuid import UUID, uuid4

import boto3
import psycopg
from psycopg.rows import dict_row

OBJECT_KEY = re.compile(
    r"^reports/(?P<report>[0-9a-f-]{36})/revisions/(?P<revision>[1-9][0-9]*)/"
    r"(?P<document>[0-9a-f-]{36})\.(?:pdf|png|jpg)$"
)
DATABASE_USER = re.compile(r"^[a-z][a-z0-9_]{2,30}$")


class RetriableEventError(RuntimeError):
    """Transient ordering or provider failure that AWS should retry."""


@dataclass(frozen=True)
class ObjectCreated:
    event_id: str
    event_name: str
    bucket: str
    key: str
    version_id: str | None
    document_id: UUID


def required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def parse_record(record: dict[str, Any], expected_bucket: str) -> ObjectCreated:
    if record.get("eventSource") != "aws:s3":
        raise ValueError("Only aws:s3 events are accepted")
    event_name = str(record.get("eventName", ""))
    if not event_name.startswith("ObjectCreated:"):
        raise ValueError("Only ObjectCreated events are accepted")

    s3 = record.get("s3") or {}
    bucket = str((s3.get("bucket") or {}).get("name", ""))
    object_data = s3.get("object") or {}
    key = unquote_plus(str(object_data.get("key", "")))
    if bucket != expected_bucket:
        raise ValueError("Unexpected S3 bucket")
    match = OBJECT_KEY.fullmatch(key)
    if match is None:
        raise ValueError("Unexpected S3 object key")

    document_id = UUID(match.group("document"))
    # S3 event notifications do not expose one universal event UUID. The
    # sequencer and version identify one mutation; hashing keeps the DB key short.
    identity = {
        "bucket": bucket,
        "event": event_name,
        "key": key,
        "sequencer": object_data.get("sequencer"),
        "version": object_data.get("versionId"),
    }
    event_id = (
        "s3:"
        + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    return ObjectCreated(
        event_id=event_id,
        event_name=event_name,
        bucket=bucket,
        key=key,
        version_id=object_data.get("versionId"),
        document_id=document_id,
    )


def object_digest(s3_client, event: ObjectCreated) -> tuple[int, str, dict[str, str]]:
    arguments = {"Bucket": event.bucket, "Key": event.key}
    if event.version_id:
        arguments["VersionId"] = event.version_id
    response = s3_client.get_object(**arguments)
    body = response["Body"]
    digest = hashlib.sha256()
    size = 0
    try:
        while chunk := body.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    finally:
        body.close()
    return size, digest.hexdigest(), response.get("Metadata", {})


def event_already_processed(connection, event_id: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM object_events WHERE provider_event_id = %s",
        (event_id,),
    ).fetchone()
    return row is not None


def load_document(connection, event: ObjectCreated) -> dict[str, Any]:
    document = connection.execute(
        """
        SELECT id, object_key, size_bytes, sha256
        FROM report_documents
        WHERE id = %s AND object_key = %s
        """,
        (event.document_id, event.key),
    ).fetchone()
    if document is None:
        # S3 can notify before the API transaction becomes visible. Retrying is
        # safer than permanently discarding a valid event.
        raise RetriableEventError("Document metadata is not committed yet")
    return document


def validation_failure(
    document: dict[str, Any],
    event: ObjectCreated,
    actual_size: int,
    actual_sha256: str,
    metadata: dict[str, str],
) -> str | None:
    if metadata.get("document-id") != str(event.document_id):
        return "S3 document metadata does not match the object key"
    if actual_size != document["size_bytes"]:
        return "S3 object size does not match PostgreSQL metadata"
    if actual_sha256 != document["sha256"]:
        return "S3 object digest does not match PostgreSQL metadata"
    return None


def persist_result(connection, event: ObjectCreated, failure: str | None) -> str:
    with connection.transaction():
        inserted = connection.execute(
            """
            INSERT INTO object_events (id, provider_event_id, document_id, event_name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (provider_event_id) DO NOTHING
            RETURNING id
            """,
            (uuid4(), event.event_id, event.document_id, event.event_name),
        ).fetchone()
        if inserted is None:
            return "duplicate"
        if failure is None:
            connection.execute(
                """
                UPDATE report_documents
                SET processing_status = 'PROCESSED', processed_at = now(), failure_reason = NULL
                WHERE id = %s AND object_key = %s
                """,
                (event.document_id, event.key),
            )
            return "processed"
        connection.execute(
            """
            UPDATE report_documents
            SET processing_status = 'FAILED', processed_at = now(), failure_reason = %s
            WHERE id = %s AND object_key = %s
            """,
            (failure[:500], event.document_id, event.key),
        )
        return "failed"


def process_record(record: dict[str, Any], expected_bucket: str, s3_client, connection) -> str:
    event = parse_record(record, expected_bucket)
    if event_already_processed(connection, event.event_id):
        return "duplicate"
    document = load_document(connection, event)
    size, sha256, metadata = object_digest(s3_client, event)
    failure = validation_failure(document, event, size, sha256, metadata)
    return persist_result(connection, event, failure)


@contextmanager
def database_connection():
    region = required_environment("AWS_REGION")
    host = required_environment("POSTGRES_HOST")
    port = int(required_environment("POSTGRES_PORT"))
    database = required_environment("POSTGRES_DB")
    user = required_environment("POSTGRES_USER")
    ca_file = Path(required_environment("POSTGRES_SSLROOTCERT"))
    if not DATABASE_USER.fullmatch(user):
        raise RuntimeError("POSTGRES_USER is not an approved identifier")
    if not host.endswith((".rds.amazonaws.com", ".rds.amazonaws.com.cn")):
        raise RuntimeError("POSTGRES_HOST must be an RDS endpoint")
    if not ca_file.is_file():
        raise RuntimeError("POSTGRES_SSLROOTCERT is missing")

    token = boto3.client("rds", region_name=region).generate_db_auth_token(
        DBHostname=host,
        Port=port,
        DBUsername=user,
        Region=region,
    )
    with psycopg.connect(
        host=host,
        port=port,
        dbname=database,
        user=user,
        password=token,
        sslmode="verify-full",
        sslrootcert=str(ca_file),
        connect_timeout=5,
        autocommit=True,
        row_factory=dict_row,
    ) as connection:
        yield connection


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, int]:
    expected_bucket = required_environment("S3_BUCKET")
    records = event.get("Records")
    if not isinstance(records, list) or not records:
        raise ValueError("At least one S3 record is required")

    counts = {"processed": 0, "duplicate": 0, "failed": 0}
    s3_client = boto3.client("s3", region_name=required_environment("AWS_REGION"))
    with database_connection() as connection:
        for record in records:
            result = process_record(record, expected_bucket, s3_client, connection)
            counts[result] += 1
    return counts
