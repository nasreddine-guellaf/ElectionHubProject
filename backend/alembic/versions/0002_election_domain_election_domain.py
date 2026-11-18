"""election_domain

Revision ID: 0002_election_domain
Revises: 0001_polling_stations
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_election_domain"
down_revision = "0001_polling_stations"
branch_labels = None
depends_on = None


def upgrade():
    # Migration additive relue : aucune modification de polling_stations.
    op.create_table(
        "candidates",
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("code LIKE 'DEMO-%'", name="ck_candidate_demo_code"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_candidate_name"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "elections",
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("enforce_ballot_equation", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("code LIKE 'DEMO-%'", name="ck_election_demo_code"),
        sa.CheckConstraint("end_date >= start_date", name="ck_election_dates"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_election_name"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "user_references",
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("code LIKE 'DEMO-%'", name="ck_user_demo_code"),
        sa.CheckConstraint("length(trim(display_name)) > 0", name="ck_user_display_name"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "election_candidates",
        sa.Column("election_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
        ),
        sa.ForeignKeyConstraint(
            ["election_id"],
            ["elections.id"],
        ),
        sa.PrimaryKeyConstraint("election_id", "candidate_id"),
    )
    op.create_table(
        "election_stations",
        sa.Column("election_id", sa.Uuid(), nullable=False),
        sa.Column("polling_station_id", sa.Uuid(), nullable=False),
        sa.Column("registered_voters", sa.Integer(), nullable=False),
        sa.CheckConstraint("registered_voters >= 0", name="ck_election_station_registered"),
        sa.ForeignKeyConstraint(
            ["election_id"],
            ["elections.id"],
        ),
        sa.ForeignKeyConstraint(
            ["polling_station_id"],
            ["polling_stations.id"],
        ),
        sa.PrimaryKeyConstraint("election_id", "polling_station_id"),
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "role IN ('AGENT', 'ADMIN', 'VALIDATOR', 'CITIZEN')", name="ck_user_role"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_references.id"],
        ),
        sa.PrimaryKeyConstraint("user_id", "role"),
    )
    op.create_table(
        "agent_assignments",
        sa.Column("election_id", sa.Uuid(), nullable=False),
        sa.Column("polling_station_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["election_id", "polling_station_id"],
            ["election_stations.election_id", "election_stations.polling_station_id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_references.id"],
        ),
        sa.PrimaryKeyConstraint("election_id", "polling_station_id", "user_id"),
    )
    op.create_table(
        "reports",
        sa.Column("election_id", sa.Uuid(), nullable=False),
        sa.Column("polling_station_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("current_revision", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("current_revision >= 1", name="ck_report_current_revision"),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["user_references.id"],
        ),
        sa.ForeignKeyConstraint(
            ["election_id", "polling_station_id"],
            ["election_stations.election_id", "election_stations.polling_station_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("election_id", "polling_station_id", name="uq_report_election_station"),
        sa.UniqueConstraint("id", "election_id", name="uq_report_id_election"),
    )
    op.create_table(
        "report_revisions",
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("election_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("edit_version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("revision_reason", sa.String(length=1000), nullable=False),
        sa.Column("registered_voters", sa.Integer(), nullable=False),
        sa.Column("enforce_ballot_equation", sa.Boolean(), nullable=False),
        sa.Column("ballots_cast", sa.Integer(), nullable=False),
        sa.Column("valid_votes", sa.Integer(), nullable=False),
        sa.Column("blank_votes", sa.Integer(), nullable=False),
        sa.Column("invalid_votes", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','PROCESSING','PENDING_VALIDATION','APPROVED',"
            "'REJECTED','PUBLISHED','PROCESSING_FAILED')",
            name="ck_revision_status",
        ),
        sa.CheckConstraint(
            "NOT enforce_ballot_equation OR "
            "CAST(valid_votes AS BIGINT) + blank_votes + invalid_votes = ballots_cast",
            name="ck_revision_ballot_equation",
        ),
        sa.CheckConstraint(
            "registered_voters >= 0 AND ballots_cast >= 0 AND valid_votes >= 0 "
            "AND blank_votes >= 0 AND invalid_votes >= 0",
            name="ck_revision_counts",
        ),
        sa.CheckConstraint(
            "revision_number = 1 OR length(trim(revision_reason)) > 0", name="ck_revision_reason"
        ),
        sa.CheckConstraint(
            "revision_number >= 1 AND edit_version >= 1", name="ck_revision_versions"
        ),
        sa.CheckConstraint(
            "valid_votes <= ballots_cast AND ballots_cast <= registered_voters "
            "AND blank_votes <= ballots_cast AND invalid_votes <= ballots_cast",
            name="ck_revision_turnout",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["user_references.id"],
        ),
        sa.ForeignKeyConstraint(
            ["report_id", "election_id"],
            ["reports.id", "reports.election_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "election_id", name="uq_revision_id_election"),
        sa.UniqueConstraint("report_id", "revision_number", name="uq_revision_number"),
    )
    op.create_index("ix_revision_status", "report_revisions", ["status"], unique=False)
    op.create_index(
        "uq_report_draft",
        "report_revisions",
        ["report_id"],
        unique=True,
        postgresql_where=sa.text("status = 'DRAFT'"),
    )
    op.create_table(
        "report_events",
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("edit_version", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=1000), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('CREATED','RESULTS_UPDATED','SUBMITTED','REVISED')",
            name="ck_report_event_action",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["user_references.id"],
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["report_revisions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_report_events_revision_id"), "report_events", ["revision_id"], unique=False
    )
    op.create_table(
        "report_results",
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("election_id", sa.Uuid(), nullable=False),
        sa.Column("votes", sa.Integer(), nullable=False),
        sa.CheckConstraint("votes >= 0", name="ck_result_votes"),
        sa.ForeignKeyConstraint(
            ["election_id", "candidate_id"],
            ["election_candidates.election_id", "election_candidates.candidate_id"],
        ),
        sa.ForeignKeyConstraint(
            ["revision_id", "election_id"],
            ["report_revisions.id", "report_revisions.election_id"],
        ),
        sa.PrimaryKeyConstraint("revision_id", "candidate_id"),
    )
    op.create_table(
        "report_validations",
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("validator_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision != 'REJECTED' OR length(trim(reason)) > 0",
            name="ck_validation_rejection_reason",
        ),
        sa.CheckConstraint("decision IN ('APPROVED','REJECTED')", name="ck_validation_decision"),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["report_revisions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["validator_id"],
            ["user_references.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("revision_id"),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("report_validations")
    op.drop_table("report_results")
    op.drop_index(op.f("ix_report_events_revision_id"), table_name="report_events")
    op.drop_table("report_events")
    op.drop_index(
        "uq_report_draft",
        table_name="report_revisions",
        postgresql_where=sa.text("status = 'DRAFT'"),
    )
    op.drop_index("ix_revision_status", table_name="report_revisions")
    op.drop_table("report_revisions")
    op.drop_table("reports")
    op.drop_table("agent_assignments")
    op.drop_table("user_roles")
    op.drop_table("election_stations")
    op.drop_table("election_candidates")
    op.drop_table("user_references")
    op.drop_table("elections")
    op.drop_table("candidates")
    # ### end Alembic commands ###
