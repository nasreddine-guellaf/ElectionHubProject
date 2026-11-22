"""API de recette UI isolée : schéma jetable, mots de passe exclusivement de test.

Arrêter avec Ctrl+C pour supprimer uniquement le schéma généré par ce processus.
Les comptes demo-agent/admin/validator utilisent ui-test-password-only-2026.
Ne pas utiliser ce serveur hors de la machine locale.
"""

import sys
from pathlib import Path
from uuid import uuid4

import uvicorn
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from alembic import command
from app.auth_models import Account
from app.bootstrap_auth import DEMO_USERS, seed_citizen
from app.config import ROOT, Settings
from app.database import create_db_engine
from app.main import create_app
from app.security import hasher
from app.seed_domain import seed_domain


def main():
    schema = "ui_test_" + uuid4().hex
    settings = Settings(
        app_env="test",
        citizen_otp_enabled=True,
        otp_hmac_key=uuid4().hex + uuid4().hex,
        mock_sms_directory=ROOT / ".local/ui-sms",
    )
    admin = create_db_engine(settings)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        settings.database_url,
        hide_parameters=True,
        connect_args={"options": f"-csearch_path={schema}", "connect_timeout": 3},
    )
    try:
        with engine.begin() as connection:
            config = Config(str(ROOT / "backend/alembic.ini"))
            config.set_main_option("script_location", str(ROOT / "backend/alembic"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        with Session(engine) as session, session.begin():
            seed_domain(session)
            seed_citizen(session)
            for username, user_id in DEMO_USERS.items():
                session.add(
                    Account(
                        user_id=user_id,
                        username=username,
                        password_hash=hasher.hash("ui-test-password-only-2026"),
                    )
                )
        print("Recette UI isolée : http://127.0.0.1:8001", flush=True)
        uvicorn.run(
            create_app(settings, engine=engine),
            host="127.0.0.1",
            port=8001,
            proxy_headers=False,
            log_level="warning",
        )
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


if __name__ == "__main__":
    main()
