from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import get_uow
from app.core.config import Settings, get_settings
from app.identity.api import schemas
from app.identity.api.deps import get_voice
from app.identity.application import enrolment
from app.identity.application.verification import Voice
from app.identity.domain.entities import EnrolmentSession
from app.identity.domain.prompts import LANGUAGES, guide

router = APIRouter(prefix="/enrolment", tags=["enrolment"])


def session_out(sess: EnrolmentSession) -> schemas.SessionOut:
    accepted = sess.accepted()
    next_step = next((i for i in range(sess.required_samples) if i not in accepted), None)
    g = guide(sess.language)
    name = sess.customer.display_name
    return schemas.SessionOut(
        id=sess.id, customer_id=sess.customer_id, language=sess.language, status=sess.status, prompts=sess.prompts,
        required_samples=sess.required_samples, accepted_samples=len(accepted),
        next_step=next_step if sess.status == "in_progress" else None,
        guide={"welcome": g["welcome"].format(name=name),
               "step": g["step"].format(n=(next_step or 0) + 1, total=sess.required_samples),
               "done": g["done"].format(name=name)},
        samples=[schemas.SampleOut(id=s.id, step_index=s.step_index, accepted=s.accepted, quality=s.quality, spoof_score=s.spoof_score)
                 for s in sess.samples],
    )


@router.get("/languages")
def languages():
    return [{"code": k, "name": v} for k, v in LANGUAGES.items()]


@router.post("/sessions", response_model=schemas.SessionOut, status_code=201)
def create_session(body: schemas.SessionCreate, uow=Depends(get_uow), s: Settings = Depends(get_settings)):
    return session_out(enrolment.start(uow, body.customer_id, body.language, s))


@router.get("/sessions/{session_id}", response_model=schemas.SessionOut)
def get_session(session_id: str, uow=Depends(get_uow)):
    return session_out(enrolment.load(uow, session_id))


@router.post("/sessions/{session_id}/samples", response_model=schemas.SampleOut)
async def add_sample(session_id: str, step_index: int = Form(...), audio: UploadFile = File(...), uow=Depends(get_uow),
                     s: Settings = Depends(get_settings), voice: Voice = Depends(get_voice)):
    r = enrolment.add_sample(uow, session_id, step_index, await audio.read(), s, voice.decoder, voice.embedder,
                             voice.antispoof, voice.cipher)
    sm = r.sample
    return schemas.SampleOut(id=sm.id, step_index=sm.step_index, accepted=sm.accepted, quality=sm.quality,
                             spoof_score=sm.spoof_score, message=r.message)


@router.post("/sessions/{session_id}/complete", response_model=schemas.CompleteOut)
def complete_session(session_id: str, uow=Depends(get_uow), voice: Voice = Depends(get_voice)):
    done = enrolment.complete(uow, session_id, voice.embedder, voice.cipher)
    return schemas.CompleteOut(session_id=done.session.id, customer_id=done.session.customer_id,
                               template=schemas.TemplateOut.model_validate(done.template, from_attributes=True),
                               message=done.message, warnings=done.warnings)
