"""Modèle métier phase 2. Les autorisations et les intégrations cloud sont ultérieures."""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ReportStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PROCESSING = "PROCESSING"
    PENDING_VALIDATION = "PENDING_VALIDATION"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PUBLISHED = "PUBLISHED"
    PROCESSING_FAILED = "PROCESSING_FAILED"


class IdentityMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Election(IdentityMixin, Base):
    __tablename__ = "elections"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_election_dates"),
        CheckConstraint("length(trim(name)) > 0", name="ck_election_name"),
        CheckConstraint("code LIKE 'DEMO-%'", name="ck_election_demo_code"),
    )
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    enforce_ballot_equation: Mapped[bool] = mapped_column(Boolean, default=True)


class ElectionStation(Base):
    __tablename__ = "election_stations"
    __table_args__ = (
        CheckConstraint("registered_voters >= 0", name="ck_election_station_registered"),
    )
    election_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("elections.id"), primary_key=True)
    polling_station_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("polling_stations.id"), primary_key=True
    )
    registered_voters: Mapped[int] = mapped_column(Integer)


class Candidate(IdentityMixin, Base):
    __tablename__ = "candidates"
    __table_args__ = (
        CheckConstraint("code LIKE 'DEMO-%'", name="ck_candidate_demo_code"),
        CheckConstraint("length(trim(name)) > 0", name="ck_candidate_name"),
    )
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(200))


class ElectionCandidate(Base):
    __tablename__ = "election_candidates"
    election_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("elections.id"), primary_key=True)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id"), primary_key=True)


class UserReference(IdentityMixin, Base):
    __tablename__ = "user_references"
    __table_args__ = (
        CheckConstraint("code LIKE 'DEMO-%'", name="ck_user_demo_code"),
        CheckConstraint("length(trim(display_name)) > 0", name="ck_user_display_name"),
    )
    code: Mapped[str] = mapped_column(String(40), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        CheckConstraint("role IN ('AGENT', 'ADMIN', 'VALIDATOR', 'CITIZEN')", name="ck_user_role"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_references.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), primary_key=True)


class AgentAssignment(Base):
    __tablename__ = "agent_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["election_id", "polling_station_id"],
            ["election_stations.election_id", "election_stations.polling_station_id"],
        ),
    )
    election_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    polling_station_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_references.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Report(IdentityMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["election_id", "polling_station_id"],
            ["election_stations.election_id", "election_stations.polling_station_id"],
        ),
        UniqueConstraint("election_id", "polling_station_id", name="uq_report_election_station"),
        UniqueConstraint("id", "election_id", name="uq_report_id_election"),
        CheckConstraint("current_revision >= 1", name="ck_report_current_revision"),
    )
    election_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    polling_station_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_references.id"))
    current_revision: Mapped[int] = mapped_column(Integer, default=1)
    revisions: Mapped[list["ReportRevision"]] = relationship(
        back_populates="report", order_by="ReportRevision.revision_number"
    )


class ReportRevision(IdentityMixin, Base):
    __tablename__ = "report_revisions"
    __table_args__ = (
        ForeignKeyConstraint(["report_id", "election_id"], ["reports.id", "reports.election_id"]),
        UniqueConstraint("report_id", "revision_number", name="uq_revision_number"),
        UniqueConstraint("id", "election_id", name="uq_revision_id_election"),
        CheckConstraint("revision_number >= 1 AND edit_version >= 1", name="ck_revision_versions"),
        CheckConstraint(
            "registered_voters >= 0 AND ballots_cast >= 0 AND valid_votes >= 0 "
            "AND blank_votes >= 0 AND invalid_votes >= 0",
            name="ck_revision_counts",
        ),
        CheckConstraint(
            "valid_votes <= ballots_cast AND ballots_cast <= registered_voters "
            "AND blank_votes <= ballots_cast AND invalid_votes <= ballots_cast",
            name="ck_revision_turnout",
        ),
        CheckConstraint(
            "NOT enforce_ballot_equation OR "
            "CAST(valid_votes AS BIGINT) + blank_votes + invalid_votes = ballots_cast",
            name="ck_revision_ballot_equation",
        ),
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','PROCESSING','PENDING_VALIDATION','APPROVED',"
            "'REJECTED','PUBLISHED','PROCESSING_FAILED')",
            name="ck_revision_status",
        ),
        CheckConstraint(
            "revision_number = 1 OR length(trim(revision_reason)) > 0",
            name="ck_revision_reason",
        ),
        Index(
            "uq_report_draft", "report_id", unique=True, postgresql_where=text("status = 'DRAFT'")
        ),
        Index("ix_revision_status", "status"),
    )
    report_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    election_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    revision_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default=ReportStatus.DRAFT)
    edit_version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_references.id"))
    revision_reason: Mapped[str] = mapped_column(String(1000), default="")
    registered_voters: Mapped[int] = mapped_column(Integer)
    enforce_ballot_equation: Mapped[bool] = mapped_column(Boolean)
    ballots_cast: Mapped[int] = mapped_column(Integer, default=0)
    valid_votes: Mapped[int] = mapped_column(Integer, default=0)
    blank_votes: Mapped[int] = mapped_column(Integer, default=0)
    invalid_votes: Mapped[int] = mapped_column(Integer, default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    report: Mapped[Report] = relationship(back_populates="revisions")
    results: Mapped[list["ReportResult"]] = relationship(
        cascade="all, delete-orphan", order_by="ReportResult.candidate_id"
    )


class ReportResult(Base):
    __tablename__ = "report_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["revision_id", "election_id"], ["report_revisions.id", "report_revisions.election_id"]
        ),
        ForeignKeyConstraint(
            ["election_id", "candidate_id"],
            ["election_candidates.election_id", "election_candidates.candidate_id"],
        ),
        CheckConstraint("votes >= 0", name="ck_result_votes"),
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    candidate_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    election_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    votes: Mapped[int] = mapped_column(Integer)


class ReportEvent(IdentityMixin, Base):
    __tablename__ = "report_events"
    __table_args__ = (
        CheckConstraint(
            "action IN ('CREATED','RESULTS_UPDATED','SUBMITTED','REVISED',"
            "'REVIEW_STARTED','APPROVED','REJECTED')",
            name="ck_report_event_action",
        ),
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("report_revisions.id"), index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_references.id"))
    action: Mapped[str] = mapped_column(String(30))
    edit_version: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(1000), default="")


class ReportValidation(IdentityMixin, Base):
    __tablename__ = "report_validations"
    __table_args__ = (
        CheckConstraint("decision IN ('APPROVED','REJECTED')", name="ck_validation_decision"),
        CheckConstraint(
            "decision != 'REJECTED' OR length(trim(reason)) > 0",
            name="ck_validation_rejection_reason",
        ),
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("report_revisions.id"), unique=True)
    validator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_references.id"))
    decision: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(1000), default="")
