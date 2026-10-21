"""Learning from outcomes: confirmed labels, guarded weight learning, the backtest and the shadow risk model."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_uow
from app.core.config import Settings, get_settings
from app.network.api.schemas import BacktestIn, LabelIn
from app.network.application import backtest as backtest_run
from app.network.application import learning, model

router = APIRouter()


@router.post("/labels")
def add_labels(body: list[LabelIn], uow=Depends(get_uow)):
    """Confirmed investigation outcomes: an account is a mule or legitimate, and when that was known."""
    return {"labels": learning.add_labels(uow, [lab.model_dump() for lab in body])}


@router.get("/labels/summary")
def labels_summary(uow=Depends(get_uow)):
    return learning.labels_summary(uow)


@router.get("/learning")
def learning_view(uow=Depends(get_uow), s: Settings = Depends(get_settings)):
    return learning.view(uow, s)


@router.post("/learning/refresh")
def learning_refresh(uow=Depends(get_uow), s: Settings = Depends(get_settings)):
    return learning.refresh(uow, s)


@router.post("/backtest")
def backtest(body: BacktestIn, uow=Depends(get_uow), s: Settings = Depends(get_settings)):
    return backtest_run.run(uow, s, body.days, body.step_hours, body.capacity_per_day)


@router.get("/model")
def model_status(uow=Depends(get_uow), s: Settings = Depends(get_settings)):
    """The shadow risk model: how it was trained, how it compares with the rules, and where they disagree."""
    return model.status(uow, s.network_flag_threshold)


@router.post("/model/train")
def model_train(uow=Depends(get_uow), s: Settings = Depends(get_settings)):
    return model.train(uow, s.network_flag_threshold)
