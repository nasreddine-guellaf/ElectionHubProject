from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints

from app.domain_schemas import ExpectedVersion, Read


class DocumentRead(Read):
    id: UUID
    revision_id: UUID
    uploaded_by: UUID
    original_filename: str
    media_type: str
    size_bytes: int
    sha256: str
    storage_provider: Literal["LOCAL", "S3"]
    processing_status: Literal["STORED", "PROCESSED", "FAILED"]
    created_at: datetime
    processed_at: datetime | None
    failure_reason: str | None


class IncidentAttachmentRead(Read):
    id: UUID
    incident_id: UUID
    uploaded_by: UUID
    original_filename: str
    media_type: Literal["image/jpeg", "image/png"]
    size_bytes: int
    sha256: str
    storage_provider: Literal["LOCAL", "S3"]
    created_at: datetime


class IncidentInput(ExpectedVersion):
    category: Literal["SECURITY", "MATERIAL", "ACCESS", "OTHER"]
    description: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=10, max_length=2000),
    ]


class IncidentRead(Read):
    id: UUID
    revision_id: UUID
    created_by: UUID
    category: Literal["SECURITY", "MATERIAL", "ACCESS", "OTHER"]
    description: str
    created_at: datetime
    attachments: list[IncidentAttachmentRead] = Field(default_factory=list)
