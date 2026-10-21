"""Voice verification: one utterance against the template, or a call verified continuously, chunk by chunk."""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.core.errors import Conflict, Invalid, NotFound, Unsupported
from app.core.timeutil import now
from app.identity.application import customers
from app.identity.application.ports import AntiSpoofScorer, AudioDecoder, Cipher, IdentityUnitOfWork, SpeakerEmbedder
from app.identity.domain.entities import ContinuousSession, Customer, VerificationEvent
from app.identity.domain.matcher import cosine
from app.identity.domain.policy import Decision, Thresholds, decide


@dataclass
class Voice:
    decoder: AudioDecoder
    embedder: SpeakerEmbedder
    antispoof: AntiSpoofScorer
    cipher: Cipher


@dataclass
class Scored:
    event: VerificationEvent
    signals: dict[str, float]
    raw_match: float


def thresholds(s: Settings) -> Thresholds:
    return Thresholds(match_accept=s.match_accept_threshold, match_stepup=s.match_stepup_threshold,
                      spoof_stepup=s.spoof_stepup_threshold, spoof_reject=s.spoof_reject_threshold,
                      high_risk_margin=s.high_risk_accept_margin)


def _score(customer: Customer, audio: bytes, context: str | None, s: Settings, v: Voice, min_seconds: float | None = None) -> Scored:
    tpl = customer.template
    if not tpl:
        raise Conflict("customer has no voice template; enrol first")
    try:
        wav, sr = v.decoder.decode(audio, s.target_sample_rate)
    except ValueError as exc:
        raise Unsupported(str(exc)) from exc
    floor = min_seconds or s.min_sample_seconds
    q = v.decoder.assess_quality(wav, sr, floor, s.max_sample_seconds)
    if q.duration_s < floor:
        raise Invalid(f"audio too short ({q.duration_s}s)")
    try:
        emb = v.embedder.embed(wav, sr)
    except ValueError as exc:
        raise Invalid(str(exc)) from exc
    if tpl.model_name != v.embedder.name:
        raise Conflict(f"template was built with {tpl.model_name}; re-enrol with {v.embedder.name}")
    raw = cosine(emb, v.cipher.decrypt_vector(tpl.embedding_enc, tpl.dim))
    spoof = v.antispoof.score(wav, sr)
    result = decide(raw, spoof.score, context, thresholds(s))
    if not q.ok:
        result.reasons.append("audio quality warnings: " + "; ".join(q.issues))
    ev = VerificationEvent(customer_id=customer.id, context=context, match_score=round(raw, 4), spoof_score=spoof.score,
                           spoof_model=spoof.model, decision=result.decision.value, reasons=result.reasons, quality=q.as_dict())
    return Scored(ev, spoof.signals, raw)


def verify(uow: IdentityUnitOfWork, customer_id: str, context: str | None, audio: bytes, s: Settings, v: Voice) -> Scored:
    scored = _score(customers.load(uow, customer_id), audio, context, s, v)
    uow.events.add(scored.event)
    uow.commit()
    return scored


def load_session(uow: IdentityUnitOfWork, session_id: str) -> ContinuousSession:
    cs = uow.continuous_sessions.get(session_id)
    if not cs:
        raise NotFound("continuous session not found")
    return cs


def start_session(uow: IdentityUnitOfWork, customer_id: str, context: str | None) -> ContinuousSession:
    c = customers.load(uow, customer_id)
    if not c.template:
        raise Conflict("customer has no voice template; enrol first")
    cs = uow.continuous_sessions.add(ContinuousSession(customer_id=c.id, context=context))
    uow.commit()
    return cs


def add_chunk(uow: IdentityUnitOfWork, session_id: str, audio: bytes, s: Settings, v: Voice) -> tuple[ContinuousSession, Scored]:
    """The session keeps a moving average of the match score and decides on that, so one noisy chunk
    does not drop the call while a sustained change of speaker degrades it within a few chunks."""
    cs = load_session(uow, session_id)
    if cs.status == "ended":
        raise Conflict("session has ended")
    scored = _score(customers.load(uow, cs.customer_id), audio, cs.context, s, v, min_seconds=1.0)
    ev, raw = scored.event, scored.raw_match
    alpha = s.continuous_ema_alpha
    ema = raw if cs.ema_score is None else (1 - alpha) * cs.ema_score + alpha * raw
    result = decide(ema, ev.spoof_score, cs.context, thresholds(s))
    ev.decision = result.decision.value
    ev.reasons = [f"rolling score {ema:.2f} (chunk {raw:.2f})", *result.reasons]
    ev.continuous_session_id = cs.id
    cs.ema_score = round(ema, 4)
    cs.chunk_count += 1
    cs.last_decision = ev.decision
    cs.status = "active" if result.decision == Decision.ACCEPT else "degraded"
    uow.events.add(ev)
    uow.commit()
    return cs, scored


def end_session(uow: IdentityUnitOfWork, session_id: str) -> ContinuousSession:
    cs = load_session(uow, session_id)
    cs.status, cs.ended_at = "ended", now()
    uow.commit()
    return cs
