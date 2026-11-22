"""Métadonnées des objets privés de la phase 5; aucun binaire en PostgreSQL."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.domain_models import IdentityMixin


class ReportDocument(IdentityMixin, Base):
    __tablename__ = "report_documents"
    __table_args__ = (
        CheckConstraint("size_bytes > 0 AND size_bytes <= 26214400", name="ck_document_size"),
        CheckConstraint("length(sha256) = 64", name="ck_document_sha256"),
        CheckConstraint(
            "media_type IN ('application/pdf','image/jpeg','image/png')",
            name="ck_document_media_type",
        ),
        CheckConstraint("storage_provider IN ('LOCAL','S3')", name="ck_document_provider"),
        CheckConstraint(
            "processing_status IN ('STORED','PROCESSED','FAILED')",
            name="ck_document_processing_status",
        ),
        Index("ix_document_revision", "revision_id"),
    )

    revision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("report_revisions.id"))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_references.id"))
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_provider: Mapped[str] = mapped_column(String(10))
    processing_status: Mapped[str] = mapped_column(String(20), default="STORED")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String(500))


class ObjectEvent(IdentityMixin, Base):
    """Réception idempotente d'un événement objet; remplie par Lambda PV ultérieurement."""

    __tablename__ = "object_events"
    __table_args__ = (
        CheckConstraint("length(trim(provider_event_id)) > 0", name="ck_object_event_id"),
    )

    provider_event_id: Mapped[str] = mapped_column(String(200), unique=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("report_documents.id"), index=True)
    event_name: Mapped[str] = mapped_column(String(100))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
