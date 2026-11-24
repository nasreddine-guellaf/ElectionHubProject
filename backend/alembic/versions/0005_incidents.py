"""private report incidents and photographs

Revision ID: 0005_incidents
Revises: 0004_private_documents
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_incidents"
down_revision = "0004_private_documents"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "report_incidents",
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('SECURITY','MATERIAL','ACCESS','OTHER')",
            name="ck_incident_category",
        ),
        sa.CheckConstraint(
            "length(trim(description)) BETWEEN 10 AND 2000",
            name="ck_incident_description",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["user_references.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["report_revisions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incident_revision", "report_incidents", ["revision_id"])
    op.create_table(
        "incident_attachments",
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=80), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_provider", sa.String(length=10), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "media_type IN ('image/jpeg','image/png')",
            name="ck_incident_file_media_type",
        ),
        sa.CheckConstraint(
            "storage_provider IN ('LOCAL','S3')",
            name="ck_incident_file_provider",
        ),
        sa.CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 26214400",
            name="ck_incident_file_size",
        ),
        sa.CheckConstraint("length(sha256) = 64", name="ck_incident_file_sha256"),
        sa.ForeignKeyConstraint(["incident_id"], ["report_incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["user_references.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index("ix_incident_attachment_incident", "incident_attachments", ["incident_id"])


def downgrade():
    op.drop_index("ix_incident_attachment_incident", table_name="incident_attachments")
    op.drop_table("incident_attachments")
    op.drop_index("ix_incident_revision", table_name="report_incidents")
    op.drop_table("report_incidents")
