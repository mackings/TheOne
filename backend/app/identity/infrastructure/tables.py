"""Identity tables, and the mapping of the identity entities onto them."""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, Column, Float, ForeignKey, Integer, LargeBinary, String, Table
from sqlalchemy.orm import relationship

from app.core.timeutil import new_id, now
from app.identity.domain import entities as e
from app.infrastructure.database import UtcDateTime, mapper_registry, metadata


def _id() -> Column:
    return Column("id", String(32), primary_key=True, default=new_id)


def _at(name: str, nullable: bool = False, **kw) -> Column:
    return Column(name, UtcDateTime(timezone=True), nullable=nullable, **kw)


customers = Table(
    "customers", metadata,
    _id(),
    Column("external_id", String(64), unique=True, nullable=True),
    Column("display_name", String(120), nullable=False),
    Column("language", String(8), default="en", nullable=False),
    _at("created_at", default=now),
)

enrolment_sessions = Table(
    "enrolment_sessions", metadata,
    _id(),
    Column("customer_id", ForeignKey("customers.id"), index=True, nullable=False),
    Column("language", String(8), nullable=False),
    Column("prompts", JSON, nullable=False),
    Column("required_samples", Integer, nullable=False),
    Column("status", String(16), default="in_progress", nullable=False),
    _at("created_at", default=now),
    _at("completed_at", nullable=True),
)

voice_samples = Table(
    "voice_samples", metadata,
    _id(),
    Column("session_id", ForeignKey("enrolment_sessions.id"), index=True, nullable=False),
    Column("step_index", Integer, nullable=False),
    Column("accepted", Boolean, default=False, nullable=False),
    Column("quality", JSON, nullable=False),
    Column("spoof_score", Float, nullable=True),
    Column("embedding_enc", LargeBinary, nullable=True),
    Column("embedding_dim", Integer, nullable=True),
    _at("created_at", default=now),
)

voice_templates = Table(
    "voice_templates", metadata,
    _id(),
    Column("customer_id", ForeignKey("customers.id"), unique=True, nullable=False),
    Column("embedding_enc", LargeBinary, nullable=False),
    Column("dim", Integer, nullable=False),
    Column("model_name", String(120), nullable=False),
    Column("sample_count", Integer, nullable=False),
    Column("consistency", Float, nullable=False),
    _at("created_at", default=now),
    _at("updated_at", default=now, onupdate=now),
)

iris_templates = Table(
    "iris_templates", metadata,
    _id(),
    Column("customer_id", ForeignKey("customers.id"), unique=True, nullable=False),
    Column("code_enc", LargeBinary, nullable=False),
    Column("mask_enc", LargeBinary, nullable=False),
    Column("model_name", String(64), nullable=False),
    Column("sample_count", Integer, nullable=False),
    Column("consistency_hd", Float, nullable=False),
    Column("quality", JSON, nullable=False),
    _at("created_at", default=now),
)

iris_duress_templates = Table(
    "iris_duress_templates", metadata,
    _id(),
    Column("customer_id", ForeignKey("customers.id"), unique=True, nullable=False),
    Column("code_enc", LargeBinary, nullable=False),
    Column("mask_enc", LargeBinary, nullable=False),
    Column("model_name", String(64), nullable=False),
    Column("consistency_hd", Float, nullable=False),
    _at("created_at", default=now),
)

device_keys = Table(
    "device_keys", metadata,
    _id(),
    Column("customer_id", ForeignKey("customers.id"), index=True, nullable=False),
    Column("label", String(120), default="", nullable=False),
    Column("public_key_der", LargeBinary, nullable=False),
    Column("algorithm", String(16), default="ES256", nullable=False),
    _at("created_at", default=now),
    _at("last_used_at", nullable=True),
    _at("revoked_at", nullable=True),
)

stepup_challenges = Table(
    "stepup_challenges", metadata,
    _id(),
    Column("customer_id", ForeignKey("customers.id"), index=True, nullable=False),
    Column("device_key_id", ForeignKey("device_keys.id"), nullable=False),
    Column("nonce", String(64), nullable=False),
    Column("payload", String(300), nullable=False),
    Column("resolves_event_id", String(32), nullable=True),
    Column("context", String(64), nullable=True),
    _at("created_at", default=now),
    _at("expires_at"),
    _at("used_at", nullable=True),
)

continuous_sessions = Table(
    "continuous_sessions", metadata,
    _id(),
    Column("customer_id", ForeignKey("customers.id"), index=True, nullable=False),
    Column("status", String(16), default="active", nullable=False),
    Column("ema_score", Float, nullable=True),
    Column("chunk_count", Integer, default=0, nullable=False),
    Column("last_decision", String(16), nullable=True),
    Column("context", String(64), nullable=True),
    _at("created_at", default=now),
    _at("ended_at", nullable=True),
)

verification_events = Table(
    "verification_events", metadata,
    _id(),
    Column("customer_id", ForeignKey("customers.id"), index=True, nullable=False),
    Column("continuous_session_id", ForeignKey("continuous_sessions.id"), nullable=True, index=True),
    Column("context", String(64), nullable=True),
    Column("modality", String(8), default="voice", nullable=False),
    Column("resolves_event_id", String(32), nullable=True),
    Column("match_score", Float, nullable=False),
    Column("spoof_score", Float, nullable=False),
    Column("spoof_model", String(64), nullable=False),
    Column("decision", String(16), nullable=False),
    Column("reasons", JSON, nullable=False),
    Column("quality", JSON, nullable=False),
    Column("duress", Boolean, default=False, nullable=False),
    _at("created_at", default=now),
)


def map_entities() -> None:
    m = mapper_registry.map_imperatively
    m(e.Customer, customers, properties={
        "template": relationship(e.VoiceTemplate, uselist=False, back_populates="customer"),
        "iris_template": relationship(e.IrisTemplate, uselist=False, back_populates="customer"),
        "iris_duress": relationship(e.IrisDuressTemplate, uselist=False),
    })
    m(e.EnrolmentSession, enrolment_sessions, properties={
        "customer": relationship(e.Customer),
        "samples": relationship(e.VoiceSample, back_populates="session", order_by=voice_samples.c.created_at),
    })
    m(e.VoiceSample, voice_samples, properties={"session": relationship(e.EnrolmentSession, back_populates="samples")})
    m(e.VoiceTemplate, voice_templates, properties={"customer": relationship(e.Customer, back_populates="template")})
    m(e.IrisTemplate, iris_templates, properties={"customer": relationship(e.Customer, back_populates="iris_template")})
    m(e.IrisDuressTemplate, iris_duress_templates)
    m(e.DeviceKey, device_keys)
    m(e.StepUpChallenge, stepup_challenges)
    m(e.ContinuousSession, continuous_sessions)
    m(e.VerificationEvent, verification_events)


map_entities()
