"""Fraud-desk alerts."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_uow
from app.network.api.schemas import AckIn
from app.network.application import alerts

router = APIRouter()


@router.get("/alerts")
def alert_list(open_only: bool = True, limit: int = 50, uow=Depends(get_uow)):
    return alerts.list_alerts(uow, open_only, limit)


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: str, body: AckIn, uow=Depends(get_uow)):
    return alerts.acknowledge(uow, alert_id, body.actor)
