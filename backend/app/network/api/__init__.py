"""HTTP API for the mule network, mounted at /network. One module per area; each is thin and
calls the application use cases, which do the work."""
from fastapi import APIRouter

from app.network.api import accounts, alerts, analysis, bank_actions, decisions, demo, ingest, learning, rings, statements

router = APIRouter(prefix="/network", tags=["mule network"])
for area in (ingest, bank_actions, analysis, rings, accounts, decisions, alerts, statements, learning, demo):
    router.include_router(area.router)

__all__ = ["router"]
