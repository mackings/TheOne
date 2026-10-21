from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CustomerCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    external_id: str | None = Field(default=None, max_length=64)
    language: str = "en"


class CustomerOut(BaseModel):
    id: str
    external_id: str | None
    display_name: str
    language: str
    created_at: datetime
    enrolled: bool
    template: TemplateOut | None = None
    iris_enrolled: bool = False
    iris_template: IrisTemplateOut | None = None
    iris_duress_enrolled: bool = False


class IrisTemplateOut(BaseModel):
    id: str
    model_name: str
    sample_count: int
    consistency_hd: float
    quality: dict
    created_at: datetime


class IrisFrameOut(BaseModel):
    index: int
    quality: dict
    hamming: float | None = None


class IrisEnrolOut(BaseModel):
    customer_id: str
    template: IrisTemplateOut
    frames: list[IrisFrameOut]
    liveness: dict
    message: str
    warnings: list[str]


class IrisVerifyOut(BaseModel):
    event_id: str
    customer_id: str
    hamming_distance: float
    match_score: float
    accept_hd: float
    decision: str
    reasons: list[str]
    liveness: dict
    frames: list[IrisFrameOut]
    resolves_event_id: str | None


class TemplateOut(BaseModel):
    id: str
    model_name: str
    dim: int
    sample_count: int
    consistency: float
    created_at: datetime
    updated_at: datetime


class SessionCreate(BaseModel):
    customer_id: str
    language: str | None = None


class SampleOut(BaseModel):
    id: str
    step_index: int
    accepted: bool
    quality: dict
    spoof_score: float | None
    message: str | None = None


class SessionOut(BaseModel):
    id: str
    customer_id: str
    language: str
    status: str
    prompts: list[str]
    required_samples: int
    accepted_samples: int
    next_step: int | None
    guide: dict[str, str]
    samples: list[SampleOut]


class CompleteOut(BaseModel):
    session_id: str
    customer_id: str
    template: TemplateOut
    message: str
    warnings: list[str]


class VerifyOut(BaseModel):
    event_id: str
    customer_id: str
    match_score: float
    spoof_score: float
    spoof_model: str
    spoof_signals: dict[str, float]
    decision: str
    reasons: list[str]
    quality: dict
    context: str | None


class ContinuousCreate(BaseModel):
    customer_id: str
    context: str | None = None


class ContinuousOut(BaseModel):
    id: str
    customer_id: str
    status: str
    ema_score: float | None
    chunk_count: int
    last_decision: str | None
    context: str | None
    last_event: VerifyOut | None = None


class EventOut(BaseModel):
    id: str
    customer_id: str
    continuous_session_id: str | None
    context: str | None
    modality: str = "voice"
    resolves_event_id: str | None = None
    duress: bool = False
    match_score: float
    spoof_score: float
    spoof_model: str
    decision: str
    reasons: list[str]
    quality: dict
    created_at: datetime


class HealthOut(BaseModel):
    status: str
    embedder: str
    embedding_dim: int
    antispoof: str
    accepted_formats: list[str]
    thresholds: dict[str, float]


class IrisDuressEnrolOut(BaseModel):
    customer_id: str
    frames_used: int
    consistency_hd: float
    distance_from_normal_eye: float
    liveness: dict
    message: str
