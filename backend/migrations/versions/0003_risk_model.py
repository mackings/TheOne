"""Table for trained models (the shadow risk model).

Revision ID: 0003_risk_model
Revises: 0002_bank_limits
"""
import sqlalchemy as sa

from migrations.helpers import has_table

revision = "0003_risk_model"
down_revision = "0002_bank_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from alembic import op

    if not has_table("net_models"):
        op.create_table(
            "net_models",
            sa.Column("key", sa.String(40), primary_key=True),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("trained_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    from alembic import op

    op.drop_table("net_models")
