from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_session
from app.domain_models import (
    AgentAssignment,
    Candidate,
    Election,
    ElectionCandidate,
    ElectionStation,
    Report,
    ReportEvent,
    ReportRevision,
    ReportValidation,
    UserReference,
    UserRole,
)
from app.domain_schemas import (
    AssignmentInput,
    AssignmentRead,
    CandidateInput,
    CandidateRead,
    DraftInput,
    ElectionCandidateInput,
    ElectionCandidateRead,
    ElectionInput,
    ElectionRead,
    ElectionStationInput,
    ElectionStationRead,
    EventRead,
    ExpectedVersion,
    Page,
    ReportRead,
    ResultsInput,
    RevisionInput,
    RevisionRead,
    UserRead,
    ValidationRead,
)
from app.domain_service import (
    create_draft,
    lock_election,
    require,
    revise_report,
    submit_report,
    update_results,
)
from app.models import PollingStation
from app.security import (
    Admin,
    Authenticated,
    accessible_report,
    agent_actor,
    audit,
    report_conditions,
    staff_access,
)

Db = Annotated[Session, Depends(get_session)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


Actor = Annotated[UUID, Depends(agent_actor)]
router = APIRouter(
    prefix="/api/v1",
    tags=["Domaine électoral — accès selon rôle"],
    dependencies=[Depends(staff_access)],
)


def page(session, model, schema, limit, offset, *conditions, order=None):
    rows = session.scalars(
        select(model)
        .where(*conditions)
        .order_by(order if order is not None else model.id)
        .limit(limit)
        .offset(offset)
    ).all()
    total = session.scalar(select(func.count()).select_from(model).where(*conditions))
    return Page[schema](
        items=[schema.model_validate(row) for row in rows], total=total, limit=limit, offset=offset
    )


def commit_domain(session):
    if "domain_audit" in session.info:
        actor_id, resource = session.info["domain_audit"]
        audit(session, "REFERENCE_CHANGED", actor_id, resource=resource)
    session.commit()


def persist(session, instance):
    session.add(instance)
    commit_domain(session)
    session.refresh(instance)
    return instance


@router.get("/elections", response_model=Page[ElectionRead])
def elections(session: Db, limit: Limit = 20, offset: Offset = 0):
    return page(session, Election, ElectionRead, limit, offset, order=Election.code)


@router.post("/elections", response_model=ElectionRead, status_code=201)
def add_election(data: ElectionInput, session: Db):
    return persist(session, Election(**data.model_dump()))


@router.get("/elections/{election_id}", response_model=ElectionRead)
def election(election_id: UUID, session: Db):
    return require(session, Election, election_id)


@router.put("/elections/{election_id}", response_model=ElectionRead)
def replace_election(election_id: UUID, data: ElectionInput, session: Db):
    instance = lock_election(session, election_id, mutable=True)
    for name, value in data.model_dump().items():
        setattr(instance, name, value)
    return persist(session, instance)


@router.delete("/elections/{election_id}", status_code=204)
def delete_election(election_id: UUID, session: Db):
    session.delete(lock_election(session, election_id, mutable=True))
    commit_domain(session)
    return Response(status_code=204)


@router.get("/candidates", response_model=Page[CandidateRead])
def candidates(session: Db, limit: Limit = 20, offset: Offset = 0):
    return page(session, Candidate, CandidateRead, limit, offset, order=Candidate.code)


@router.post("/candidates", response_model=CandidateRead, status_code=201)
def add_candidate(data: CandidateInput, session: Db):
    return persist(session, Candidate(**data.model_dump()))


@router.get("/candidates/{candidate_id}", response_model=CandidateRead)
def candidate(candidate_id: UUID, session: Db):
    return require(session, Candidate, candidate_id)


@router.get("/elections/{election_id}/candidates", response_model=Page[ElectionCandidateRead])
def election_candidates(election_id: UUID, session: Db, limit: Limit = 20, offset: Offset = 0):
    require(session, Election, election_id)
    return page(
        session,
        ElectionCandidate,
        ElectionCandidateRead,
        limit,
        offset,
        ElectionCandidate.election_id == election_id,
        order=ElectionCandidate.candidate_id,
    )


@router.post(
    "/elections/{election_id}/candidates", response_model=ElectionCandidateRead, status_code=201
)
def register_candidate(election_id: UUID, data: ElectionCandidateInput, session: Db):
    lock_election(session, election_id, mutable=True)
    require(session, Candidate, data.candidate_id)
    count = session.scalar(
        select(func.count())
        .select_from(ElectionCandidate)
        .where(ElectionCandidate.election_id == election_id)
    )
    if count >= 500:
        raise HTTPException(422, "La démonstration accepte au maximum 500 candidats par scrutin.")
    return persist(session, ElectionCandidate(election_id=election_id, **data.model_dump()))


@router.delete("/elections/{election_id}/candidates/{candidate_id}", status_code=204)
def unregister_candidate(election_id: UUID, candidate_id: UUID, session: Db):
    lock_election(session, election_id, mutable=True)
    session.delete(require(session, ElectionCandidate, (election_id, candidate_id)))
    commit_domain(session)
    return Response(status_code=204)


@router.get("/elections/{election_id}/polling-stations", response_model=Page[ElectionStationRead])
def election_stations(
    election_id: UUID, session: Db, actor: Authenticated, limit: Limit = 20, offset: Offset = 0
):
    require(session, Election, election_id)
    conditions = [ElectionStation.election_id == election_id]
    if actor.role == "AGENT":
        conditions.append(
            select(AgentAssignment.user_id)
            .where(
                AgentAssignment.user_id == actor.id,
                AgentAssignment.election_id == ElectionStation.election_id,
                AgentAssignment.polling_station_id == ElectionStation.polling_station_id,
            )
            .exists()
        )
    return page(
        session,
        ElectionStation,
        ElectionStationRead,
        limit,
        offset,
        *conditions,
        order=ElectionStation.polling_station_id,
    )


@router.post(
    "/elections/{election_id}/polling-stations", response_model=ElectionStationRead, status_code=201
)
def register_station(election_id: UUID, data: ElectionStationInput, session: Db):
    lock_election(session, election_id, mutable=True)
    require(session, PollingStation, data.polling_station_id)
    return persist(session, ElectionStation(election_id=election_id, **data.model_dump()))


@router.get("/user-references", response_model=Page[UserRead])
def users(session: Db, actor: Admin, limit: Limit = 20, offset: Offset = 0):
    return page(session, UserReference, UserRead, limit, offset, order=UserReference.code)


@router.get("/assignments", response_model=Page[AssignmentRead])
def assignments(
    session: Db,
    actor: Authenticated,
    election_id: UUID | None = None,
    limit: Limit = 20,
    offset: Offset = 0,
):
    conditions = [] if election_id is None else [AgentAssignment.election_id == election_id]
    if actor.role != "ADMIN":
        conditions.append(AgentAssignment.user_id == actor.id)
    # Ordre composite pour une pagination stable.
    query = (
        select(AgentAssignment)
        .where(*conditions)
        .order_by(
            AgentAssignment.election_id, AgentAssignment.polling_station_id, AgentAssignment.user_id
        )
    )
    rows = session.scalars(query.limit(limit).offset(offset)).all()
    total = session.scalar(select(func.count()).select_from(AgentAssignment).where(*conditions))
    return Page[AssignmentRead](
        items=[AssignmentRead.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/assignments", response_model=AssignmentRead, status_code=201)
def add_assignment(data: AssignmentInput, session: Db):
    lock_election(session, data.election_id, mutable=True)
    require(session, ElectionStation, (data.election_id, data.polling_station_id))
    user = require(session, UserReference, data.user_id)
    if not user.active or session.get(UserRole, (data.user_id, "AGENT")) is None:
        raise HTTPException(422, "L'affectation exige une référence active déclarée agent.")
    return persist(session, AgentAssignment(**data.model_dump()))


@router.delete("/assignments/{election_id}/{station_id}/{user_id}", status_code=204)
def delete_assignment(election_id: UUID, station_id: UUID, user_id: UUID, session: Db):
    lock_election(session, election_id, mutable=True)
    session.delete(require(session, AgentAssignment, (election_id, station_id, user_id)))
    commit_domain(session)
    return Response(status_code=204)


@router.get("/reports", response_model=Page[ReportRead])
def reports(
    session: Db,
    actor: Authenticated,
    election_id: UUID | None = None,
    polling_station_id: UUID | None = None,
    limit: Limit = 20,
    offset: Offset = 0,
):
    conditions = report_conditions(actor)
    if election_id is not None:
        conditions.append(Report.election_id == election_id)
    if polling_station_id is not None:
        conditions.append(Report.polling_station_id == polling_station_id)
    return page(session, Report, ReportRead, limit, offset, *conditions)


@router.post("/reports", response_model=RevisionRead, status_code=201)
def add_report(data: DraftInput, session: Db, actor: Actor):
    return persist(session, create_draft(session, data, actor))


@router.get("/reports/{report_id}", response_model=ReportRead)
def report(report_id: UUID, session: Db, actor: Authenticated):
    return accessible_report(session, report_id, actor)


@router.get("/reports/{report_id}/revisions", response_model=Page[RevisionRead])
def revisions(
    report_id: UUID, session: Db, actor: Authenticated, limit: Limit = 20, offset: Offset = 0
):
    accessible_report(session, report_id, actor)
    return page(
        session,
        ReportRevision,
        RevisionRead,
        limit,
        offset,
        ReportRevision.report_id == report_id,
        order=ReportRevision.revision_number,
    )


@router.get("/reports/{report_id}/revisions/{number}", response_model=RevisionRead)
def revision(report_id: UUID, number: int, session: Db, actor: Authenticated):
    accessible_report(session, report_id, actor)
    instance = session.scalar(
        select(ReportRevision).where(
            ReportRevision.report_id == report_id, ReportRevision.revision_number == number
        )
    )
    if instance is None:
        raise HTTPException(404, "Révision introuvable.")
    return instance


@router.put("/reports/{report_id}/revisions/{number}/results", response_model=RevisionRead)
def results(report_id: UUID, number: int, data: ResultsInput, session: Db, actor: Actor):
    return persist(session, update_results(session, report_id, number, data, actor))


@router.post("/reports/{report_id}/revisions/{number}/submit", response_model=RevisionRead)
def submit(report_id: UUID, number: int, data: ExpectedVersion, session: Db, actor: Actor):
    return persist(session, submit_report(session, report_id, number, data.expected_version, actor))


@router.post(
    "/reports/{report_id}/revisions/{number}/revise", response_model=RevisionRead, status_code=201
)
def revise(report_id: UUID, number: int, data: RevisionInput, session: Db, actor: Actor):
    return persist(
        session,
        revise_report(session, report_id, number, data.expected_version, data.reason, actor),
    )


@router.get("/reports/{report_id}/history", response_model=Page[EventRead])
def history(
    report_id: UUID, session: Db, actor: Authenticated, limit: Limit = 20, offset: Offset = 0
):
    accessible_report(session, report_id, actor)
    # now() peut être identique pour plusieurs événements créés dans une même transaction.
    query = select(ReportEvent).join(ReportRevision).where(ReportRevision.report_id == report_id)
    rows = session.scalars(
        query.order_by(ReportRevision.revision_number, ReportEvent.edit_version, ReportEvent.id)
        .limit(limit)
        .offset(offset)
    ).all()
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    return Page[EventRead](
        items=[EventRead.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/reports/{report_id}/validations", response_model=Page[ValidationRead])
def validations(
    report_id: UUID, session: Db, actor: Authenticated, limit: Limit = 20, offset: Offset = 0
):
    accessible_report(session, report_id, actor)
    revision_ids = select(ReportRevision.id).where(ReportRevision.report_id == report_id)
    return page(
        session,
        ReportValidation,
        ValidationRead,
        limit,
        offset,
        ReportValidation.revision_id.in_(revision_ids),
        order=ReportValidation.created_at,
    )
