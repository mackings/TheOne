"""Accounts: flagged and searched lists, one account's detail, bank sync, customer link and safe limits."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_bank, get_uow
from app.core.config import Settings, get_settings
from app.network.api.schemas import LinkIn, SafeLimitIn
from app.network.application import accounts, queries
from app.network.application.analysis import cache

router = APIRouter()


@router.get("/accounts")
def account_list(flagged: bool = True, limit: int = 100, uow=Depends(get_uow), s: Settings = Depends(get_settings)):
    return queries.list_accounts(cache.get(uow), s, flagged, limit)


@router.get("/accounts/search")
def account_search(q: str, limit: int = 20, uow=Depends(get_uow)):
    return queries.search_accounts(cache.get(uow), q, limit)


@router.get("/accounts/lookup")
def account_lookup(bank_code: str, account_no: str, uow=Depends(get_uow)):
    """Name enquiry: the holder of an account, by bank and account number, as a bank checks it before a transfer."""
    return queries.lookup_account(uow, bank_code, account_no)


@router.get("/accounts/{account_id}")
def account_detail(account_id: str, uow=Depends(get_uow)):
    return queries.account_detail(uow, account_id)


@router.post("/accounts/{account_id}/sync")
def sync_account(account_id: str, uow=Depends(get_uow), bank=Depends(get_bank)):
    return accounts.sync_from_bank(uow, account_id, bank)


@router.post("/accounts/{account_id}/link")
def link_customer(account_id: str, body: LinkIn, uow=Depends(get_uow)):
    return accounts.link_customer(uow, account_id, body.customer_id)


@router.get("/accounts/{account_id}/safe-limit")
def get_safe_limit(account_id: str, uow=Depends(get_uow)):
    return accounts.get_safe_limit(uow, account_id)


@router.put("/accounts/{account_id}/safe-limit")
def put_safe_limit(account_id: str, body: SafeLimitIn, uow=Depends(get_uow), s: Settings = Depends(get_settings)):
    return accounts.set_safe_limit(uow, account_id, body.limit_kobo, s)


@router.get("/customers/{customer_id}/accounts")
def customer_accounts(customer_id: str, uow=Depends(get_uow)):
    return accounts.customer_accounts(uow, customer_id)
