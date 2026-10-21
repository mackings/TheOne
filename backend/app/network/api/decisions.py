"""Real-time transfer decisions, and how they are resolved, reviewed and executed."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends

from app.api.deps import get_bank, get_nibss, get_uow, new_uow
from app.core.config import Settings, get_settings
from app.network.api.schemas import DecideIn, ResolveIn, ReviewIn
from app.network.application import decisions, queries

router = APIRouter()


@router.post("/decide")
def decide(body: DecideIn, uow=Depends(get_uow), s: Settings = Depends(get_settings)):
    """Real-time decision for an outbound transfer: ALLOW, WARN_PAYEE, STEP_UP_OWNER or HOLD."""
    return decisions.decide(uow, body.model_dump(), s)


@router.post("/decisions/{decision_id}/resolve")
def resolve(decision_id: str, body: ResolveIn, uow=Depends(get_uow), bank=Depends(get_bank), s: Settings = Depends(get_settings)):
    """Called by the customer's app after a step-up or payee warning. Returns the client view."""
    return decisions.resolve(uow, decision_id, body.verification_event_id, body.customer_confirmed, bank, s,
                             bank_factor_passed=body.bank_factor_passed)


@router.post("/decisions/{decision_id}/review")
def review(decision_id: str, body: ReviewIn, uow=Depends(get_uow)):
    return decisions.review(uow, decision_id, body.outcome, body.actor, body.note)


@router.post("/decisions/{decision_id}/execute")
def execute_decision(decision_id: str, background: BackgroundTasks, uow=Depends(get_uow), nibss=Depends(get_nibss),
                     s: Settings = Depends(get_settings)):
    """Record that an allowed or released transfer was sent. In production the bank's transfer feed
    does this; the demo app calls it."""
    out = decisions.execute(uow, decision_id, s, nibss)
    # A silent duress hold returns no references, so it leaves no trace.
    if "_refs" in out:
        background.add_task(queries.refresh, new_uow, out.pop("_refs"))
    return out


@router.get("/decisions")
def decision_list(limit: int = 50, uow=Depends(get_uow)):
    return decisions.list_decisions(uow, limit)
