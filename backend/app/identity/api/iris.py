from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import get_uow
from app.core.config import Settings, get_settings
from app.core.errors import Invalid
from app.identity.api import schemas
from app.identity.api.deps import iris_engine
from app.identity.application import iris
from app.infrastructure.crypto import cipher

router = APIRouter(prefix="/iris", tags=["iris"])


def _hints(raw: str | None) -> list[iris.Hint]:
    """Iris circles from the browser's face-landmark model, one per image (or null), as JSON."""
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except ValueError as exc:
        raise Invalid(f"hints is not valid JSON: {exc}") from exc
    return [(float(h["cx"]), float(h["cy"]), float(h["r"])) if h else None for h in items]


async def _read(images: list[UploadFile]) -> list[bytes]:
    return [await up.read() for up in images[:iris.MAX_FRAMES]]


def _frames(codes: list, hds: list | None = None) -> list[schemas.IrisFrameOut]:
    return [schemas.IrisFrameOut(index=i, quality=c.quality.as_dict(), hamming=hds[i] if hds else None) for i, c in enumerate(codes)]


@router.post("/enrol", response_model=schemas.IrisEnrolOut)
async def enrol(customer_id: str = Form(...), images: list[UploadFile] = File(...), hints: str | None = Form(default=None),
                blink: bool | None = Form(default=None), eye: str | None = Form(default=None), uow=Depends(get_uow),
                s: Settings = Depends(get_settings)):
    """Enrol an iris from a burst of frames."""
    r = iris.enrol(uow, customer_id, await _read(images), _hints(hints), blink, eye, s, iris_engine, cipher)
    return schemas.IrisEnrolOut(customer_id=customer_id, template=schemas.IrisTemplateOut.model_validate(r.template, from_attributes=True),
                                frames=_frames(r.capture.codes), liveness=r.capture.liveness, message=r.message, warnings=r.warnings)


@router.post("/duress/enrol", response_model=schemas.IrisDuressEnrolOut)
async def enrol_duress(customer_id: str = Form(...), images: list[UploadFile] = File(...), hints: str | None = Form(default=None),
                       blink: bool | None = Form(default=None), uow=Depends(get_uow), s: Settings = Depends(get_settings)):
    """Enrol the customer's other eye as a silent duress signal."""
    r = iris.enrol_duress(uow, customer_id, await _read(images), _hints(hints), blink, s, iris_engine, cipher)
    return schemas.IrisDuressEnrolOut(customer_id=customer_id, frames_used=r.frames_used, consistency_hd=r.consistency_hd,
                                      distance_from_normal_eye=r.distance_from_normal_eye, liveness=r.liveness, message=r.message)


@router.post("/verify", response_model=schemas.IrisVerifyOut)
async def verify(customer_id: str = Form(...), resolves_event_id: str | None = Form(default=None),
                 context: str | None = Form(default=None), images: list[UploadFile] = File(...),
                 hints: str | None = Form(default=None), blink: bool | None = Form(default=None), uow=Depends(get_uow),
                 s: Settings = Depends(get_settings)):
    """Verify a burst of frames against the stored iris code: the step-up after a voice STEP_UP."""
    r = iris.verify(uow, customer_id, resolves_event_id, context, await _read(images), _hints(hints), blink, s, iris_engine, cipher)
    ev = r.event
    return schemas.IrisVerifyOut(event_id=ev.id, customer_id=customer_id, hamming_distance=round(r.hamming_distance, 4),
                                 match_score=ev.match_score, accept_hd=r.accept_hd, decision=ev.decision, reasons=ev.reasons,
                                 liveness=r.capture.liveness, frames=_frames(r.capture.codes, r.distances),
                                 resolves_event_id=resolves_event_id)
