"""Analyst actions on a ring (watch-list, confirm, dismiss, release) and the bank actions they cause."""
from __future__ import annotations

from app.core.config import Settings
from app.core.errors import Forbidden, Invalid, NotFound
from app.core.timeutil import now
from app.network.application import bank_actions
from app.network.application.analysis import cache
from app.network.application.ingest import set_label
from app.network.application.ports import BankConnector, NetworkUnitOfWork
from app.network.domain.entities import AnalystAction, Report

ACTIONS = {"watchlist_24h", "confirm", "dismiss", "release"}
SUPERVISORS = {"supervisor", "admin"}


def ring_action(uow: NetworkUnitOfWork, ring_id: str, action: str, account_ids: list[str] | None, actor: str,
                note: str | None, role: str, bank: BankConnector, s: Settings) -> dict:
    if action == "confirm" and role not in SUPERVISORS:
        raise Forbidden("only a supervisor can confirm a ring (it blocks accounts at the bank)")
    ring = uow.rings.get(ring_id)
    if not ring:
        raise NotFound("ring not found")
    members = list(ring.member_ids)
    if account_ids:
        outside = set(account_ids) - set(members)
        if outside:
            raise Invalid(f"accounts not in this ring: {sorted(outside)}")
        targets = account_ids
    elif action == "watchlist_24h":
        targets = list(ring.summary.get("top_connected") or members)[:5]
    else:
        targets = members
    if action not in ACTIONS:
        raise Invalid("action must be watchlist_24h, confirm, dismiss or release")
    stamp = now()
    for acc_id in targets:
        acc = uow.accounts.get(acc_id)
        if action == "watchlist_24h":
            acc.watch(stamp)
        elif action == "confirm":
            acc.confirm_mule()
            uow.reports.add(Report(kind="confirmed_mule", account_id=acc_id, reporter=actor, note=note))
            set_label(uow, acc_id, "mule", stamp, f"analyst:{actor}")
        elif action == "dismiss":
            if acc.clear():
                uow.reports.add(Report(kind="cleared", account_id=acc_id, reporter=actor, note=note))
                set_label(uow, acc_id, "legit", stamp, f"analyst:{actor}")
        else:
            acc.release()
    if action == "confirm":
        ring.status = "confirmed"
    elif action == "dismiss":
        ring.status = "dismissed"
    uow.actions.add(AnalystAction(actor=actor, action=action, ring_id=ring_id, account_ids=targets, note=note))
    queued = bank_actions.queue_for(uow, action, targets, bank, s, ring_id=ring_id, note=note)
    uow.commit()
    cache.bump()
    done = bank_actions.run(uow, queued, bank, s)
    out = {"ring_id": ring_id, "action": action, "accounts": targets, "ring_status": ring.status, "bank_actions": done}
    cache.run(uow, s)
    return out
