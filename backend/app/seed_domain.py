"""Jeu de démonstration phase 2, sans approbation et sans écrasement d'un dossier existant."""

import json
from datetime import date
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import ROOT, Settings
from app.database import create_db_engine
from app.domain_models import (
    AgentAssignment,
    Candidate,
    Election,
    ElectionCandidate,
    ElectionStation,
    Report,
    UserReference,
    UserRole,
)
from app.domain_schemas import DraftInput, ResultsInput
from app.domain_service import create_draft, submit_report, update_results
from app.models import PollingStation
from app.seed import seed_stations


def seed_domain(session: Session, *, include_reports: bool = True) -> None:
    # Sérialise uniquement les exécutions de ce seed dans cette base.
    session.execute(text("SELECT pg_advisory_xact_lock(74209102)"))
    seed_stations(session, ROOT / "database/seeds/polling_stations.json")
    data = json.loads((ROOT / "database/seeds/domain.json").read_text(encoding="utf-8"))

    def insert_once(model, values):
        session.execute(insert(model).values(**values).on_conflict_do_nothing())

    election = data["election"]
    election["id"] = UUID(election["id"])
    for name in ("start_date", "end_date"):
        election[name] = date.fromisoformat(election[name])
    insert_once(Election, election)
    election_id = election["id"]
    for candidate in data["candidates"]:
        candidate["id"] = UUID(candidate["id"])
        insert_once(Candidate, candidate)
        insert_once(
            ElectionCandidate, {"election_id": election_id, "candidate_id": candidate["id"]}
        )
    for user in data["users"]:
        role = user.pop("role")
        user["id"] = UUID(user["id"])
        insert_once(UserReference, {**user, "active": True})
        if session.scalar(select(UserRole.role).where(UserRole.user_id == user["id"])) is None:
            insert_once(UserRole, {"user_id": user["id"], "role": role})
    actor_id = data["users"][0]["id"]
    station_ids = [UUID(f"00000000-0000-4000-8000-{number:012d}") for number in range(1, 4)]
    for station_id in station_ids:
        station = session.get(PollingStation, station_id)
        insert_once(
            ElectionStation,
            {
                "election_id": election_id,
                "polling_station_id": station_id,
                "registered_voters": station.registered_voters,
            },
        )
        insert_once(
            AgentAssignment,
            {"election_id": election_id, "polling_station_id": station_id, "user_id": actor_id},
        )
    if not include_reports:
        return
    for item in data["reports"]:
        station_id = UUID(item["polling_station_id"])
        if (
            session.scalar(
                select(Report.id).where(
                    Report.election_id == election_id, Report.polling_station_id == station_id
                )
            )
            is not None
        ):
            continue
        revision = create_draft(
            session, DraftInput(election_id=election_id, polling_station_id=station_id), actor_id
        )
        valid = sum(item["votes"])
        results = ResultsInput(
            expected_version=1,
            ballots_cast=valid + item["blank_votes"] + item["invalid_votes"],
            valid_votes=valid,
            blank_votes=item["blank_votes"],
            invalid_votes=item["invalid_votes"],
            results=[
                {"candidate_id": candidate["id"], "votes": votes}
                for candidate, votes in zip(data["candidates"], item["votes"], strict=True)
            ],
        )
        update_results(session, revision.report_id, 1, results, actor_id)
        if item["submit"]:
            submit_report(session, revision.report_id, 1, 2, actor_id)


def main():
    engine = create_db_engine(Settings())
    try:
        with Session(engine) as session, session.begin():
            seed_domain(session)
        print("Données fictives phase 2 chargées ; aucun résultat approuvé ou publié.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
