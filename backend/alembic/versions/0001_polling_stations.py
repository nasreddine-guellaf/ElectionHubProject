"""Création du référentiel minimal des bureaux de vote."""

import sqlalchemy as sa

from alembic import op

revision = "0001_polling_stations"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "polling_stations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("registered_voters", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.CheckConstraint("registered_voters >= 0", name="ck_station_registered_nonnegative"),
        sa.CheckConstraint("length(trim(code)) > 0", name="ck_station_code_nonempty"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_station_name_nonempty"),
    )


def downgrade():
    op.drop_table("polling_stations")
