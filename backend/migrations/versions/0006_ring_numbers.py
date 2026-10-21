"""Ring numbers: a plain number per ring (100001, 100002, ...) that people can read and copy.

Revision ID: 0006_ring_numbers
Revises: 0005_import_jobs
"""
import sqlalchemy as sa

from migrations.helpers import add_column_if_missing

revision = "0006_ring_numbers"
down_revision = "0005_import_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from alembic import op

    add_column_if_missing("net_rings", sa.Column("case_no", sa.Integer(), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id FROM net_rings WHERE case_no IS NULL ORDER BY created_at, id")).fetchall()
    start = (bind.execute(sa.text("SELECT MAX(case_no) FROM net_rings")).scalar() or 100000) + 1
    for i, (rid,) in enumerate(rows):
        bind.execute(sa.text("UPDATE net_rings SET case_no = :n WHERE id = :id"), {"n": start + i, "id": rid})
    insp = sa.inspect(bind)
    if "uq_net_rings_case_no" not in {u["name"] for u in insp.get_unique_constraints("net_rings")} and \
            "ix_net_rings_case_no" not in {i["name"] for i in insp.get_indexes("net_rings")}:
        op.create_index("ix_net_rings_case_no", "net_rings", ["case_no"], unique=True)


def downgrade() -> None:
    from alembic import op

    op.drop_index("ix_net_rings_case_no", table_name="net_rings")
    with op.batch_alter_table("net_rings") as b:
        b.drop_column("case_no")
