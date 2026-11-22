"""Bootstrap local explicite : secrets aléatoires, sans affichage ni reset implicite."""

import json
import secrets
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth_models import Account, Citizen
from app.config import ROOT, Settings
from app.database import create_db_engine
from app.domain_models import UserReference, UserRole
from app.models import PollingStation
from app.security import audit, hasher

DEMO_USERS = {
    "demo-agent": UUID("30000000-0000-4000-8000-000000000001"),
    "demo-validator": UUID("30000000-0000-4000-8000-000000000002"),
    "demo-admin": UUID("30000000-0000-4000-8000-000000000003"),
}
CITIZEN_ID = UUID("30000000-0000-4000-8000-000000000004")


def seed_citizen(session):
    station_id = UUID("00000000-0000-4000-8000-000000000001")
    if session.get(PollingStation, station_id) is None:
        raise RuntimeError("Exécutez d'abord python -m app.seed_domain.")
    if session.get(UserReference, CITIZEN_ID) is None:
        session.add(
            UserReference(id=CITIZEN_ID, code="DEMO-CITIZEN-01", display_name="Citoyen fictif 01")
        )
        session.flush()
        session.add(UserRole(user_id=CITIZEN_ID, role="CITIZEN"))
    if session.get(Citizen, CITIZEN_ID) is None:
        session.add(
            Citizen(
                user_id=CITIZEN_ID,
                synthetic_cin="DEMO-CIN-0001",
                polling_station_id=station_id,
                mock_recipient="mock://DEMO-CITIZEN-01",
            )
        )


def main():
    engine = create_db_engine(Settings())
    output = ROOT / ".local/demo-credentials.json"
    try:
        with Session(engine) as session, session.begin():
            session.execute(text("SELECT pg_advisory_xact_lock(74209104)"))
            credentials = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
            changed = False
            for username, user_id in DEMO_USERS.items():
                if session.get(UserReference, user_id) is None:
                    raise RuntimeError("Exécutez d'abord python -m app.seed_domain.")
                if session.get(Account, user_id) is not None:
                    continue
                password = secrets.token_urlsafe(24)
                session.add(
                    Account(user_id=user_id, username=username, password_hash=hasher.hash(password))
                )
                credentials[username] = password
                audit(session, "ACCOUNT_BOOTSTRAPPED", target_id=user_id)
                changed = True
            seed_citizen(session)
            session.flush()
            if changed:
                output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                output.write_text(json.dumps(credentials, indent=2) + "\n", encoding="utf-8")
                output.chmod(0o600)
        print(
            "Comptes fictifs préparés. Secrets initiaux dans .local/demo-credentials.json ; "
            "aucun reset."
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
