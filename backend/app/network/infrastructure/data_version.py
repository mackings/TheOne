"""The shared data version. Every commit that changes graph data bumps a counter in the database,
so each server worker can tell when its cached analysis is stale."""
from __future__ import annotations

from sqlalchemy import event, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.network.application.analysis import cache
from app.network.domain.entities import Account, AccountIdentifier, Identifier, Report, Transfer, TypologyWeight
from app.network.infrastructure.tables import meta

KEY = "data_version"
GRAPH_DATA = (Account, Transfer, Report, Identifier, AccountIdentifier, TypologyWeight)
NOT_APPEND_ONLY = (Report, TypologyWeight)


def read(session: Session) -> int:
    return int(session.scalar(select(meta.c.value).where(meta.c.key == KEY)) or 0)


@event.listens_for(Session, "after_flush")
def _note_graph_change(session: Session, _ctx) -> None:
    new = [o for o in session.new if isinstance(o, GRAPH_DATA)]
    changed = [o for o in list(session.dirty) + list(session.deleted)
               if isinstance(o, GRAPH_DATA) and (o in session.deleted or session.is_modified(o))]
    if new or changed:
        other = changed or any(isinstance(o, NOT_APPEND_ONLY) for o in new) or session.info.get("net_graph_change") == "other"
        session.info["net_graph_change"] = "other" if other else "append"


@event.listens_for(Session, "after_rollback")
def _forget_graph_change(session: Session) -> None:
    session.info.pop("net_graph_change", None)


@event.listens_for(Session, "after_commit")
def _bump(session: Session) -> None:
    kind = session.info.pop("net_graph_change", None)
    if not kind:
        return
    if kind == "append":
        cache.local_appends += 1
    else:
        cache.local_others += 1
    with session.get_bind().begin() as conn:
        if not conn.execute(update(meta).where(meta.c.key == KEY).values(value=meta.c.value + 1)).rowcount:
            try:
                with conn.begin_nested():
                    conn.execute(insert(meta).values(key=KEY, value=1))
            except IntegrityError:
                conn.execute(update(meta).where(meta.c.key == KEY).values(value=meta.c.value + 1))
