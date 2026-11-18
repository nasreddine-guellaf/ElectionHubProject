from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.auth_models import Account
from app.bootstrap_auth import DEMO_USERS
from app.config import Settings
from app.domain_models import (
    Candidate,
    Election,
    ElectionCandidate,
    Report,
    ReportEvent,
    ReportResult,
    ReportRevision,
    ReportValidation,
    UserReference,
)
from app.domain_schemas import DraftInput, ResultsInput
from app.domain_service import create_draft, update_results
from app.main import create_app
from app.security import hasher, issue_session
from app.seed_domain import seed_domain
from tests.conftest import alembic_config

ACTOR = UUID("30000000-0000-4000-8000-000000000001")
ELECTION = "10000000-0000-4000-8000-000000000001"
STATION = "00000000-0000-4000-8000-000000000001"
TEST_PASSWORD = "test-only-password-for-fixtures"
CANDIDATES = [f"20000000-0000-4000-8000-{i:012d}" for i in range(1, 4)]


@pytest.fixture
def domain_engine(db_engine):
    with Session(db_engine) as session, session.begin():
        seed_domain(session, include_reports=False)
        for username, user_id in DEMO_USERS.items():
            session.add(
                Account(
                    user_id=user_id, username=username, password_hash=hasher.hash(TEST_PASSWORD)
                )
            )
    return db_engine


@pytest.fixture
def domain_client(domain_engine):
    settings = Settings(app_env="test")
    with TestClient(create_app(settings, engine=domain_engine)) as client:
        with Session(domain_engine) as session, session.begin():
            client.tokens = {
                name.removeprefix("demo-").upper(): issue_session(
                    session, user_id, 3600
                ).access_token
                for name, user_id in DEMO_USERS.items()
            }
        as_role(client, "AGENT")
        yield client


def as_role(client, role):
    client.headers["Authorization"] = "Bearer " + client.tokens[role]


def draft(client):
    as_role(client, "AGENT")
    response = client.post(
        "/api/v1/reports", json={"election_id": ELECTION, "polling_station_id": STATION}
    )
    assert response.status_code == 201, response.text
    return response.json()


def payload(version=1):
    return {
        "expected_version": version,
        "ballots_cast": 100,
        "valid_votes": 90,
        "blank_votes": 6,
        "invalid_votes": 4,
        "results": [
            {"candidate_id": cid, "votes": votes}
            for cid, votes in zip(CANDIDATES, [40, 30, 20], strict=True)
        ],
    }


def path(revision):
    return f"/api/v1/reports/{revision['report_id']}/revisions/{revision['revision_number']}"


def submitted(client):
    revision = draft(client)
    assert client.put(path(revision) + "/results", json=payload()).status_code == 200
    response = client.post(path(revision) + "/submit", json={"expected_version": 2})
    assert response.status_code == 200, response.text
    return response.json()


def test_new_api_requires_authentication(client):
    for method, endpoint in [("get", "/elections"), ("get", "/reports"), ("post", "/reports")]:
        assert getattr(client, method)("/api/v1" + endpoint).status_code == 401
    assert client.get("/api/v1/polling-stations").status_code == 200


def test_key_and_actor_cannot_be_spoofed(domain_client, domain_engine):
    response = domain_client.get("/api/v1/reports", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401
    forged = {"election_id": ELECTION, "polling_station_id": STATION, "created_by": str(uuid4())}
    assert domain_client.post("/api/v1/reports", json=forged).status_code == 422
    with Session(domain_engine) as session, session.begin():
        session.get(UserReference, ACTOR).active = False
    assert domain_client.get("/api/v1/reports").status_code == 401


def test_election_crud_and_errors(domain_client):
    as_role(domain_client, "ADMIN")
    data = {
        "code": "DEMO-CRUD",
        "name": "Scrutin fictif CRUD",
        "start_date": "2027-01-01",
        "end_date": "2027-01-02",
    }
    created = domain_client.post("/api/v1/elections", json=data)
    assert created.status_code == 201
    endpoint = "/api/v1/elections/" + created.json()["id"]
    assert domain_client.get(endpoint).json()["name"] == data["name"]
    assert domain_client.post("/api/v1/elections", json=data).status_code == 409
    data["name"] = "Scrutin fictif modifié"
    assert domain_client.put(endpoint, json=data).json()["name"] == data["name"]
    assert domain_client.get("/api/v1/elections?limit=1&offset=0").json()["total"] == 2
    assert domain_client.get("/api/v1/elections?limit=101").status_code == 422
    assert domain_client.delete(endpoint).status_code == 204
    assert domain_client.get(endpoint).status_code == 404
    assert domain_client.delete(f"/api/v1/elections/{ELECTION}").status_code == 409
    data["end_date"] = "2026-01-01"
    assert domain_client.post("/api/v1/elections", json=data).status_code == 422
    assert domain_client.get("/api/v1/elections/bad-uuid").status_code == 422


def test_candidate_station_and_assignment_apis(domain_client):
    as_role(domain_client, "ADMIN")
    candidate = domain_client.post(
        "/api/v1/candidates", json={"code": "DEMO-NEW", "name": "Liste fictive nouvelle"}
    )
    assert candidate.status_code == 201
    cid = candidate.json()["id"]
    assert domain_client.get(f"/api/v1/candidates/{cid}").status_code == 200
    endpoint = f"/api/v1/elections/{ELECTION}/candidates"
    assert domain_client.post(endpoint, json={"candidate_id": cid}).status_code == 201
    assert domain_client.get(endpoint).json()["total"] == 4
    assert domain_client.post(endpoint, json={"candidate_id": cid}).status_code == 409
    assert domain_client.delete(endpoint + "/" + cid).status_code == 204
    stations = domain_client.get(f"/api/v1/elections/{ELECTION}/polling-stations").json()
    assert stations["total"] == 3
    assignment = f"/api/v1/assignments/{ELECTION}/{STATION}/{ACTOR}"
    assert domain_client.delete(assignment).status_code == 204
    data = {"election_id": ELECTION, "polling_station_id": STATION, "user_id": str(ACTOR)}
    assert domain_client.post("/api/v1/assignments", json=data).status_code == 201
    assert domain_client.get(f"/api/v1/assignments?election_id={ELECTION}").json()["total"] == 3
    assert domain_client.get("/api/v1/user-references").json()["total"] == 3


def test_full_report_lifecycle_and_preserved_history(domain_client, domain_engine):
    first = submitted(domain_client)
    assert first["status"] == "SUBMITTED"
    assert first["submitted_at"].endswith("Z")
    response = domain_client.post(
        path(first) + "/revise",
        json={"expected_version": 3, "reason": "Correction fictive de la répartition"},
    )
    assert response.status_code == 201, response.text
    second = response.json()
    assert second["revision_number"] == 2 and second["status"] == "DRAFT"
    data = payload()
    data["results"][0]["votes"] = 30
    data["results"][1]["votes"] = 40
    assert domain_client.put(path(second) + "/results", json=data).status_code == 200
    assert domain_client.get(path(first)).json() == first
    assert (
        domain_client.post(path(second) + "/submit", json={"expected_version": 2}).status_code
        == 200
    )
    report_path = "/api/v1/reports/" + first["report_id"]
    assert domain_client.get(report_path).json()["current_revision"] == 2
    assert domain_client.get(report_path + "/revisions").json()["total"] == 2
    assert domain_client.get(report_path + "/validations").json()["total"] == 0
    events = domain_client.get(report_path + "/history").json()["items"]
    assert [event["action"] for event in events] == [
        "CREATED",
        "RESULTS_UPDATED",
        "SUBMITTED",
        "REVISED",
        "RESULTS_UPDATED",
        "SUBMITTED",
    ]
    assert domain_client.get("/api/v1/reports").json()["total"] == 1
    with Session(domain_engine) as session:
        report = session.get(Report, UUID(first["report_id"]))
        assert len(report.revisions) == 2
        assert session.scalar(select(func.count()).select_from(ReportResult)) == 6


@pytest.mark.parametrize(
    "change",
    [
        {"valid_votes": 89},
        {"ballots_cast": 101},
        {"ballots_cast": 601},
        {"ballots_cast": 80},
        {"blank_votes": -1},
        {"valid_votes": 1.5},
        {"valid_votes": True},
        {"valid_votes": "90"},
        {"ballots_cast": 2147483648},
        {"results": []},
        {"status": "APPROVED"},
    ],
)
def test_invalid_results_roll_back_without_audit_changes(domain_client, change):
    revision = draft(domain_client)
    data = payload()
    data.update(change)
    response = domain_client.put(path(revision) + "/results", json=data)
    assert response.status_code == 422, response.text
    assert set(response.json()) == {"detail"}
    assert domain_client.get(path(revision)).json()["edit_version"] == 1
    assert (
        domain_client.get(f"/api/v1/reports/{revision['report_id']}/history").json()["total"] == 1
    )


@pytest.mark.parametrize("kind", ["duplicate", "missing", "foreign", "negative"])
def test_candidate_set_and_vote_integrity(domain_client, kind):
    revision = draft(domain_client)
    data = payload()
    if kind == "duplicate":
        data["results"][1]["candidate_id"] = CANDIDATES[0]
    elif kind == "missing":
        data["results"].pop()
    elif kind == "foreign":
        data["results"][0]["candidate_id"] = str(uuid4())
    else:
        data["results"][0]["votes"] = -1
    assert domain_client.put(path(revision) + "/results", json=data).status_code == 422


def test_configurable_ballot_equation(domain_client):
    as_role(domain_client, "ADMIN")
    election = domain_client.get(f"/api/v1/elections/{ELECTION}").json()
    data = {key: election[key] for key in ("code", "name", "start_date", "end_date")}
    data["enforce_ballot_equation"] = False
    assert domain_client.put(f"/api/v1/elections/{ELECTION}", json=data).status_code == 200
    revision = draft(domain_client)
    counts = payload()
    counts["ballots_cast"] = 110
    assert domain_client.put(path(revision) + "/results", json=counts).status_code == 200
    assert (
        domain_client.post(path(revision) + "/submit", json={"expected_version": 2}).status_code
        == 200
    )
    as_role(domain_client, "ADMIN")
    assert domain_client.put(f"/api/v1/elections/{ELECTION}", json=data).status_code == 409


def test_invalid_transitions_stale_versions_and_no_approval_route(domain_client):
    revision = draft(domain_client)
    base = path(revision)
    assert domain_client.post(base + "/submit", json={"expected_version": 1}).status_code == 422
    assert (
        domain_client.post(
            base + "/revise", json={"expected_version": 1, "reason": "Essai"}
        ).status_code
        == 409
    )
    assert domain_client.put(base + "/results", json=payload(99)).status_code == 409
    assert domain_client.put(base + "/results", json=payload()).status_code == 200
    assert domain_client.put(base + "/results", json=payload()).status_code == 409
    assert domain_client.post(base + "/submit", json={"expected_version": 2}).status_code == 200
    assert domain_client.put(base + "/results", json=payload(3)).status_code == 409
    assert domain_client.post(base + "/submit", json={"expected_version": 3}).status_code == 409
    assert domain_client.post(base + "/approve", json={}).status_code == 404
    assert domain_client.patch(base, json={"status": "APPROVED"}).status_code == 405
    assert (
        domain_client.post(
            base + "/revise", json={"expected_version": 3, "reason": " "}
        ).status_code
        == 422
    )
    assert (
        domain_client.post(
            base + "/revise", json={"expected_version": 3, "reason": "Correction"}
        ).status_code
        == 201
    )
    assert (
        domain_client.post(
            base + "/revise", json={"expected_version": 3, "reason": "Double"}
        ).status_code
        == 409
    )


def test_duplicate_missing_station_and_assignment(domain_client):
    as_role(domain_client, "ADMIN")
    endpoint = f"/api/v1/assignments/{ELECTION}/{STATION}/{ACTOR}"
    assert domain_client.delete(endpoint).status_code == 204
    data = {"election_id": ELECTION, "polling_station_id": STATION}
    assert domain_client.post("/api/v1/reports", json=data).status_code == 403
    assert (
        domain_client.post("/api/v1/assignments", json={**data, "user_id": str(ACTOR)}).status_code
        == 201
    )
    draft(domain_client)
    assert domain_client.post("/api/v1/reports", json=data).status_code == 409
    data["polling_station_id"] = str(uuid4())
    assert domain_client.post("/api/v1/reports", json=data).status_code == 404
    assert domain_client.get(f"/api/v1/reports/{uuid4()}/history").status_code == 404


def test_rejected_revision_preserves_decision(domain_client, domain_engine):
    first = submitted(domain_client)
    # Fixture de décision future, pas une opération HTTP ouverte en phase 2.
    with Session(domain_engine) as session, session.begin():
        session.get(ReportRevision, UUID(first["id"])).status = "REJECTED"
        session.add(
            ReportValidation(
                revision_id=UUID(first["id"]),
                validator_id=UUID("30000000-0000-4000-8000-000000000002"),
                decision="REJECTED",
                reason="Pièce fictive à corriger",
            )
        )
    response = domain_client.post(
        path(first) + "/revise", json={"expected_version": 3, "reason": "Correction demandée"}
    )
    assert response.status_code == 201
    assert domain_client.get(path(first)).json()["status"] == "REJECTED"
    assert (
        domain_client.get(f"/api/v1/reports/{first['report_id']}/validations").json()["total"] == 1
    )


def test_seed_idempotence_and_no_automatic_approval(domain_engine):
    with Session(domain_engine) as session, session.begin():
        seed_domain(session)
    with Session(domain_engine) as session, session.begin():
        before = list(session.scalars(select(ReportEvent.id).order_by(ReportEvent.id)))
        seed_domain(session)
        assert list(session.scalars(select(ReportEvent.id).order_by(ReportEvent.id))) == before
        assert session.scalar(select(func.count()).select_from(Report)) == 2
        assert set(session.scalars(select(ReportRevision.status))) == {"DRAFT", "SUBMITTED"}


def test_upgrade_preserves_phase1_data_and_downgrade(db_engine):
    with db_engine.begin() as connection:
        config = alembic_config(connection)
        command.downgrade(config, "0001_polling_stations")
        connection.execute(
            text(
                "INSERT INTO polling_stations (id,code,name,registered_voters) "
                "VALUES (:id,'DEMO-KEEP','Bureau fictif préservé',42)"
            ),
            {"id": uuid4()},
        )
        command.upgrade(config, "head")
        assert connection.scalar(text("SELECT registered_voters FROM polling_stations")) == 42
        command.check(config)
        command.downgrade(config, "0001_polling_stations")
        assert connection.scalar(text("SELECT count(*) FROM polling_stations")) == 1


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE report_revisions SET ballots_cast = -1",
        "UPDATE report_revisions SET status = 'INVALID'",
        "UPDATE report_revisions SET ballots_cast = 601, valid_votes = 591",
        "UPDATE report_revisions SET valid_votes = 91",
        "UPDATE report_results SET votes = -1",
        "UPDATE election_stations SET registered_voters = -1",
    ],
)
def test_database_check_constraints(domain_client, domain_engine, statement):
    submitted(domain_client)
    with domain_engine.begin() as connection, pytest.raises(IntegrityError):
        with connection.begin_nested():
            connection.execute(text(statement))


def test_composite_foreign_key_rejects_candidate_from_other_election(domain_client, domain_engine):
    revision = draft(domain_client)
    with Session(domain_engine) as session, session.begin():
        other = Election(
            code="DEMO-OTHER",
            name="Autre scrutin fictif",
            start_date="2026-01-01",
            end_date="2026-01-01",
        )
        candidate = Candidate(code="DEMO-OTHER-CANDIDATE", name="Autre liste fictive")
        session.add_all([other, candidate])
        session.flush()
        session.add(ElectionCandidate(election_id=other.id, candidate_id=candidate.id))
        session.flush()
        with pytest.raises(IntegrityError), session.begin_nested():
            session.add(
                ReportResult(
                    revision_id=UUID(revision["id"]),
                    election_id=UUID(ELECTION),
                    candidate_id=candidate.id,
                    votes=1,
                )
            )
            session.flush()


def test_concurrent_creation_has_one_winner(domain_engine):
    barrier = Barrier(2)

    def attempt():
        with Session(domain_engine) as session:
            barrier.wait(timeout=10)
            try:
                create_draft(
                    session, DraftInput(election_id=ELECTION, polling_station_id=STATION), ACTOR
                )
                session.commit()
                return 201
            except HTTPException as error:
                session.rollback()
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(lambda _: attempt(), range(2))) == [201, 409]


def test_concurrent_edits_do_not_overwrite(domain_client, domain_engine):
    revision = draft(domain_client)
    barrier = Barrier(2)

    def attempt():
        with Session(domain_engine) as session:
            barrier.wait(timeout=10)
            try:
                update_results(
                    session,
                    UUID(revision["report_id"]),
                    1,
                    ResultsInput(**deepcopy(payload())),
                    ACTOR,
                )
                session.commit()
                return 200
            except HTTPException as error:
                session.rollback()
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(lambda _: attempt(), range(2))) == [200, 409]


def test_database_prevents_duplicate_report_and_two_drafts(domain_client, domain_engine):
    first = draft(domain_client)
    with Session(domain_engine) as session, session.begin():
        with pytest.raises(IntegrityError), session.begin_nested():
            session.add(
                Report(
                    election_id=UUID(ELECTION), polling_station_id=UUID(STATION), created_by=ACTOR
                )
            )
            session.flush()
        with pytest.raises(IntegrityError), session.begin_nested():
            session.add(
                ReportRevision(
                    report_id=UUID(first["report_id"]),
                    election_id=UUID(ELECTION),
                    revision_number=2,
                    created_by=ACTOR,
                    revision_reason="Autre",
                    registered_voters=600,
                    enforce_ballot_equation=True,
                )
            )
            session.flush()


def test_rejection_requires_reason_in_database(domain_client, domain_engine):
    first = submitted(domain_client)
    with Session(domain_engine) as session, pytest.raises(IntegrityError), session.begin():
        session.add(
            ReportValidation(
                revision_id=UUID(first["id"]), validator_id=ACTOR, decision="REJECTED", reason=" "
            )
        )
        session.flush()


@pytest.mark.parametrize("state", ["PROCESSING", "PENDING_VALIDATION", "APPROVED", "PUBLISHED"])
def test_reserved_states_cannot_be_edited_or_revised(domain_client, domain_engine, state):
    first = submitted(domain_client)
    with Session(domain_engine) as session, session.begin():
        session.get(ReportRevision, UUID(first["id"])).status = state
    assert domain_client.put(path(first) + "/results", json=payload(3)).status_code == 409
    response = domain_client.post(
        path(first) + "/revise", json={"expected_version": 3, "reason": "Modification interdite"}
    )
    assert response.status_code == 409


def test_seed_history_order_when_timestamps_match(domain_client, domain_engine):
    with Session(domain_engine) as session, session.begin():
        seed_domain(session)
    report = domain_client.get(f"/api/v1/reports?polling_station_id={STATION}").json()["items"][0]
    events = domain_client.get(f"/api/v1/reports/{report['id']}/history").json()["items"]
    assert [item["action"] for item in events] == ["CREATED", "RESULTS_UPDATED", "SUBMITTED"]


def test_bearer_is_required_for_all_domain_openapi_routes(domain_client):
    document = domain_client.get("/openapi.json").json()
    for endpoint, methods in document["paths"].items():
        if (
            endpoint.startswith("/api/v1/auth/")
            or not endpoint.startswith("/api/v1/")
            or endpoint.startswith("/api/v1/polling-stations")
        ):
            continue
        for operation in methods.values():
            assert operation["security"] == [{"HTTPBearer": []}]
    del domain_client.headers["Authorization"]
    assert domain_client.get("/api/v1/reports").status_code == 401


def test_reference_registration_and_missing_references(domain_client):
    as_role(domain_client, "ADMIN")
    election = domain_client.post(
        "/api/v1/elections",
        json={
            "code": "DEMO-REGISTER",
            "name": "Inscription fictive",
            "start_date": "2026-11-01",
            "end_date": "2026-11-01",
        },
    ).json()
    endpoint = f"/api/v1/elections/{election['id']}/polling-stations"
    assert (
        domain_client.post(
            endpoint, json={"polling_station_id": str(uuid4()), "registered_voters": 100}
        ).status_code
        == 404
    )
    assert (
        domain_client.post(
            endpoint, json={"polling_station_id": STATION, "registered_voters": 100}
        ).status_code
        == 201
    )
    assignment = {
        "election_id": election["id"],
        "polling_station_id": STATION,
        "user_id": str(ACTOR),
    }
    assert domain_client.post("/api/v1/assignments", json=assignment).status_code == 201
    as_role(domain_client, "AGENT")
    data = {"election_id": election["id"], "polling_station_id": STATION}
    assert domain_client.post("/api/v1/reports", json=data).status_code == 422  # aucun candidat
    as_role(domain_client, "ADMIN")
    endpoint = f"/api/v1/elections/{election['id']}/candidates"
    assert domain_client.post(endpoint, json={"candidate_id": str(uuid4())}).status_code == 404


def test_non_author_cannot_change_report(domain_client, domain_engine):
    from app.domain_models import AgentAssignment

    first = submitted(domain_client)
    other_id = UUID("30000000-0000-4000-8000-000000000002")
    with Session(domain_engine) as session, session.begin():
        session.add(
            AgentAssignment(
                election_id=UUID(ELECTION), polling_station_id=UUID(STATION), user_id=other_id
            )
        )
    as_role(domain_client, "VALIDATOR")
    response = domain_client.post(
        path(first) + "/revise", json={"expected_version": 3, "reason": "Autre acteur"}
    )
    assert response.status_code == 403
