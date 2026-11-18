from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.auth_schemas import DecisionInput
from app.domain_models import Report, ReportRevision, ReportValidation
from app.domain_schemas import ExpectedVersion, ResultsInput, RevisionRead
from app.domain_service import event, validate_results
from app.security import Db, Validator, audit

router = APIRouter(prefix="/api/v1/reports", tags=["Validation humaine des PV"])


def locked_revision(session, report_id, number, expected_version, actor):
    report = session.scalar(select(Report).where(Report.id == report_id).with_for_update())
    if report is None:
        raise HTTPException(404, "Dossier PV introuvable.")
    if report.created_by == actor.id:
        raise HTTPException(403, "Vous ne pouvez pas valider votre propre dossier.")
    if report.current_revision != number:
        raise HTTPException(409, "Révision remplacée par une correction.")
    revision = session.scalar(
        select(ReportRevision)
        .where(ReportRevision.report_id == report_id, ReportRevision.revision_number == number)
        .with_for_update()
    )
    if revision is None:
        raise HTTPException(404, "Révision introuvable.")
    if revision.edit_version != expected_version:
        raise HTTPException(409, "Version obsolète : rechargez le PV.")
    return revision


def check_coherence(session, revision):
    if not revision.results:
        raise HTTPException(422, "Le PV ne contient aucun résultat.")
    validate_results(
        session,
        revision,
        ResultsInput(
            expected_version=revision.edit_version,
            ballots_cast=revision.ballots_cast,
            valid_votes=revision.valid_votes,
            blank_votes=revision.blank_votes,
            invalid_votes=revision.invalid_votes,
            results=[
                {"candidate_id": row.candidate_id, "votes": row.votes} for row in revision.results
            ],
        ),
    )


@router.post("/{report_id}/revisions/{number}/review", response_model=RevisionRead)
def start_review(
    report_id: UUID, number: int, data: ExpectedVersion, actor: Validator, session: Db
):
    revision = locked_revision(session, report_id, number, data.expected_version, actor)
    if revision.status != "SUBMITTED":
        raise HTTPException(409, "Seul un PV soumis peut entrer en validation.")
    check_coherence(session, revision)
    revision.status = "PENDING_VALIDATION"
    revision.edit_version += 1
    event(session, revision, actor.id, "REVIEW_STARTED")
    audit(session, "REVIEW_STARTED", actor.id)
    session.commit()
    return revision


@router.post("/{report_id}/revisions/{number}/decision", response_model=RevisionRead)
def decide(report_id: UUID, number: int, data: DecisionInput, actor: Validator, session: Db):
    revision = locked_revision(session, report_id, number, data.expected_version, actor)
    if revision.status != "PENDING_VALIDATION":
        raise HTTPException(409, "La décision exige un PV en cours de validation humaine.")
    if data.decision == "APPROVED":
        check_coherence(session, revision)
    revision.status = data.decision
    revision.edit_version += 1
    session.add(
        ReportValidation(
            revision_id=revision.id,
            validator_id=actor.id,
            decision=data.decision,
            reason=data.reason,
        )
    )
    event(session, revision, actor.id, data.decision, data.reason)
    audit(session, "REPORT_" + data.decision, actor.id)
    session.commit()
    return revision
