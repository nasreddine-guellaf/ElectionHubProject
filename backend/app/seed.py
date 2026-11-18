"""Chargement explicite et idempotent de bureaux entièrement fictifs."""

import json
from pathlib import Path
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import ROOT, Settings
from app.database import create_db_engine
from app.models import PollingStation


def seed_stations(session: Session, path: Path) -> int:
    records = json.loads(path.read_text(encoding="utf-8"))
    for record in records:
        record["id"] = UUID(record["id"])
        if not record["code"].startswith("DEMO-"):
            raise ValueError("Seuls les bureaux fictifs DEMO sont autorisés.")
    statement = (
        insert(PollingStation)
        .values(records)
        .on_conflict_do_nothing(index_elements=["code"])
        .returning(PollingStation.id)
    )
    return len(session.scalars(statement).all())


def main() -> None:
    engine = create_db_engine(Settings())
    try:
        with Session(engine) as session, session.begin():
            count = seed_stations(session, ROOT / "database/seeds/polling_stations.json")
        print(f"Données de démonstration : {count} bureau(x) fictif(s) ajouté(s).")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
