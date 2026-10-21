"""The analysis as a whole: run it, its summary and counts, the CSV report and, on simulated data, evaluation."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from app.api.deps import get_uow
from app.core.config import Settings, get_settings
from app.network.api.reports import rings_csv
from app.network.application import queries
from app.network.application.analysis import cache
from app.network.application.evaluation import evaluate

router = APIRouter()


@router.post("/analyse")
def analyse(uow=Depends(get_uow), s: Settings = Depends(get_settings)):
    return queries.summary_out(cache.run(uow), s)


@router.get("/summary")
def summary(uow=Depends(get_uow), s: Settings = Depends(get_settings)):
    return queries.summary_out(cache.get(uow), s)


@router.get("/stats")
def stats(uow=Depends(get_uow)):
    return queries.stats(uow)


@router.get("/report.csv", response_class=PlainTextResponse)
def report_csv(uow=Depends(get_uow)):
    """Ring summary for fraud reporting (a working export, not the official NIBSS template)."""
    return PlainTextResponse(rings_csv.render(cache.get(uow)), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={rings_csv.FILENAME}"})


@router.get("/evaluation")
def evaluation(uow=Depends(get_uow), s: Settings = Depends(get_settings)):
    return evaluate(cache.get(uow), s)
