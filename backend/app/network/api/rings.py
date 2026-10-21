"""Mule rings: the list, one ring's money map, analyst actions, cross-bank traces and the evidence pack."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from app.api.deps import get_bank, get_nibss, get_role, get_uow
from app.core.config import Settings, get_settings
from app.network.api.reports import evidence as evidence_pack
from app.network.api.schemas import RingActionIn, TraceIn
from app.network.application import actions, queries, tracing
from app.network.application.analysis import cache

router = APIRouter()


@router.get("/rings")
def rings(status: str | None = None, uow=Depends(get_uow)):
    return queries.list_rings(cache.get(uow), status)


@router.get("/rings/{ring_id}")
def ring_detail(ring_id: str, uow=Depends(get_uow)):
    return queries.ring_detail(uow, ring_id)


@router.post("/rings/{ring_id}/actions")
def ring_action(ring_id: str, body: RingActionIn, uow=Depends(get_uow), role: str = Depends(get_role),
                bank=Depends(get_bank), s: Settings = Depends(get_settings)):
    return actions.ring_action(uow, queries.ring_key(uow, ring_id), body.action, body.account_ids, body.actor, body.note,
                               role, bank, s)


@router.post("/rings/{ring_id}/trace")
def trace_ring(ring_id: str, body: TraceIn, uow=Depends(get_uow), nibss=Depends(get_nibss), s: Settings = Depends(get_settings)):
    """Follow money that left this ring to other banks, through NIBSS, and add what comes back to the map."""
    rid = queries.ring_graph(cache.get(uow), ring_id)["id"]
    return tracing.trace_ring(uow, rid, body.actor, nibss, s, depth=body.depth)


@router.get("/rings/{ring_id}/traces")
def ring_traces(ring_id: str, uow=Depends(get_uow)):
    return tracing.trace_log(uow, queries.ring_key(uow, ring_id))


@router.get("/rings/{ring_id}/evidence", response_class=HTMLResponse)
def evidence(ring_id: str, uow=Depends(get_uow), s: Settings = Depends(get_settings)):
    """Printable evidence pack: how the money moved, why each account was flagged, analyst actions."""
    a = cache.get(uow)
    g = queries.ring_graph(a, ring_id)
    return HTMLResponse(evidence_pack.render(g, queries.ring_actions(uow, g["id"]), s.network_home_bank_name, a.computed_at))
