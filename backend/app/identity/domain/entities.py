"""Biometric identity: customers, their voice and iris templates, device keys and verification events.

Relationship attributes (customer.template, customer.iris_template, customer.iris_duress,
session.samples, session.customer) are added by the infrastructure mapping."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.core.timeutil import new_id, now


@dataclass(eq=False)
class Customer:
    display_name: str
    external_id: str | None = None
    language: str = "en"
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=now)


@dataclass(eq=False)
class EnrolmentSession:
    customer_id: str
    language: str
    prompts: list
    required_samples: int
    status: str = "in_progress"
    completed_at: datetime | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=now)

    def accepted(self) -> dict[int, VoiceSample]:
        """The latest accepted sample for each step."""
        return {s.step_index: s for s in self.samples if s.accepted}


@dataclass(eq=False)
class VoiceSample:
    """One enrolment utterance. Only the encrypted embedding is kept; raw audio is discarded."""

    session_id: str
    step_index: int
    quality: dict
    accepted: bool = False
    spoof_score: float | None = None
    embedding_enc: bytes | None = None
    embedding_dim: int | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=now)


@dataclass(eq=False)
class VoiceTemplate:
    customer_id: str
    embedding_enc: bytes
    dim: int
    model_name: str
    sample_count: int
    consistency: float
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)


@dataclass(eq=False)
class IrisTemplate:
    customer_id: str
    code_enc: bytes
    mask_enc: bytes
    model_name: str
    sample_count: int
    consistency_hd: float
    quality: dict
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=now)


@dataclass(eq=False)
class IrisDuressTemplate:
    """The customer's other eye, enrolled as a silent duress signal: it verifies normally on screen,
    but any transfer it approves is held and the fraud desk is alerted."""

    customer_id: str
    code_enc: bytes
    mask_enc: bytes
    model_name: str
    consistency_hd: float
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=now)


@dataclass(eq=False)
class DeviceKey:
    """A hardware-backed public key from the customer's phone. Its private key only signs after a
    strong biometric on the device."""

    customer_id: str
    public_key_der: bytes
    label: str = ""
    algorithm: str = "ES256"
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=now)


@dataclass(eq=False)
class StepUpChallenge:
    customer_id: str
    device_key_id: str
    nonce: str
    expires_at: datetime
    payload: str = ""
    resolves_event_id: str | None = None
    context: str | None = None
    used_at: datetime | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=now)


@dataclass(eq=False)
class ContinuousSession:
    customer_id: str
    context: str | None = None
    status: str = "active"
    ema_score: float | None = None
    chunk_count: int = 0
    last_decision: str | None = None
    ended_at: datetime | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=now)


@dataclass(eq=False)
class VerificationEvent:
    customer_id: str
    match_score: float
    spoof_score: float
    spoof_model: str
    decision: str
    reasons: list
    quality: dict
    context: str | None = None
    modality: str = "voice"
    resolves_event_id: str | None = None
    continuous_session_id: str | None = None
    duress: bool = False
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=now)
