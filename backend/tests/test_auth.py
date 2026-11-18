from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.auth_models import Account, AuthAudit, AuthSession, OtpChallenge, RateLimit
from app.bootstrap_auth import DEMO_USERS, seed_citizen
from app.config import Settings
from app.domain_models import AgentAssignment, UserReference, UserRole
from app.main import create_app
from app.security import digest, issue_session, now, verify_password
from tests.test_domain import (  # réutilise le jeu métier, pas de bypass des dépendances RBAC
    ACTOR,
    ELECTION,
    STATION,
    TEST_PASSWORD,
    as_role,
    draft,
    path,
    payload,
    submitted,
)


def login(client, username="demo-agent", password=TEST_PASSWORD):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def use_token(client, token):
    client.headers["Authorization"] = "Bearer " + token


def test_login_session_hash_logout_and_no_secrets(domain_client, domain_engine):
    response = login(domain_client)
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    assert response.headers["cache-control"] == "no-store"
    assert TEST_PASSWORD not in response.text
    use_token(domain_client, token)
    assert domain_client.get("/api/v1/auth/me").json()["role"] == "AGENT"
    with Session(domain_engine) as session:
        assert session.get(AuthSession, digest(token)).user_id == ACTOR
        assert session.get(AuthSession, token) is None
        account = session.get(Account, ACTOR)
        assert account.password_hash.startswith("$argon2id$")
        assert TEST_PASSWORD not in account.password_hash
        assert verify_password(account.password_hash, TEST_PASSWORD)
    assert domain_client.post("/api/v1/auth/logout").status_code == 204
    assert domain_client.get("/api/v1/reports").status_code == 401


def test_wrong_unknown_disabled_login_uniform_and_throttled(domain_client, domain_engine):
    wrong = login(domain_client, password="wrong-password")
    missing = login(domain_client, username="demo-missing", password="wrong-password")
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json() == missing.json() == {"detail": "Identifiants invalides."}
    with Session(domain_engine) as session, session.begin():
        session.get(UserReference, ACTOR).active = False
    assert login(domain_client).json() == wrong.json()
    for _ in range(3):
        assert login(domain_client).status_code == 401
    response = login(domain_client)
    assert response.status_code == 429 and response.headers["retry-after"] == "900"
    with Session(domain_engine) as session:
        assert (
            session.scalar(
                select(RateLimit.attempts).where(RateLimit.key == digest("login:id:demo-agent"))
            )
            == 6
        )


def test_expired_forged_and_development_key_denied(domain_client, domain_engine):
    token = domain_client.tokens["AGENT"]
    with Session(domain_engine) as session, session.begin():
        session.get(AuthSession, digest(token)).expires_at = now() - timedelta(seconds=1)
    assert domain_client.get("/api/v1/reports").status_code == 401
    use_token(domain_client, "x" * 43)
    assert domain_client.get("/api/v1/reports").status_code == 401
    del domain_client.headers["Authorization"]
    assert (
        domain_client.get("/api/v1/reports", headers={"X-Development-Key": "legacy"}).status_code
        == 401
    )


def test_password_change_revokes_every_session(domain_client, domain_engine):
    second = login(domain_client).json()["access_token"]
    response = domain_client.post(
        "/api/v1/auth/password",
        json={"current_password": "wrong", "new_password": "new-test-password-123"},
    )
    assert response.status_code == 400
    response = domain_client.post(
        "/api/v1/auth/password",
        json={"current_password": TEST_PASSWORD, "new_password": "new-test-password-123"},
    )
    assert response.status_code == 204
    assert domain_client.get("/api/v1/auth/me").status_code == 401
    use_token(domain_client, second)
    assert domain_client.get("/api/v1/auth/me").status_code == 401
    assert login(domain_client).status_code == 401
    assert login(domain_client, password="new-test-password-123").status_code == 200


@pytest.mark.parametrize("role", ["AGENT", "VALIDATOR"])
def test_staff_cannot_manage_accounts_or_reference_data(domain_client, role):
    as_role(domain_client, role)
    assert domain_client.get("/api/v1/accounts").status_code == 403
    assert domain_client.get("/api/v1/user-references").status_code == 403
    assert domain_client.get("/api/v1/audit").status_code == 403
    data = {
        "code": "DEMO-NO",
        "name": "Refus",
        "start_date": "2026-11-01",
        "end_date": "2026-11-01",
    }
    assert domain_client.post("/api/v1/elections", json=data).status_code == 403
    assert (
        domain_client.post(
            "/api/v1/candidates", json={"code": "DEMO-NO", "name": "Refus"}
        ).status_code
        == 403
    )


def test_admin_account_lifecycle_and_audit(domain_client, domain_engine):
    as_role(domain_client, "ADMIN")
    data = {
        "code": "DEMO-NEW-AGENT",
        "display_name": "Agent fictif nouveau",
        "username": "demo-new-agent",
        "password": TEST_PASSWORD,
        "role": "AGENT",
    }
    response = domain_client.post("/api/v1/accounts", json=data)
    assert response.status_code == 201, response.text
    user_id = response.json()["id"]
    assert "password" not in response.text
    assert domain_client.post("/api/v1/accounts", json=data).status_code == 409
    token = login(domain_client, username="demo-new-agent").json()["access_token"]
    endpoint = f"/api/v1/accounts/{user_id}"
    assert (
        domain_client.put(endpoint, json={"role": "VALIDATOR", "active": True}).status_code == 200
    )
    use_token(domain_client, token)
    assert domain_client.get("/api/v1/auth/me").status_code == 401
    token = login(domain_client, username="demo-new-agent").json()["access_token"]
    as_role(domain_client, "ADMIN")
    assert (
        domain_client.put(endpoint, json={"role": "VALIDATOR", "active": False}).status_code == 200
    )
    use_token(domain_client, token)
    assert domain_client.get("/api/v1/auth/me").status_code == 401
    assert login(domain_client, username="demo-new-agent").status_code == 401
    as_role(domain_client, "ADMIN")
    audit = domain_client.get("/api/v1/audit").json()["items"]
    assert {row["action"] for row in audit} >= {"ACCOUNT_CREATED", "ACCOUNT_UPDATED"}
    assert TEST_PASSWORD not in str(audit) and token not in str(audit)
    assert (
        domain_client.put(
            f"/api/v1/accounts/{DEMO_USERS['demo-admin']}",
            json={"role": "VALIDATOR", "active": False},
        ).status_code
        == 409
    )


def test_admin_reset_revokes_token_and_password_validation_redacted(domain_client):
    as_role(domain_client, "ADMIN")
    endpoint = f"/api/v1/accounts/{ACTOR}/password"
    response = domain_client.post(endpoint, json={"new_password": "tiny"})
    assert response.status_code == 422 and "tiny" not in response.text
    assert (
        domain_client.post(endpoint, json={"new_password": "replacement-test-password"}).status_code
        == 204
    )
    as_role(domain_client, "AGENT")
    assert domain_client.get("/api/v1/auth/me").status_code == 401
    assert login(domain_client).status_code == 401
    assert login(domain_client, password="replacement-test-password").status_code == 200


def test_agent_scope_on_all_report_read_routes(domain_client, domain_engine):
    report = submitted(domain_client)
    other = uuid4()
    with Session(domain_engine) as session, session.begin():
        session.add(
            UserReference(id=other, code="DEMO-OTHER-AGENT", display_name="Autre agent fictif")
        )
        session.flush()
        session.add(UserRole(user_id=other, role="AGENT"))
        session.add(
            AgentAssignment(
                election_id=UUID(ELECTION), polling_station_id=UUID(STATION), user_id=other
            )
        )
        token = issue_session(session, other, 3600).access_token
    use_token(domain_client, token)
    assert domain_client.get("/api/v1/reports").json()["total"] == 0
    base = f"/api/v1/reports/{report['report_id']}"
    for suffix in ("", "/revisions", "/revisions/1", "/history", "/validations"):
        assert domain_client.get(base + suffix).status_code == 404
    assert domain_client.put(path(report) + "/results", json=payload(3)).status_code == 403
    assert domain_client.get("/api/v1/assignments").json()["total"] == 1
    assert domain_client.get(f"/api/v1/elections/{ELECTION}/polling-stations").json()["total"] == 1
    with Session(domain_engine) as session, session.begin():
        session.execute(delete(AgentAssignment).where(AgentAssignment.user_id == other))
    assert domain_client.get(f"/api/v1/elections/{ELECTION}/polling-stations").json()["total"] == 0


@pytest.mark.parametrize("role", ["ADMIN", "AGENT"])
def test_only_validator_can_review_and_decide(domain_client, role):
    report = submitted(domain_client)
    as_role(domain_client, role)
    assert (
        domain_client.post(path(report) + "/review", json={"expected_version": 3}).status_code
        == 403
    )
    assert (
        domain_client.post(
            path(report) + "/decision", json={"expected_version": 3, "decision": "APPROVED"}
        ).status_code
        == 403
    )


@pytest.mark.parametrize("decision", ["APPROVED", "REJECTED"])
def test_human_review_decision_and_revision_history(domain_client, decision):
    report = draft(domain_client)
    as_role(domain_client, "VALIDATOR")
    assert domain_client.get("/api/v1/reports").json()["total"] == 0
    assert domain_client.get(path(report)).status_code == 404
    as_role(domain_client, "AGENT")
    assert domain_client.put(path(report) + "/results", json=payload()).status_code == 200
    assert (
        domain_client.post(path(report) + "/submit", json={"expected_version": 2}).status_code
        == 200
    )
    as_role(domain_client, "VALIDATOR")
    base = path(report)
    assert (
        domain_client.post(
            base + "/decision",
            json={"expected_version": 3, "decision": decision, "reason": "Contrôle fictif"},
        ).status_code
        == 409
    )
    response = domain_client.post(base + "/review", json={"expected_version": 3})
    assert response.status_code == 200 and response.json()["status"] == "PENDING_VALIDATION"
    assert (
        domain_client.post(
            base + "/decision", json={"expected_version": 4, "decision": "REJECTED"}
        ).status_code
        == 422
    )
    response = domain_client.post(
        base + "/decision",
        json={"expected_version": 4, "decision": decision, "reason": "Contrôle fictif"},
    )
    assert response.status_code == 200 and response.json()["status"] == decision
    assert response.json()["edit_version"] == 5
    assert (
        domain_client.post(
            base + "/decision", json={"expected_version": 5, "decision": decision, "reason": "Bis"}
        ).status_code
        == 409
    )
    validations = domain_client.get(f"/api/v1/reports/{report['report_id']}/validations").json()[
        "items"
    ]
    assert len(validations) == 1 and validations[0]["validator_id"] == str(
        DEMO_USERS["demo-validator"]
    )
    as_role(domain_client, "AGENT")
    response = domain_client.post(
        base + "/revise", json={"expected_version": 5, "reason": "Correction fictive"}
    )
    assert response.status_code == (201 if decision == "REJECTED" else 409)


def test_no_self_validation_after_role_change(domain_client, domain_engine):
    report = submitted(domain_client)
    with Session(domain_engine) as session, session.begin():
        session.execute(update(UserRole).where(UserRole.user_id == ACTOR).values(role="VALIDATOR"))
    assert (
        domain_client.post(path(report) + "/review", json={"expected_version": 3}).status_code
        == 403
    )


def test_approval_rechecks_totals_and_cannot_review_obsolete_revision(domain_client, domain_engine):
    report = submitted(domain_client)
    as_role(domain_client, "VALIDATOR")
    assert (
        domain_client.post(path(report) + "/review", json={"expected_version": 3}).status_code
        == 200
    )
    with Session(domain_engine) as session, session.begin():
        from app.domain_models import ReportResult

        session.execute(
            update(ReportResult)
            .where(ReportResult.revision_id == UUID(report["id"]))
            .values(votes=0)
        )
    assert (
        domain_client.post(
            path(report) + "/decision", json={"expected_version": 4, "decision": "APPROVED"}
        ).status_code
        == 422
    )
    assert domain_client.get(path(report)).json()["status"] == "PENDING_VALIDATION"


def test_concurrent_decisions_one_winner(domain_client, domain_engine):
    report = submitted(domain_client)
    as_role(domain_client, "VALIDATOR")
    assert (
        domain_client.post(path(report) + "/review", json={"expected_version": 3}).status_code
        == 200
    )
    token = domain_client.tokens["VALIDATOR"]

    def attempt(decision):
        with TestClient(create_app(Settings(app_env="test"), engine=domain_engine)) as client:
            return client.post(
                path(report) + "/decision",
                headers={"Authorization": "Bearer " + token},
                json={
                    "expected_version": 4,
                    "decision": decision,
                    "reason": "Décision concurrente fictive",
                },
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(attempt, ["APPROVED", "REJECTED"])) == [200, 409]


class MemorySms:
    def __init__(self):
        self.messages = {}

    def send(self, recipient, challenge_id, code):
        self.messages[str(challenge_id)] = code


@pytest.fixture
def otp_client(domain_engine):
    with Session(domain_engine) as session, session.begin():
        seed_citizen(session)
    settings = Settings(
        app_env="test",
        citizen_otp_enabled=True,
        otp_hmac_key="test-only-hmac-secret-at-least-32-characters",
    )
    app = create_app(settings, engine=domain_engine)
    app.state.sms_sender = MemorySms()
    with TestClient(app) as client:
        yield client


def otp_request(client, cin="DEMO-CIN-0001"):
    response = client.post("/api/v1/auth/citizen/request-otp", json={"cin": cin})
    assert response.status_code == 202, response.text
    assert set(response.json()) == {"challenge_id", "message"}
    return response.json()["challenge_id"]


def otp_verify(client, challenge, code):
    return client.post(
        "/api/v1/auth/citizen/verify-otp", json={"challenge_id": challenge, "code": code}
    )


def test_citizen_otp_single_use_and_private_scope(otp_client, domain_engine):
    challenge = otp_request(otp_client)
    code = otp_client.app.state.sms_sender.messages[challenge]
    with Session(domain_engine) as session:
        row = session.get(OtpChallenge, UUID(challenge))
        assert row.code_digest != code and len(row.code_digest) == 64
    response = otp_verify(otp_client, challenge, code)
    assert response.status_code == 200
    assert otp_verify(otp_client, challenge, code).status_code == 401
    use_token(otp_client, response.json()["access_token"])
    assert otp_client.get("/api/v1/auth/me").json()["role"] == "CITIZEN"
    assert otp_client.get("/api/v1/citizen/polling-station").json()["id"] == STATION
    for endpoint in (
        "/reports",
        "/accounts",
        "/elections",
        "/assignments",
        "/audit",
        "/user-references",
    ):
        assert otp_client.get("/api/v1" + endpoint).status_code == 403


def test_otp_expiry_attempts_and_resend(otp_client, domain_engine):
    old = otp_request(otp_client)
    challenge = otp_request(otp_client)
    assert (
        otp_verify(otp_client, old, otp_client.app.state.sms_sender.messages[old]).status_code
        == 401
    )
    code = otp_client.app.state.sms_sender.messages[challenge]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert otp_verify(otp_client, challenge, wrong).status_code == 401
    assert otp_verify(otp_client, challenge, code).status_code == 401
    challenge = otp_request(otp_client)
    with Session(domain_engine) as session, session.begin():
        session.get(OtpChallenge, UUID(challenge)).expires_at = now() - timedelta(seconds=1)
    assert (
        otp_verify(
            otp_client, challenge, otp_client.app.state.sms_sender.messages[challenge]
        ).status_code
        == 401
    )
    assert (
        otp_client.post(
            "/api/v1/auth/citizen/request-otp", json={"cin": "DEMO-CIN-0001"}
        ).status_code
        == 429
    )


def test_unknown_citizen_and_disabled_otp(otp_client, domain_client):
    known = otp_client.post(
        "/api/v1/auth/citizen/request-otp", json={"cin": "DEMO-CIN-0001"}
    ).json()
    unknown = otp_client.post(
        "/api/v1/auth/citizen/request-otp", json={"cin": "DEMO-CIN-UNKNOWN"}
    ).json()
    assert known["message"] == unknown["message"]
    assert unknown["challenge_id"] not in otp_client.app.state.sms_sender.messages
    assert otp_verify(otp_client, unknown["challenge_id"], "123456").status_code == 401
    assert (
        domain_client.post(
            "/api/v1/auth/citizen/request-otp", json={"cin": "DEMO-CIN-0001"}
        ).status_code
        == 503
    )


def test_concurrent_otp_use_only_one_session(otp_client, domain_engine):
    challenge = otp_request(otp_client)
    code = otp_client.app.state.sms_sender.messages[challenge]

    def attempt(_):
        with TestClient(create_app(otp_client.app.state.settings, engine=domain_engine)) as client:
            return otp_verify(client, challenge, code).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(attempt, range(2))) == [200, 401]


def test_multiple_roles_fail_closed_and_role_change_is_immediate(domain_client, domain_engine):
    with Session(domain_engine) as session, session.begin():
        session.add(UserRole(user_id=ACTOR, role="ADMIN"))
    assert domain_client.get("/api/v1/reports").status_code == 401
    assert login(domain_client).status_code == 401


def test_reference_writes_are_audited(domain_client, domain_engine):
    as_role(domain_client, "ADMIN")
    assert (
        domain_client.post(
            "/api/v1/candidates", json={"code": "DEMO-AUDIT", "name": "Liste fictive"}
        ).status_code
        == 201
    )
    with Session(domain_engine) as session:
        row = session.scalar(select(AuthAudit).where(AuthAudit.action == "REFERENCE_CHANGED"))
        assert (
            row.actor_id == DEMO_USERS["demo-admin"] and row.resource == "POST /api/v1/candidates"
        )
