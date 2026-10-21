"""Background jobs for large file imports.

Revision ID: 0005_import_jobs
Revises: 0004_nibss_traces
"""
import sqlalchemy as sa

from migrations.helpers import has_table

revision = "0005_import_jobs"
down_revision = "0004_nibss_traces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from alembic import op

    if not has_table("net_import_jobs"):
        op.create_table(
            "net_import_jobs",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, index=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("fmt", sa.String(16), nullable=False),
            sa.Column("filename", sa.String(200), nullable=False),
            sa.Column("size_bytes", sa.BigInteger(), nullable=False),
            sa.Column("bytes_read", sa.BigInteger(), nullable=False),
            sa.Column("dry_run", sa.Boolean(), nullable=False),
            sa.Column("status", sa.String(12), nullable=False),
            sa.Column("rows", sa.BigInteger(), nullable=False),
            sa.Column("valid", sa.BigInteger(), nullable=False),
            sa.Column("added", sa.BigInteger(), nullable=False),
            sa.Column("skipped", sa.BigInteger(), nullable=False),
            sa.Column("accounts_added", sa.BigInteger(), nullable=False),
            sa.Column("error_count", sa.BigInteger(), nullable=False),
            sa.Column("errors", sa.JSON(), nullable=True),
            sa.Column("message", sa.String(300), nullable=True),
            sa.Column("actor", sa.String(80), nullable=True),
        )


def downgrade() -> None:
    from alembic import op

    op.drop_table("net_import_jobs")
