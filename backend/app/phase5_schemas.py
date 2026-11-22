from datetime import datetime
from typing import Literal
from uuid import UUID

from app.domain_schemas import Read


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
