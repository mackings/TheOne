"""Audit table for trace requests sent through NIBSS.

Revision ID: 0004_nibss_traces
Revises: 0003_risk_model
"""
import sqlalchemy as sa

from migrations.helpers import has_table

revision = "0004_nibss_traces"
down_revision = "0003_risk_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from alembic import op

    if not has_table("net_traces"):
        op.create_table(
            "net_traces",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, index=True),
            sa.Column("ring_id", sa.String(32), nullable=False, index=True),
            sa.Column("actor", sa.String(80), nullable=False),
            sa.Column("bank_code", sa.String(12), nullable=False),
            sa.Column("account_no", sa.String(20), nullable=False),
            sa.Column("hop", sa.Integer(), nullable=False),
            sa.Column("connector", sa.String(20), nullable=False),
            sa.Column("status", sa.String(12), nullable=False),
            sa.Column("error", sa.String(300), nullable=True),
            sa.Column("amount_in_kobo", sa.BigInteger(), nullable=False),
            sa.Column("onward_count", sa.Integer(), nullable=False),
            sa.Column("amount_onward_kobo", sa.BigInteger(), nullable=False),
        )


def downgrade() -> None:
    from alembic import op

    op.drop_table("net_traces")
