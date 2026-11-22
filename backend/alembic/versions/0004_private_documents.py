"""private documents

Revision ID: 0004_private_documents
Revises: 0003_authentication
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_private_documents"
down_revision = "0003_authentication"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "report_documents",
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=80), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_provider", sa.String(length=10), nullable=False),
        sa.Column("processing_status", sa.String(length=20), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(length=500), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "media_type IN ('application/pdf','image/jpeg','image/png')",
            name="ck_document_media_type",
        ),
        sa.CheckConstraint(
            "processing_status IN ('STORED','PROCESSED','FAILED')",
            name="ck_document_processing_status",
        ),
        sa.CheckConstraint(
            "storage_provider IN ('LOCAL','S3')", name="ck_document_provider"
        ),
        sa.CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 26214400", name="ck_document_size"
        ),
        sa.CheckConstraint("length(sha256) = 64", name="ck_document_sha256"),
        sa.ForeignKeyConstraint(["revision_id"], ["report_revisions.id"]),
        sa.ForeignKeyConstraint(["uploaded_by"], ["user_references.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index("ix_document_revision", "report_documents", ["revision_id"])
    op.create_table(
        "object_events",
        sa.Column("provider_event_id", sa.String(length=200), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("event_name", sa.String(length=100), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(provider_event_id)) > 0", name="ck_object_event_id"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["report_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_event_id"),
    )
    op.create_index(
        op.f("ix_object_events_document_id"), "object_events", ["document_id"]
    )


def downgrade():
    op.drop_index(op.f("ix_object_events_document_id"), table_name="object_events")
    op.drop_table("object_events")
    op.drop_index("ix_document_revision", table_name="report_documents")
    op.drop_table("report_documents")
