from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_uow
from app.core.config import Settings, get_settings
from app.identity.application import stepup
from app.identity.domain.entities import VerificationEvent

router = APIRouter(prefix="/stepup", tags=["step-up"])


class DeviceStepUpIn(BaseModel):
    customer_id: str
    method: str = Field(description="fingerprint | face | device_credential")
    resolves_event_id: str | None = None
    context: str | None = None
    device_id: str | None = Field(default=None, max_length=128)
    device_model: str | None = Field(default=None, max_length=128)
    nonce: str | None = None
    signature: str | None = None


class DeviceStepUpOut(BaseModel):
    event_id: str
    customer_id: str
    decision: str
    reasons: list[str]
    resolves_event_id: str | None


class RegisterKeyIn(BaseModel):
    customer_id: str
    public_key: str = Field(description="base64 DER SubjectPublicKeyInfo of an EC P-256 key")
    label: str = Field(default="", max_length=120)


class ChallengeIn(BaseModel):
    customer_id: str
    device_key_id: str
    resolves_event_id: str | None = None
    context: str | None = Field(default=None, max_length=64)


class AttestedStepUpIn(BaseModel):
    challenge_id: str
    signature: str = Field(description="base64 DER ECDSA-SHA256 signature over the challenge payload")
    method: str = "fingerprint"
    device_model: str | None = Field(default=None, max_length=128)


def _out(ev: VerificationEvent) -> DeviceStepUpOut:
    return DeviceStepUpOut(event_id=ev.id, customer_id=ev.customer_id, decision=ev.decision, reasons=ev.reasons,
                           resolves_event_id=ev.resolves_event_id)


@router.post("/device", response_model=DeviceStepUpOut)
def device_step_up(body: DeviceStepUpIn, uow=Depends(get_uow)):
    return _out(stepup.unattested(uow, body.customer_id, body.method, body.resolves_event_id, body.context, body.device_id,
                                  body.device_model, body.signature))


@router.post("/device/keys", status_code=201)
def register_key(body: RegisterKeyIn, uow=Depends(get_uow)):
    key, created = stepup.register_key(uow, body.customer_id, body.public_key, body.label)
    return {"device_key_id": key.id, "created": created}


@router.delete("/device/keys/{key_id}", status_code=204)
def revoke_key(key_id: str, uow=Depends(get_uow)):
    stepup.revoke_key(uow, key_id)


@router.post("/device/challenge")
def challenge(body: ChallengeIn, uow=Depends(get_uow), s: Settings = Depends(get_settings)):
    ch = stepup.challenge(uow, body.customer_id, body.device_key_id, body.resolves_event_id, body.context, s)
    return {"challenge_id": ch.id, "payload": ch.payload, "expires_at": ch.expires_at.isoformat()}


@router.post("/device/attested", response_model=DeviceStepUpOut)
def attested(body: AttestedStepUpIn, uow=Depends(get_uow)):
    return _out(stepup.attested(uow, body.challenge_id, body.signature, body.method, body.device_model))
