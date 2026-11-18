import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select, update

from app.auth_models import Citizen, OtpChallenge
from app.auth_schemas import OtpRequest, OtpRequested, OtpVerify, TokenRead
from app.domain_models import UserReference
from app.domain_service import require
from app.models import PollingStation
from app.schemas import PollingStationRead
from app.security import Authenticated, Db, audit, effective_role, issue_session, now, throttle

router = APIRouter(prefix="/api/v1", tags=["Citoyen — OTP fictif local"])


class LocalSmsSender:
    """Simulateur local uniquement ; aucun appel réseau, aucune journalisation de code."""

    def __init__(self, directory: Path):
        self.directory = directory

    def send(self, recipient: str, challenge_id, code: str):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.directory / f"{challenge_id}.json"
        with path.open("x", encoding="utf-8") as output:
            json.dump({"recipient": recipient, "code": code, "synthetic": True}, output)
        path.chmod(0o600)


def otp_settings(request):
    settings = request.app.state.settings
    if not settings.citizen_otp_enabled:
        raise HTTPException(503, "La simulation OTP locale n'est pas activée.")
    return settings


def code_digest(settings, challenge_id, code):
    return hmac.new(
        settings.otp_hmac_key.get_secret_value().encode(),
        f"{challenge_id}:{code}".encode(),
        hashlib.sha256,
    ).hexdigest()


@router.post("/auth/citizen/request-otp", response_model=OtpRequested, status_code=202)
def request_otp(data: OtpRequest, request: Request, session: Db):
    settings = otp_settings(request)
    throttle(session, request, "otp-request", data.cin, per_identity=3, seconds=300)
    citizen = session.scalar(
        select(Citizen).where(Citizen.synthetic_cin == data.cin).with_for_update()
    )
    user = session.get(UserReference, citizen.user_id) if citizen else None
    eligible = user is not None and user.active and effective_role(session, user.id) == "CITIZEN"
    challenge_id = uuid4()
    code = f"{secrets.randbelow(1_000_000):06d}"
    if eligible:
        session.execute(
            update(OtpChallenge).where(OtpChallenge.user_id == user.id).values(consumed=True)
        )
    challenge = OtpChallenge(
        id=challenge_id,
        user_id=user.id if eligible else None,
        code_digest=code_digest(settings, challenge_id, code),
        expires_at=now() + timedelta(minutes=5),
    )
    session.add(challenge)
    session.commit()
    if eligible:
        try:
            request.app.state.sms_sender.send(citizen.mock_recipient, challenge_id, code)
        except OSError:
            challenge.consumed = True
            session.commit()
            raise HTTPException(503, "Le simulateur SMS est indisponible.") from None
    return OtpRequested(challenge_id=challenge_id)


@router.post("/auth/citizen/verify-otp", response_model=TokenRead)
def verify_otp(data: OtpVerify, request: Request, session: Db):
    settings = otp_settings(request)
    throttle(session, request, "otp-verify", str(data.challenge_id), per_identity=10, seconds=300)
    challenge = session.scalar(
        select(OtpChallenge).where(OtpChallenge.id == data.challenge_id).with_for_update()
    )
    valid = (
        challenge is not None
        and not challenge.consumed
        and challenge.expires_at > now()
        and challenge.attempts < 5
    )
    if not valid:
        raise HTTPException(401, "Code invalide ou expiré.")
    challenge.attempts += 1
    user = session.get(UserReference, challenge.user_id) if challenge.user_id else None
    if not hmac.compare_digest(
        challenge.code_digest, code_digest(settings, challenge.id, data.code)
    ) or (user is None or not user.active or effective_role(session, user.id) != "CITIZEN"):
        if challenge.attempts >= 5:
            challenge.consumed = True
        audit(session, "OTP_FAILED")
        session.commit()
        raise HTTPException(401, "Code invalide ou expiré.")
    challenge.consumed = True
    token = issue_session(session, user.id, settings.session_ttl_seconds)
    audit(session, "OTP_LOGIN", user.id, user.id)
    session.commit()
    return token


@router.get("/citizen/polling-station", response_model=PollingStationRead)
def citizen_station(actor: Authenticated, session: Db):
    if actor.role != "CITIZEN":
        raise HTTPException(403, "Accès réservé au citoyen authentifié.")
    citizen = require(session, Citizen, actor.id)
    return require(session, PollingStation, citizen.polling_station_id)
