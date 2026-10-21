"""Account upkeep: refresh an account from the bank, link it to a biometric customer, and the
customer's own safe limit."""
from __future__ import annotations

from app.core.config import Settings
from app.core.errors import Conflict, NotFound, Upstream
from app.core.timeutil import now
from app.network.application.analysis import cache
from app.network.application.ports import BankConnector, NetworkUnitOfWork
from app.network.domain.entities import Account, SafeLimit


def _account(uow: NetworkUnitOfWork, account_id: str) -> Account:
    acc = uow.accounts.get(account_id)
    if not acc:
        raise NotFound("account not found")
    return acc


def sync_from_bank(uow: NetworkUnitOfWork, account_id: str, bank: BankConnector) -> dict:
    """Pull the account profile and daily limit from the bank (OBN Account and Limits APIs)."""
    acc = _account(uow, account_id)
    if bank.name == "none":
        raise Conflict("no bank connector configured (NETWORK_BANK_CONNECTOR=obn)")
    prof = bank.account_profile(acc.account_no)
    if not prof.ok:
        raise Upstream(f"bank account lookup failed: {prof.error}")
    if prof.opened_at:
        acc.opened_at = prof.opened_at
    if prof.full_name:
        acc.holder_name = prof.full_name
    if prof.kyc_tier is not None:
        acc.kyc_tier = prof.kyc_tier
    limits_ok, limit_kobo = bank.daily_limit_kobo(acc.account_no)
    if limit_kobo is not None:
        acc.bank_daily_limit_kobo = limit_kobo
    acc.bank_synced_at = now()
    uow.commit()
    cache.bump()
    return {"account_id": acc.id, "opened_at": acc.opened_at.isoformat() if acc.opened_at else None,
            "kyc_tier": acc.kyc_tier, "bank_status": prof.status, "daily_limit_kobo": limit_kobo, "limits_ok": limits_ok}


def link_customer(uow: NetworkUnitOfWork, account_id: str, customer_id: str) -> dict:
    acc = _account(uow, account_id)
    if not uow.customers.get(customer_id):
        raise NotFound("customer not found")
    acc.customer_id = customer_id
    uow.commit()
    cache.bump()
    return {"account_id": acc.id, "customer_id": acc.customer_id}


def customer_accounts(uow: NetworkUnitOfWork, customer_id: str) -> list[dict]:
    """Accounts linked to a biometric customer: what the customer's app sends money from."""
    return [{"id": a.id, "bank_code": a.bank_code, "account_no": a.account_no, "name": a.holder_name,
             "status": a.effective_status()} for a in uow.accounts.by_customer(customer_id)]


def safe_limit_out(lim: SafeLimit | None, note: str | None = None) -> dict:
    if lim is None:
        return {"limit_kobo": None, "pending_limit_kobo": None, "pending_effective_at": None, "note": "no safe limit set"}
    return {"limit_kobo": lim.limit_kobo, "pending_limit_kobo": lim.pending_limit_kobo,
            "pending_effective_at": lim.pending_effective_at.isoformat() if lim.pending_effective_at else None, "note": note}


def get_safe_limit(uow: NetworkUnitOfWork, account_id: str) -> dict:
    _account(uow, account_id)
    lim = uow.safe_limits.get(account_id)
    if lim:
        lim.current()
        uow.commit()
    return safe_limit_out(lim)


def set_safe_limit(uow: NetworkUnitOfWork, account_id: str, limit_kobo: int, s: Settings) -> dict:
    """Lowering applies at once; raising waits the cooling-off period."""
    _account(uow, account_id)
    lim = uow.safe_limits.get(account_id)
    if lim is None:
        lim = uow.safe_limits.add(SafeLimit(account_id=account_id, limit_kobo=limit_kobo))
        note = "safe limit set"
    else:
        note = lim.change(limit_kobo, now(), s.network_safe_limit_cooling_hours)
    uow.commit()
    return safe_limit_out(lim, note)
