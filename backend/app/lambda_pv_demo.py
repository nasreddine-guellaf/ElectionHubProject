"""Synthetic PV smoke entry point, packaged only for the Account B demo."""

import hashlib
from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace

from app.lambda_pv import parse_records, process_events

BUCKET = "electionhub-synthetic"
DOCUMENT = "33333333-3333-4333-8333-333333333333"
KEY = f"reports/22222222-2222-4222-8222-222222222222/revisions/1/{DOCUMENT}.pdf"
VERSION = "demo-version-1"
CONTENT = b"%PDF-1.4\nSynthetic test input\n%%EOF\n"


class DemoS3:
    def get_object(self, *, Bucket, Key, VersionId=None):
        if (Bucket, Key, VersionId) != (BUCKET, KEY, VERSION):
            raise ValueError("Unknown synthetic object version")
        return {"Body": BytesIO(CONTENT), "Metadata": {"document-id": DOCUMENT}}


class DemoConnection:
    def __init__(self):
        self.events = set()

    def execute(self, query, parameters):
        normalized = " ".join(query.split())
        row = None
        if normalized.startswith("SELECT 1 FROM object_events"):
            row = (1,) if parameters[0] in self.events else None
        elif normalized.startswith("SELECT id, object_key, size_bytes, sha256"):
            if (str(parameters[0]), parameters[1]) == (DOCUMENT, KEY):
                row = {"size_bytes": len(CONTENT), "sha256": hashlib.sha256(CONTENT).hexdigest()}
        elif normalized.startswith("INSERT INTO object_events"):
            if parameters[1] not in self.events:
                self.events.add(parameters[1])
                row = (parameters[1],)
        elif not normalized.startswith("UPDATE report_documents"):
            raise AssertionError("Unexpected demo SQL")
        return SimpleNamespace(fetchone=lambda: row)

    @contextmanager
    def transaction(self):
        previous_events = self.events.copy()
        try:
            yield
        except Exception:
            self.events = previous_events
            raise


def lambda_handler(event, context):
    return process_events(parse_records(event, BUCKET), DemoS3(), DemoConnection())
