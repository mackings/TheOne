"""The outbox of actions sent to the bank: holds, hold removals and post-no-debit blocks.

TheOne decides; the bank acts. Every action is recorded first and sent after the commit, so a failed
call stays visible and can be retried instead of being lost."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from app.core.config import Settings
from app.core.errors import Conflict, NotFound
from app.core.timeutil import now
from app.network.application.ports import BankConnector, BankResult, NetworkUnitOfWork
from app.network.domain.entities import Account, BankAction

log = logging.getLogger(__name__)


def enqueue(uow: NetworkUnitOfWork, kind: str, account: Account, bank: BankConnector, *, ring_id: str | None = None,
            reason: str = "", hold_hours: int = 24) -> BankAction:
    req: dict[str, Any] = {"account_no": account.account_no, "bank_code": account.bank_code, "reason": reason}
    if kind == "place_hold":
        start = now()
        req |= {"start": start.isoformat(), "end": (start + timedelta(hours=hold_hours)).isoformat()}
    return uow.bank_actions.add(BankAction(kind=kind, account_id=account.id, ring_id=ring_id, reference=f"THEONE-{uuid.uuid4().hex[:20].upper()}",
                                           request=req, connector=bank.name))


def execute(uow: NetworkUnitOfWork, a: BankAction, bank: BankConnector, s: Settings) -> BankAction:
    """Send one outbox action. Shadow mode records it without touching the bank."""
    if a.status == "done":
        return a
    if s.network_mode == "shadow":
        a.status, a.last_error = "shadow", None
        return a
    acc = uow.accounts.get(a.account_id)
    if acc.bank_code != s.network_home_bank_code:
        a.status, a.last_error = "recorded", "account is at another bank; report it to that bank"
        return a
    a.connector = bank.name
    a.attempts += 1
    req = a.request
    if a.kind == "place_hold":
        amount = bank.available_balance(acc.account_no)
        start, end = datetime.fromisoformat(req["start"]), datetime.fromisoformat(req["end"])
        res = bank.place_hold(acc.account_no, amount or "0", a.reference, req.get("reason", ""), start, end)
        if res.ok and amount is not None:
            a.request = {**req, "amount_naira": amount}
    elif a.kind == "remove_hold":
        res = bank.remove_hold(acc.account_no, req.get("hold_reference", a.reference))
    elif a.kind == "block_pnd":
        res = bank.block_pnd(acc.account_no, req.get("reason") or "TheOne: confirmed mule account")
    else:
        res = BankResult(False, error=f"unknown action {a.kind}")
    a.response = res.body if isinstance(res.body, (dict, list)) else ({"value": res.body} if res.body is not None else None)
    if res.ok:
        a.status = "recorded" if res.meta.get("recorded_only") else "done"
        a.last_error, a.done_at = None, now()
    else:
        a.status, a.last_error = "failed", (res.error or "unknown error")[:500]
        log.warning("bank action %s %s failed: %s", a.kind, a.reference, a.last_error)
    return a


def run(uow: NetworkUnitOfWork, ids: list[str], bank: BankConnector, s: Settings) -> list[dict]:
    out = []
    for i in ids:
        a = execute(uow, uow.bank_actions.get(i), bank, s)
        uow.commit()
        out.append(action_out(a))
    return out


def retry(uow: NetworkUnitOfWork, action_id: str, bank: BankConnector, s: Settings) -> dict:
    a = uow.bank_actions.get(action_id)
    if not a:
        raise NotFound("bank action not found")
    if a.status == "done":
        raise Conflict("already done")
    execute(uow, a, bank, s)
    uow.commit()
    return action_out(a)


def recent(uow: NetworkUnitOfWork, status: str | None, limit: int) -> list[dict]:
    return [action_out(a) for a in uow.bank_actions.newest(status, max(1, min(limit, 500)))]


def active_holds(uow: NetworkUnitOfWork, account_id: str) -> list[BankAction]:
    placed = uow.bank_actions.for_account(account_id, "place_hold", {"done", "recorded"})
    removed = {(r.request or {}).get("hold_reference")
               for r in uow.bank_actions.for_account(account_id, "remove_hold", {"done", "recorded", "pending"})}
    return [p for p in placed if p.reference not in removed]


def queue_for(uow: NetworkUnitOfWork, action: str, account_ids: list[str], bank: BankConnector, s: Settings, *,
              ring_id: str | None = None, note: str | None = None) -> list[str]:
    """The bank actions an analyst action causes, for accounts at this bank. Sent after commit."""
    ids: list[str] = []
    for acc_id in account_ids:
        acc = uow.accounts.get(acc_id)
        if acc.bank_code != s.network_home_bank_code:
            continue
        if action == "watchlist_24h":
            ids.append(enqueue(uow, "place_hold", acc, bank, ring_id=ring_id, reason=note or "TheOne 24-hour mule watchlist").id)
        elif action in {"release", "dismiss"}:
            for h in active_holds(uow, acc_id):
                a = enqueue(uow, "remove_hold", acc, bank, ring_id=ring_id, reason=action)
                a.request = {**a.request, "hold_reference": h.reference}
                ids.append(a.id)
        elif action == "confirm":
            ids.append(enqueue(uow, "block_pnd", acc, bank, ring_id=ring_id,
                               reason=note or "TheOne: confirmed mule account (post no debit)").id)
    uow.flush()
    return ids


def action_out(a: BankAction) -> dict:
    return {"id": a.id, "created_at": a.created_at.isoformat(), "kind": a.kind, "account_id": a.account_id,
            "ring_id": a.ring_id, "reference": a.reference, "status": a.status, "attempts": a.attempts,
            "connector": a.connector, "last_error": a.last_error, "request": a.request, "response": a.response,
            "done_at": a.done_at.isoformat() if a.done_at else None}
