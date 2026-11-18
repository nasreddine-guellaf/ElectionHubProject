from datetime import date, datetime
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.domain_models import ReportStatus

Count = Annotated[int, Field(strict=True, ge=0, le=2_147_483_647)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Code = Annotated[str, StringConstraints(pattern=r"^DEMO-[A-Z0-9-]+$", max_length=40)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Read(BaseModel):
    model_config = ConfigDict(from_attributes=True)


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
    data_kind: Literal["synthetic"] = "synthetic"


class ElectionInput(Input):
    code: Code
    name: Name
    start_date: date
    end_date: date
    enforce_ballot_equation: bool = True

    @model_validator(mode="after")
    def dates_in_order(self):
        if self.end_date < self.start_date:
            raise ValueError("La fin du scrutin doit suivre son début.")
        return self


class ElectionRead(ElectionInput, Read):
    id: UUID
    created_at: datetime


class CandidateInput(Input):
    code: Code
    name: Name


class CandidateRead(CandidateInput, Read):
    id: UUID
    created_at: datetime


class ElectionCandidateInput(Input):
    candidate_id: UUID


class ElectionCandidateRead(Read):
    election_id: UUID
    candidate_id: UUID


class ElectionStationInput(Input):
    polling_station_id: UUID
    registered_voters: Count


class ElectionStationRead(ElectionStationInput, Read):
    election_id: UUID


class UserRead(Read):
    id: UUID
    code: str
    display_name: str
    active: bool


class AssignmentInput(Input):
    election_id: UUID
    polling_station_id: UUID
    user_id: UUID


class AssignmentRead(AssignmentInput, Read):
    created_at: datetime


class DraftInput(Input):
    election_id: UUID
    polling_station_id: UUID


class ExpectedVersion(Input):
    expected_version: Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]


class ResultInput(Input):
    candidate_id: UUID
    votes: Count


class ResultsInput(ExpectedVersion):
    ballots_cast: Count
    valid_votes: Count
    blank_votes: Count
    invalid_votes: Count
    results: Annotated[list[ResultInput], Field(min_length=1, max_length=500)]


class RevisionInput(ExpectedVersion):
    reason: Reason


class RevisionRead(Read):
    id: UUID
    report_id: UUID
    election_id: UUID
    revision_number: int
    status: ReportStatus
    edit_version: int
    created_by: UUID
    revision_reason: str
    registered_voters: int
    enforce_ballot_equation: bool
    ballots_cast: int
    valid_votes: int
    blank_votes: int
    invalid_votes: int
    created_at: datetime
    submitted_at: datetime | None
    results: list["ResultRead"]


class ResultRead(Read):
    candidate_id: UUID
    votes: int


class ReportRead(Read):
    id: UUID
    election_id: UUID
    polling_station_id: UUID
    created_by: UUID
    current_revision: int
    created_at: datetime


class EventRead(Read):
    id: UUID
    revision_id: UUID
    actor_id: UUID
    action: str
    edit_version: int
    note: str
    created_at: datetime


class ValidationRead(Read):
    id: UUID
    revision_id: UUID
    validator_id: UUID
    decision: str
    reason: str
    created_at: datetime
