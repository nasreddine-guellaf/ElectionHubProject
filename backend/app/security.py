"""Sessions opaques, hachage des mots de passe et contrôle d'accès serveur."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.auth_models import AuthAudit, AuthSession, RateLimit
from app.auth_schemas import TokenRead
from app.database import get_session
from app.domain_models import AgentAssignment, Report, ReportRevision, UserReference, UserRole

Db = Annotated[Session, Depends(get_session)]
bearer = HTTPBearer(auto_error=False)
hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1)
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


def now():
    return datetime.now(UTC)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def verify_password(encoded: str, password: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def audit(session: Session, action: str, actor_id=None, target_id=None, resource=None):
    session.add(AuthAudit(action=action, actor_id=actor_id, target_id=target_id, resource=resource))


def effective_role(session: Session, user_id: UUID) -> str | None:
    roles = list(session.scalars(select(UserRole.role).where(UserRole.user_id == user_id)))
    return roles[0] if len(roles) == 1 else None


def issue_session(session: Session, user_id: UUID, ttl: int) -> TokenRead:
    token = secrets.token_urlsafe(32)
    expires = now() + timedelta(seconds=ttl)
    session.add(AuthSession(token_hash=digest(token), user_id=user_id, expires_at=expires))
    return TokenRead(access_token=token, expires_at=expires)


def revoke_sessions(session: Session, user_id: UUID):
    session.execute(delete(AuthSession).where(AuthSession.user_id == user_id))


def throttle(
    session: Session,
    request: Request,
    scope: str,
    identity: str,
    *,
    per_identity: int = 5,
    per_ip: int = 30,
    seconds: int = 900,
):
    """Compteurs atomiques partagés. Ne jamais appeler après une mutation métier."""
    instant = now()
    blocked = False
    ip = request.client.host if request.client else "unknown"
    for name, limit in ((f"{scope}:ip:{ip}", per_ip), (f"{scope}:id:{identity}", per_identity)):
        key = digest(name)
        expired = RateLimit.expires_at <= instant
        statement = (
            insert(RateLimit)
            .values(key=key, attempts=1, expires_at=instant + timedelta(seconds=seconds))
            .on_conflict_do_update(
                index_elements=["key"],
                set_={
                    "attempts": case((expired, 1), else_=RateLimit.attempts + 1),
                    "expires_at": case(
                        (expired, instant + timedelta(seconds=seconds)), else_=RateLimit.expires_at
                    ),
                },
            )
            .returning(RateLimit.attempts)
        )
        blocked = session.scalar(statement) > limit or blocked
    session.commit()  # Un échec de login ne doit pas annuler le compteur.
    if blocked:
        raise HTTPException(
            429, "Trop de tentatives. Réessayez plus tard.", headers={"Retry-After": str(seconds)}
        )


@dataclass(frozen=True)
class Principal:
    id: UUID
    role: str
    token_hash: str


def unauthenticated():
    return HTTPException(
        401, "Authentification requise ou session expirée.", headers={"WWW-Authenticate": "Bearer"}
    )


def current_principal(
    session: Db,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    if credentials is None or not 40 <= len(credentials.credentials) <= 128:
        raise unauthenticated()
    key = digest(credentials.credentials)
    login = session.get(AuthSession, key)
    if login is None or login.expires_at <= now():
        raise unauthenticated()
    user = session.get(UserReference, login.user_id)
    role = effective_role(session, login.user_id)
    if user is None or not user.active or role is None:
        raise unauthenticated()
    return Principal(user.id, role, key)


Authenticated = Annotated[Principal, Depends(current_principal)]


def roles(*allowed):
    def check(actor: Authenticated) -> Principal:
        if actor.role not in allowed:
            raise HTTPException(403, "Cette action n'est pas autorisée pour votre rôle.")
        return actor

    return check


Admin = Annotated[Principal, Depends(roles("ADMIN"))]
Validator = Annotated[Principal, Depends(roles("VALIDATOR"))]


def agent_actor(actor: Annotated[Principal, Depends(roles("AGENT"))]) -> UUID:
    return actor.id


def staff_access(request: Request, actor: Authenticated, session: Db):
    if actor.role not in {"ADMIN", "AGENT", "VALIDATOR"}:
        raise HTTPException(403, "Accès réservé aux comptes opérationnels.")
    if request.method not in {"GET", "HEAD"} and not request.url.path.startswith("/api/v1/reports"):
        if actor.role != "ADMIN":
            raise HTTPException(403, "La gestion des référentiels exige le rôle administrateur.")
        session.info["domain_audit"] = (actor.id, request.method + " " + request.url.path)


def report_conditions(actor: Principal):
    if actor.role == "ADMIN":
        return []
    if actor.role == "AGENT":
        assigned = (
            select(AgentAssignment.user_id)
            .where(
                AgentAssignment.user_id == actor.id,
                AgentAssignment.election_id == Report.election_id,
                AgentAssignment.polling_station_id == Report.polling_station_id,
            )
            .exists()
        )
        return [Report.created_by == actor.id, assigned]
    if actor.role == "VALIDATOR":
        submitted = (
            select(ReportRevision.id)
            .where(
                ReportRevision.report_id == Report.id,
                ReportRevision.revision_number == Report.current_revision,
                ReportRevision.status != "DRAFT",
            )
            .exists()
        )
        return [submitted]
    raise HTTPException(403, "Accès aux PV interdit.")


def accessible_report(session: Session, report_id: UUID, actor: Principal) -> Report:
    report = session.scalar(select(Report).where(Report.id == report_id, *report_conditions(actor)))
    if report is None:
        raise HTTPException(404, "Dossier PV introuvable.")
    return report
