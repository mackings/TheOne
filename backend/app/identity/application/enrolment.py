"""Voice enrolment: a session of guided phrases, each sample checked for quality and liveness, then
one encrypted template built from the accepted samples."""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.core.errors import Conflict, Invalid, NotFound, Unsupported
from app.core.timeutil import now
from app.identity.application import customers
from app.identity.application.ports import AntiSpoofScorer, AudioDecoder, Cipher, IdentityUnitOfWork, SpeakerEmbedder
from app.identity.domain.entities import EnrolmentSession, VoiceSample, VoiceTemplate
from app.identity.domain.matcher import build_template
from app.identity.domain.prompts import LANGUAGES, guide, pick_phrases

MIN_CONSISTENCY = 0.45


@dataclass
class SampleResult:
    sample: VoiceSample
    message: str | None


@dataclass
class Completed:
    session: EnrolmentSession
    template: VoiceTemplate
    message: str
    warnings: list[str]


def start(uow: IdentityUnitOfWork, customer_id: str, language: str | None, s: Settings) -> EnrolmentSession:
    c = customers.load(uow, customer_id)
    lang = language or c.language
    if lang not in LANGUAGES:
        raise Invalid("unsupported language")
    sess = uow.enrolments.add(EnrolmentSession(customer_id=c.id, language=lang, prompts=pick_phrases(lang, s.enrolment_samples_required),
                                               required_samples=s.enrolment_samples_required))
    uow.commit()
    return sess


def load(uow: IdentityUnitOfWork, session_id: str) -> EnrolmentSession:
    sess = uow.enrolments.get(session_id)
    if not sess:
        raise NotFound("enrolment session not found")
    return sess


def add_sample(uow: IdentityUnitOfWork, session_id: str, step_index: int, audio: bytes, s: Settings, decoder: AudioDecoder,
               embedder: SpeakerEmbedder, antispoof: AntiSpoofScorer, cipher: Cipher) -> SampleResult:
    sess = load(uow, session_id)
    if sess.status != "in_progress":
        raise Conflict(f"session is {sess.status}")
    if not 0 <= step_index < sess.required_samples:
        raise Invalid("step_index out of range")
    try:
        wav, sr = decoder.decode(audio, s.target_sample_rate)
    except ValueError as exc:
        raise Unsupported(str(exc)) from exc
    q = decoder.assess_quality(wav, sr, s.min_sample_seconds, s.max_sample_seconds)
    sample = VoiceSample(session_id=sess.id, step_index=step_index, quality=q.as_dict(), accepted=False)
    message = None
    if q.ok:
        spoof = antispoof.score(wav, sr)
        sample.spoof_score = spoof.score
        if spoof.score >= s.spoof_reject_threshold:
            message = guide(sess.language)["retry"].format(issue="The recording did not sound like live speech.")
        else:
            try:
                emb = embedder.embed(wav, sr)
            except ValueError as exc:
                raise Invalid(str(exc)) from exc
            sample.embedding_enc = cipher.encrypt_vector(emb)
            sample.embedding_dim = int(emb.shape[0])
            sample.accepted = True
    else:
        message = guide(sess.language)["retry"].format(issue=" ".join(q.issues))
    uow.add(sample)
    uow.commit()
    return SampleResult(sample, message)


def complete(uow: IdentityUnitOfWork, session_id: str, embedder: SpeakerEmbedder, cipher: Cipher) -> Completed:
    sess = load(uow, session_id)
    if sess.status != "in_progress":
        raise Conflict(f"session is {sess.status}")
    accepted = sess.accepted()
    if len(accepted) < sess.required_samples:
        raise Conflict(f"{len(accepted)}/{sess.required_samples} samples accepted")
    built = build_template([cipher.decrypt_vector(sm.embedding_enc, sm.embedding_dim) for sm in accepted.values()])
    warnings = []
    if built.consistency < MIN_CONSISTENCY:
        warnings.append(f"enrolment samples are inconsistent (mean similarity {built.consistency:.2f}); "
                        "consider re-enrolling in a quieter environment")
    customer = sess.customer
    if customer.template:
        uow.delete(customer.template)
        uow.flush()
    tpl = VoiceTemplate(customer_id=customer.id, embedding_enc=cipher.encrypt_vector(built.template), dim=int(built.template.shape[0]),
                        model_name=embedder.name, sample_count=built.sample_count, consistency=round(built.consistency, 4))
    uow.add(tpl)
    sess.status, sess.completed_at = "completed", now()
    for sm in sess.samples:
        sm.embedding_enc = None
    uow.commit()
    return Completed(sess, tpl, guide(sess.language)["done"].format(name=customer.display_name), warnings)
