"""Per-account daily limit and sync time from the bank's limits API.

Revision ID: 0002_bank_limits
Revises: 0001_baseline
"""
import sqlalchemy as sa

from migrations.helpers import add_column_if_missing

revision = "0002_bank_limits"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    add_column_if_missing("net_accounts", sa.Column("bank_daily_limit_kobo", sa.BigInteger(), nullable=True))
    add_column_if_missing("net_accounts", sa.Column("bank_synced_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    from alembic import op

    with op.batch_alter_table("net_accounts") as b:
        b.drop_column("bank_synced_at")
        b.drop_column("bank_daily_limit_kobo")
