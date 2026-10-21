"""Fraud-desk alerts: duress signals, safe-limit breaches and review-cap holds."""
from __future__ import annotations

from typing import Protocol

from app.core.errors import NotFound
from app.core.timeutil import now
from app.network.application.ports import AlertRepository, NetworkUnitOfWork
from app.network.domain.entities import Alert, AnalystAction


class HasAlerts(Protocol):
    alerts: AlertRepository


def raise_alert(uow: HasAlerts, kind: str, message: str, *, severity: str = "high", customer_id: str | None = None,
                account_id: str | None = None, decision_id: str | None = None, event_id: str | None = None,
                context: dict | None = None) -> Alert:
    return uow.alerts.add(Alert(kind=kind, severity=severity, message=message, customer_id=customer_id,
                                account_id=account_id, decision_id=decision_id, event_id=event_id, context=context))


def alert_out(a: Alert) -> dict:
    return {"id": a.id, "created_at": a.created_at.isoformat(), "kind": a.kind, "severity": a.severity,
            "customer_id": a.customer_id, "account_id": a.account_id, "decision_id": a.decision_id, "event_id": a.event_id,
            "message": a.message, "context": a.context, "acknowledged_by": a.acknowledged_by,
            "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None}


def list_alerts(uow: NetworkUnitOfWork, open_only: bool = True, limit: int = 50) -> list[dict]:
    return [alert_out(a) for a in uow.alerts.newest(open_only, max(1, min(limit, 500)))]


def acknowledge(uow: NetworkUnitOfWork, alert_id: str, actor: str) -> dict:
    a = uow.alerts.get(alert_id)
    if not a:
        raise NotFound("alert not found")
    if a.acknowledged_at is None:
        a.acknowledged_by, a.acknowledged_at = actor, now()
        uow.actions.add(AnalystAction(actor=actor, action="ack_alert", decision_id=a.decision_id,
                                      account_ids=[a.account_id] if a.account_id else [], note=a.kind))
        uow.commit()
    return alert_out(a)
