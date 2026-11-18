from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import delete, func, select, text

from app.auth_models import Account, AuthAudit, AuthSession
from app.auth_schemas import (
    AccountInput,
    AccountRead,
    AccountUpdate,
    AuditRead,
    LoginInput,
    PasswordChange,
    PasswordReset,
    Profile,
    TokenRead,
)
from app.domain_models import UserReference, UserRole
from app.domain_schemas import Page
from app.domain_service import require
from app.security import (
    DUMMY_HASH,
    Admin,
    Authenticated,
    Db,
    audit,
    effective_role,
    hasher,
    issue_session,
    revoke_sessions,
    throttle,
    unauthenticated,
    verify_password,
)

router = APIRouter(prefix="/api/v1", tags=["Authentification et comptes"])


@router.post("/auth/login", response_model=TokenRead)
def login(data: LoginInput, request: Request, session: Db):
    throttle(session, request, "login", data.username)
    account = session.scalar(
        select(Account).where(Account.username == data.username).with_for_update()
    )
    valid = verify_password(
        account.password_hash if account else DUMMY_HASH, data.password.get_secret_value()
    )
    user = session.get(UserReference, account.user_id) if account else None
    role = effective_role(session, user.id) if user else None
    if not valid or user is None or not user.active or role not in {"ADMIN", "AGENT", "VALIDATOR"}:
        audit(session, "LOGIN_FAILED")
        session.commit()
        raise HTTPException(401, "Identifiants invalides.", headers={"WWW-Authenticate": "Bearer"})
    if hasher.check_needs_rehash(account.password_hash):
        account.password_hash = hasher.hash(data.password.get_secret_value())
    token = issue_session(session, user.id, request.app.state.settings.session_ttl_seconds)
    audit(session, "LOGIN", user.id, user.id)
    session.commit()
    return token


@router.get("/auth/me", response_model=Profile)
def me(actor: Authenticated, session: Db):
    user = require(session, UserReference, actor.id)
    return Profile(id=user.id, display_name=user.display_name, role=actor.role)


@router.post("/auth/logout", status_code=204)
def logout(actor: Authenticated, session: Db):
    session.execute(delete(AuthSession).where(AuthSession.token_hash == actor.token_hash))
    audit(session, "LOGOUT", actor.id, actor.id)
    session.commit()
    return Response(status_code=204)


@router.post("/auth/password", status_code=204)
def change_password(data: PasswordChange, request: Request, actor: Authenticated, session: Db):
    throttle(session, request, "password", str(actor.id))
    account = session.scalar(select(Account).where(Account.user_id == actor.id).with_for_update())
    if account is None or not verify_password(
        account.password_hash, data.current_password.get_secret_value()
    ):
        raise HTTPException(400, "Le mot de passe actuel est incorrect.")
    account.password_hash = hasher.hash(data.new_password.get_secret_value())
    revoke_sessions(session, actor.id)
    audit(session, "PASSWORD_CHANGED", actor.id, actor.id)
    session.commit()
    return Response(status_code=204)


def account_view(session, account):
    user = require(session, UserReference, account.user_id)
    role = effective_role(session, user.id)
    if role is None:
        raise HTTPException(409, "La référence possède une configuration de rôle ambiguë.")
    return AccountRead(
        id=user.id,
        display_name=user.display_name,
        role=role,
        username=account.username,
        active=user.active,
    )


@router.get("/accounts", response_model=Page[AccountRead])
def accounts(
    actor: Admin,
    session: Db,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    rows = session.scalars(select(Account).order_by(Account.username).limit(limit).offset(offset))
    return Page[AccountRead](
        items=[account_view(session, row) for row in rows],
        total=session.scalar(select(func.count()).select_from(Account)),
        limit=limit,
        offset=offset,
    )


@router.post("/accounts", response_model=AccountRead, status_code=201)
def create_account(data: AccountInput, actor: Admin, session: Db):
    user = UserReference(code=data.code, display_name=data.display_name)
    session.add(user)
    session.flush()
    account = Account(
        user_id=user.id,
        username=data.username,
        password_hash=hasher.hash(data.password.get_secret_value()),
    )
    session.add_all([account, UserRole(user_id=user.id, role=data.role)])
    audit(session, "ACCOUNT_CREATED", actor.id, user.id)
    session.commit()
    return account_view(session, account)


@router.put("/accounts/{user_id}", response_model=AccountRead)
def update_account(user_id: UUID, data: AccountUpdate, actor: Admin, session: Db):
    if user_id == actor.id:
        raise HTTPException(409, "Vous ne pouvez pas modifier votre propre rôle ou activation.")
    # Sérialise les changements de rôles, y compris deux rétrogradations simultanées.
    session.execute(text("SELECT pg_advisory_xact_lock(74209103)"))
    # Le rôle appelant est revérifié après l'attente du verrou.
    if (
        effective_role(session, actor.id) != "ADMIN"
        or not require(session, UserReference, actor.id).active
    ):
        raise unauthenticated()
    account = session.scalar(select(Account).where(Account.user_id == user_id).with_for_update())
    if account is None:
        raise HTTPException(404, "Compte introuvable.")
    user = require(session, UserReference, user_id)
    remaining = session.scalar(
        select(func.count())
        .select_from(UserReference)
        .join(UserRole)
        .join(Account, Account.user_id == UserReference.id)
        .where(
            UserRole.role == "ADMIN", UserReference.active.is_(True), UserReference.id != user_id
        )
    )
    if (
        effective_role(session, user_id) == "ADMIN"
        and (not data.active or data.role != "ADMIN")
        and not remaining
    ):
        raise HTTPException(409, "Conservez au moins un administrateur actif.")
    session.execute(delete(UserRole).where(UserRole.user_id == user_id))
    session.add(UserRole(user_id=user_id, role=data.role))
    user.active = data.active
    revoke_sessions(session, user_id)
    audit(session, "ACCOUNT_UPDATED", actor.id, user_id)
    session.commit()
    return account_view(session, account)


@router.post("/accounts/{user_id}/password", status_code=204)
def reset_password(user_id: UUID, data: PasswordReset, actor: Admin, session: Db):
    if user_id == actor.id:
        raise HTTPException(
            409, "Utilisez le changement de mot de passe avec vérification du mot de passe actuel."
        )
    account = session.scalar(select(Account).where(Account.user_id == user_id).with_for_update())
    if account is None:
        raise HTTPException(404, "Compte introuvable.")
    account.password_hash = hasher.hash(data.new_password.get_secret_value())
    revoke_sessions(session, user_id)
    audit(session, "PASSWORD_RESET", actor.id, user_id)
    session.commit()
    return Response(status_code=204)


@router.get("/audit", response_model=Page[AuditRead])
def audit_history(
    actor: Admin,
    session: Db,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    rows = session.scalars(
        select(AuthAudit).order_by(AuthAudit.created_at, AuthAudit.id).limit(limit).offset(offset)
    )
    return Page[AuditRead](
        items=[AuditRead.model_validate(row) for row in rows],
        total=session.scalar(select(func.count()).select_from(AuthAudit)),
        limit=limit,
        offset=offset,
    )
