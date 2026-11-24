"""Run on the Account A backup EC2 instance against its loopback API."""

import hashlib
import json
import sys
from datetime import date
from uuid import UUID, uuid4

import boto3
import httpx
from app.auth_models import AuthAudit, AuthSession
from app.config import Settings
from app.database import create_db_engine
from app.domain_models import (
    AgentAssignment,
    Candidate,
    Election,
    ElectionCandidate,
    ElectionStation,
    Report,
    ReportEvent,
    ReportRevision,
    UserReference,
    UserRole,
)
from app.models import PollingStation
from app.phase5_models import ReportDocument
from app.security import issue_session
from sqlalchemy import delete, insert, text
from sqlalchemy.orm import Session


def main(secret_arn: str, bucket: str) -> None:
    aws = boto3.Session(region_name="eu-north-1")
    secret = json.loads(
        aws.client("secretsmanager").get_secret_value(SecretId=secret_arn)[
            "SecretString"
        ]
    )
    settings = Settings(
        app_env="cloud",
        postgres_host=secret["host"],
        postgres_port=secret["port"],
        postgres_db=secret["database"],
        postgres_user=secret["username"],
        postgres_password=secret["password"],
        postgres_sslmode="verify-full",
        postgres_sslrootcert="/opt/electionhub/rds-ca.pem",
    )
    engine = create_db_engine(settings)
    user, station, election, candidate = (uuid4() for _ in range(4))
    marker = f"DEMO-{user.hex}"
    today = date.today()
    s3 = aws.client("s3")
    with Session(engine) as session, session.begin():
        tls = session.scalar(
            text("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()")
        )
        if tls is not True:
            raise RuntimeError("Runtime connection is not using TLS")
        for model, values in (
            (
                UserReference,
                {"id": user, "code": marker, "display_name": "EC2 smoke agent"},
            ),
            (UserRole, {"user_id": user, "role": "AGENT"}),
            (
                PollingStation,
                {
                    "id": station,
                    "code": marker,
                    "name": "EC2 smoke",
                    "registered_voters": 10,
                },
            ),
            (
                Election,
                {
                    "id": election,
                    "code": marker,
                    "name": "EC2 smoke",
                    "start_date": today,
                    "end_date": today,
                },
            ),
            (
                ElectionStation,
                {
                    "election_id": election,
                    "polling_station_id": station,
                    "registered_voters": 10,
                },
            ),
            (
                AgentAssignment,
                {
                    "election_id": election,
                    "polling_station_id": station,
                    "user_id": user,
                },
            ),
            (
                Candidate,
                {"id": candidate, "code": marker, "name": "EC2 smoke candidate"},
            ),
            (ElectionCandidate, {"election_id": election, "candidate_id": candidate}),
        ):
            session.execute(insert(model).values(**values))
        token = issue_session(session, user, 300).access_token

    report = revision = document = key = None
    content = b"%PDF-1.4\n% ElectionHub EC2 synthetic smoke\n%%EOF\n"
    digest = hashlib.sha256(content).hexdigest()
    try:
        with httpx.Client(base_url="http://127.0.0.1:8000", timeout=30) as client:
            health = client.get("/health")
            health.raise_for_status()
            assert health.json()["environment"] == "cloud"
            assert health.json()["schema_version"] == "0005_incidents"
            station_response = client.get(f"/api/v1/polling-stations/{station}")
            station_response.raise_for_status()
            assert station_response.json()["code"] == marker

            client.headers["Authorization"] = f"Bearer {token}"
            draft = client.post(
                "/api/v1/reports",
                json={"election_id": str(election), "polling_station_id": str(station)},
            )
            draft.raise_for_status()
            report, revision = (
                UUID(draft.json()[field]) for field in ("report_id", "id")
            )
            base = f"/api/v1/reports/{report}/revisions/1/documents"
            upload = client.post(
                base,
                data={"expected_version": str(draft.json()["edit_version"])},
                files={"file": ("synthetic-ec2.pdf", content, "application/pdf")},
            )
            upload.raise_for_status()
            document = upload.json()
            key = f"reports/{report}/revisions/1/{document['id']}.pdf"
            print(f"TEST_KEY={key}", flush=True)
            assert upload.status_code == 201 and document["storage_provider"] == "S3"
            assert document["sha256"] == digest
            assert (
                s3.head_object(Bucket=bucket, Key=key)["ServerSideEncryption"]
                == "AES256"
            )
            download = client.get(f"{base}/{document['id']}/content")
            download.raise_for_status()
            assert (
                download.status_code == 200
                and hashlib.sha256(download.content).hexdigest() == digest
            )
            deletion = client.delete(f"{base}/{document['id']}")
            deletion.raise_for_status()
            assert deletion.status_code == 204
            assert client.get(f"{base}/{document['id']}/content").status_code == 404
            print(
                "PASS health=200 database_read=200 tls=verified upload=201 download=200 delete=204",
                flush=True,
            )
    finally:
        if key:
            # An immediate second delete could create another S3 delete marker.
            with Session(engine) as session:
                remaining = session.scalar(
                    text(
                        "SELECT count(*) FROM report_documents WHERE object_key = :key"
                    ),
                    {"key": key},
                )
            if remaining:
                s3.delete_object(Bucket=bucket, Key=key)
        with Session(engine) as session, session.begin():
            if revision and report:
                session.execute(
                    delete(ReportDocument).where(ReportDocument.revision_id == revision)
                )
                session.execute(
                    delete(ReportEvent).where(ReportEvent.revision_id == revision)
                )
                session.execute(
                    delete(ReportRevision).where(ReportRevision.id == revision)
                )
                session.execute(delete(Report).where(Report.id == report))
            for model, predicate in (
                (AuthAudit, AuthAudit.actor_id == user),
                (AuthSession, AuthSession.user_id == user),
                (UserRole, UserRole.user_id == user),
                (AgentAssignment, AgentAssignment.user_id == user),
                (ElectionCandidate, ElectionCandidate.election_id == election),
                (ElectionStation, ElectionStation.election_id == election),
                (UserReference, UserReference.id == user),
                (Candidate, Candidate.id == candidate),
                (Election, Election.id == election),
                (PollingStation, PollingStation.id == station),
            ):
                session.execute(delete(model).where(predicate))
        engine.dispose()
        print("Synthetic RDS rows removed", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
