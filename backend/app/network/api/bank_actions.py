"""The outbox of actions sent to the bank (holds, removals, post-no-debit blocks)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_bank, get_uow
from app.core.config import Settings, get_settings
from app.network.application import bank_actions

router = APIRouter()


@router.get("/bank-actions")
def bank_action_list(status: str | None = None, limit: int = 100, uow=Depends(get_uow)):
    return bank_actions.recent(uow, status, limit)


@router.post("/bank-actions/{action_id}/retry")
def retry_bank_action(action_id: str, uow=Depends(get_uow), bank=Depends(get_bank), s: Settings = Depends(get_settings)):
    return bank_actions.retry(uow, action_id, bank, s)
