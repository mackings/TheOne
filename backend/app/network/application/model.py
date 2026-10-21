"""Training, storing and reading the shadow risk model."""
from __future__ import annotations

import json
from datetime import datetime

from app.core.errors import Conflict
from app.network.application.analysis import cache
from app.network.application.ports import NetworkUnitOfWork
from app.network.domain import risk_model
from app.network.domain.engine import Analysis
from app.network.domain.entities import TrainedModel

KEY = "risk_model"
INTERNALS = ("mean", "std", "weights", "bias", "features")


def load(uow: NetworkUnitOfWork) -> dict | None:
    row = uow.models.get(KEY)
    return json.loads(row.payload) if row else None


def score_account(uow: NetworkUnitOfWork, a: Analysis, account_id: str) -> dict | None:
    mdl = load(uow)
    return risk_model.score(mdl, a, account_id) if mdl else None


def train(uow: NetworkUnitOfWork, flag: float) -> dict:
    labels = {lab.account_id: (lab.label, lab.source) for lab in uow.labels.all()}
    try:
        payload = risk_model.train(labels, cache.get(uow), flag)
    except ValueError as e:
        raise Conflict(str(e)) from e
    row = uow.models.get(KEY) or uow.models.add(TrainedModel(key=KEY))
    row.payload = json.dumps(payload)
    row.trained_at = datetime.fromisoformat(payload["trained_at"])
    uow.commit()
    return {k: v for k, v in payload.items() if k not in INTERNALS}


def status(uow: NetworkUnitOfWork, flag: float) -> dict:
    """How the model was trained, how it compares with the rules, and where the two disagree."""
    mdl = load(uow)
    if not mdl:
        return {"trained": False, "min_each": risk_model.MIN_EACH, "has_labels": bool(uow.labels.all())}
    return {"trained": True, **{k: v for k, v in mdl.items() if k not in INTERNALS},
            "disagreements": risk_model.disagreements(mdl, cache.get(uow), flag)}
