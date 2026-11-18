"""Transactions métier indépendantes de l'authentification et des fournisseurs cloud."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain_models import (
    AgentAssignment,
    Election,
    ElectionCandidate,
    ElectionStation,
    Report,
    ReportEvent,
    ReportResult,
    ReportRevision,
    ReportStatus,
    UserReference,
)
from app.domain_schemas import DraftInput, ResultsInput


def require(session: Session, model, identity):
    instance = session.get(model, identity)
    if instance is None:
        raise HTTPException(404, "Ressource introuvable.")
    return instance


def lock_election(session: Session, election_id: UUID, *, mutable: bool = False) -> Election:
    election = session.scalar(select(Election).where(Election.id == election_id).with_for_update())
    if election is None:
        raise HTTPException(404, "Scrutin introuvable.")
    if mutable and session.scalar(
        select(Report.id).where(Report.election_id == election_id).limit(1)
    ):
        raise HTTPException(409, "Le référentiel est figé dès le premier dossier PV.")
    return election


def check_assignment(session: Session, election_id: UUID, station_id: UUID, actor_id: UUID):
    user = require(session, UserReference, actor_id)
    if not user.active or session.get(AgentAssignment, (election_id, station_id, actor_id)) is None:
        raise HTTPException(403, "Acteur inactif ou non affecté à ce bureau pour ce scrutin.")


def event(session: Session, revision: ReportRevision, actor_id: UUID, action: str, note: str = ""):
    session.add(
        ReportEvent(
            revision_id=revision.id,
            actor_id=actor_id,
            action=action,
            edit_version=revision.edit_version,
            note=note,
        )
    )


def create_draft(session: Session, data: DraftInput, actor_id: UUID) -> ReportRevision:
    election = lock_election(session, data.election_id)
    station = require(session, ElectionStation, (data.election_id, data.polling_station_id))
    check_assignment(session, data.election_id, data.polling_station_id, actor_id)
    if session.scalar(
        select(Report.id).where(
            Report.election_id == data.election_id,
            Report.polling_station_id == data.polling_station_id,
        )
    ):
        raise HTTPException(409, "Un dossier existe déjà pour ce scrutin et ce bureau.")
    if (
        session.scalar(
            select(ElectionCandidate.candidate_id)
            .where(ElectionCandidate.election_id == data.election_id)
            .limit(1)
        )
        is None
    ):
        raise HTTPException(422, "Le scrutin doit posséder au moins un candidat.")
    report = Report(**data.model_dump(), created_by=actor_id)
    session.add(report)
    session.flush()
    revision = ReportRevision(
        report_id=report.id,
        election_id=report.election_id,
        revision_number=1,
        created_by=actor_id,
        registered_voters=station.registered_voters,
        enforce_ballot_equation=election.enforce_ballot_equation,
    )
    session.add(revision)
    session.flush()
    event(session, revision, actor_id, "CREATED")
    return revision


def lock_current(
    session: Session, report_id: UUID, revision_number: int, expected_version: int, actor_id: UUID
) -> tuple[Report, ReportRevision]:
    report = session.scalar(select(Report).where(Report.id == report_id).with_for_update())
    if report is None:
        raise HTTPException(404, "Dossier PV introuvable.")
    check_assignment(session, report.election_id, report.polling_station_id, actor_id)
    if report.created_by != actor_id:
        raise HTTPException(403, "Seul l'auteur peut modifier ce dossier dans le mode local.")
    if report.current_revision != revision_number:
        raise HTTPException(409, "Cette révision n'est plus la révision courante.")
    revision = session.scalar(
        select(ReportRevision)
        .where(
            ReportRevision.report_id == report_id, ReportRevision.revision_number == revision_number
        )
        .with_for_update()
    )
    if revision is None:
        raise HTTPException(404, "Révision introuvable.")
    if revision.edit_version != expected_version:
        raise HTTPException(409, "Version obsolète : rechargez le PV avant de réessayer.")
    return report, revision


def validate_results(session: Session, revision: ReportRevision, data: ResultsInput):
    expected = set(
        session.scalars(
            select(ElectionCandidate.candidate_id).where(
                ElectionCandidate.election_id == revision.election_id
            )
        )
    )
    supplied = [item.candidate_id for item in data.results]
    if len(supplied) != len(set(supplied)):
        raise HTTPException(422, "Un candidat ne peut apparaître deux fois.")
    if not expected or set(supplied) != expected:
        raise HTTPException(422, "Saisissez exactement tous les candidats de ce scrutin.")
    if sum(item.votes for item in data.results) != data.valid_votes:
        raise HTTPException(422, "La somme des résultats doit égaler les voix valides.")
    if data.valid_votes > data.ballots_cast or data.ballots_cast > revision.registered_voters:
        raise HTTPException(422, "Voix valides ≤ bulletins déposés ≤ inscrits est obligatoire.")
    if data.blank_votes > data.ballots_cast or data.invalid_votes > data.ballots_cast:
        raise HTTPException(
            422, "Les blancs et les nuls ne peuvent dépasser les bulletins déposés."
        )
    if revision.enforce_ballot_equation and (
        data.valid_votes + data.blank_votes + data.invalid_votes != data.ballots_cast
    ):
        raise HTTPException(422, "Voix valides + blancs + nuls doit égaler les bulletins déposés.")


def update_results(
    session: Session, report_id: UUID, number: int, data: ResultsInput, actor_id: UUID
) -> ReportRevision:
    _, revision = lock_current(session, report_id, number, data.expected_version, actor_id)
    if revision.status != ReportStatus.DRAFT:
        raise HTTPException(409, "Seul un brouillon peut être modifié.")
    validate_results(session, revision, data)
    # Le flush intermédiaire évite un conflit de PK lors du remplacement des mêmes candidats.
    revision.results.clear()
    session.flush()
    revision.results = [
        ReportResult(
            election_id=revision.election_id, candidate_id=item.candidate_id, votes=item.votes
        )
        for item in data.results
    ]
    for name in ("ballots_cast", "valid_votes", "blank_votes", "invalid_votes"):
        setattr(revision, name, getattr(data, name))
    revision.edit_version += 1
    event(session, revision, actor_id, "RESULTS_UPDATED")
    session.flush()
    return revision


def submit_report(
    session: Session, report_id: UUID, number: int, expected_version: int, actor_id: UUID
) -> ReportRevision:
    _, revision = lock_current(session, report_id, number, expected_version, actor_id)
    if revision.status != ReportStatus.DRAFT:
        raise HTTPException(409, "La soumission exige un brouillon courant.")
    if not revision.results:
        raise HTTPException(422, "Saisissez les résultats avant de soumettre le PV.")
    data = ResultsInput(
        expected_version=expected_version,
        ballots_cast=revision.ballots_cast,
        valid_votes=revision.valid_votes,
        blank_votes=revision.blank_votes,
        invalid_votes=revision.invalid_votes,
        results=[
            {"candidate_id": row.candidate_id, "votes": row.votes} for row in revision.results
        ],
    )
    validate_results(session, revision, data)
    revision.status = ReportStatus.SUBMITTED
    revision.submitted_at = datetime.now(UTC)
    revision.edit_version += 1
    event(session, revision, actor_id, "SUBMITTED")
    session.flush()
    return revision


def revise_report(
    session: Session,
    report_id: UUID,
    number: int,
    expected_version: int,
    reason: str,
    actor_id: UUID,
) -> ReportRevision:
    report, previous = lock_current(session, report_id, number, expected_version, actor_id)
    if previous.status not in (
        ReportStatus.SUBMITTED,
        ReportStatus.REJECTED,
        ReportStatus.PROCESSING_FAILED,
    ):
        raise HTTPException(409, "Cet état ne permet pas la création d'une correction.")
    revision = ReportRevision(
        report_id=report.id,
        election_id=report.election_id,
        revision_number=previous.revision_number + 1,
        created_by=actor_id,
        revision_reason=reason,
        registered_voters=previous.registered_voters,
        enforce_ballot_equation=previous.enforce_ballot_equation,
        ballots_cast=previous.ballots_cast,
        valid_votes=previous.valid_votes,
        blank_votes=previous.blank_votes,
        invalid_votes=previous.invalid_votes,
        results=[
            ReportResult(
                election_id=previous.election_id, candidate_id=row.candidate_id, votes=row.votes
            )
            for row in previous.results
        ],
    )
    report.current_revision = revision.revision_number
    session.add(revision)
    session.flush()
    event(session, revision, actor_id, "REVISED", reason)
    return revision
