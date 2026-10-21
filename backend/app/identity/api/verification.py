from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import get_uow
from app.core.config import Settings, get_settings
from app.identity.api import schemas
from app.identity.api.deps import get_voice
from app.identity.application import verification
from app.identity.application.verification import Scored, Voice
from app.identity.domain.entities import ContinuousSession

router = APIRouter(prefix="/verify", tags=["verification"])


def verify_out(r: Scored) -> schemas.VerifyOut:
    ev = r.event
    return schemas.VerifyOut(event_id=ev.id, customer_id=ev.customer_id, match_score=ev.match_score, spoof_score=ev.spoof_score,
                             spoof_model=ev.spoof_model, spoof_signals=r.signals, decision=ev.decision, reasons=ev.reasons,
                             quality=ev.quality, context=ev.context)


def session_out(cs: ContinuousSession, last: schemas.VerifyOut | None = None) -> schemas.ContinuousOut:
    return schemas.ContinuousOut(id=cs.id, customer_id=cs.customer_id, status=cs.status, ema_score=cs.ema_score,
                                 chunk_count=cs.chunk_count, last_decision=cs.last_decision, context=cs.context, last_event=last)


@router.post("", response_model=schemas.VerifyOut)
async def verify(customer_id: str = Form(...), context: str | None = Form(default=None), audio: UploadFile = File(...),
                 uow=Depends(get_uow), s: Settings = Depends(get_settings), voice: Voice = Depends(get_voice)):
    """One-shot verification: compare an utterance with the customer's template."""
    return verify_out(verification.verify(uow, customer_id, context, await audio.read(), s, voice))


@router.post("/continuous/sessions", response_model=schemas.ContinuousOut, status_code=201)
def start_continuous(body: schemas.ContinuousCreate, uow=Depends(get_uow)):
    return session_out(verification.start_session(uow, body.customer_id, body.context))


@router.get("/continuous/sessions/{session_id}", response_model=schemas.ContinuousOut)
def get_continuous(session_id: str, uow=Depends(get_uow)):
    return session_out(verification.load_session(uow, session_id))


@router.post("/continuous/sessions/{session_id}/chunks", response_model=schemas.ContinuousOut)
async def add_chunk(session_id: str, audio: UploadFile = File(...), uow=Depends(get_uow), s: Settings = Depends(get_settings),
                    voice: Voice = Depends(get_voice)):
    """A short audio chunk (2-5 s) from an ongoing call."""
    cs, scored = verification.add_chunk(uow, session_id, await audio.read(), s, voice)
    return session_out(cs, verify_out(scored))


@router.post("/continuous/sessions/{session_id}/end", response_model=schemas.ContinuousOut)
def end_continuous(session_id: str, uow=Depends(get_uow)):
    return session_out(verification.end_session(uow, session_id))
