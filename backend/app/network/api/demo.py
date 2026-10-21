"""Demo data endpoints. Refused unless NETWORK_SIMULATION_ENABLED is on."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_nibss, get_uow
from app.core.config import Settings, get_settings
from app.network.api.schemas import SimulateIn
from app.network.application import queries
from app.network.application.evaluation import evaluate
from app.network.dev import demo

router = APIRouter()


@router.post("/reset")
def reset(uow=Depends(get_uow), s: Settings = Depends(get_settings)):
    demo.require_simulation(s)
    demo.reset_network(uow)
    return {"reset": True}


@router.post("/simulate")
def simulate(body: SimulateIn, uow=Depends(get_uow), nibss=Depends(get_nibss), s: Settings = Depends(get_settings)):
    """Generate a synthetic Nigerian customer base with planted mule rings, then analyse it."""
    demo.require_simulation(s)
    if body.reset:
        demo.reset_network(uow)
    generated, a = demo.seed(uow, s, nibss, body.seed, body.customers, body.rings)
    return {"generated": generated, "summary": queries.summary_out(a, s), "evaluation": evaluate(a, s)}
