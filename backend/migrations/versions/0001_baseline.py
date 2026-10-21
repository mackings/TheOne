"""Baseline: every table as of the mule-network release.

Idempotent on purpose. Databases created earlier by create_all() already hold some of these
tables (and may lack columns added later); this creates whatever is missing and adds the
missing columns, so local, test and Render databases all converge on the same schema.

Revision ID: 0001_baseline
Revises:
"""
import sqlalchemy as sa

from app.infrastructure.database import metadata, register_tables
from migrations.helpers import add_column_if_missing

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

LATE_COLUMNS = {
    "verification_events": [sa.Column("duress", sa.Boolean(), nullable=True, server_default=sa.false())],
    "net_decisions": [sa.Column("sender_score", sa.Float(), nullable=True), sa.Column("context", sa.JSON(), nullable=True)],
}


def upgrade() -> None:
    from alembic import op

    bind = op.get_bind()
    register_tables()
    metadata.create_all(bind=bind, checkfirst=True)
    for table, cols in LATE_COLUMNS.items():
        for col in cols:
            add_column_if_missing(table, col)


def downgrade() -> None:
    raise NotImplementedError("the baseline cannot be downgraded")
