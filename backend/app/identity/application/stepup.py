"""Device-biometric step-up: fingerprint or face through the phone's secure hardware.

Attested (use this): the phone registers an ECDSA P-256 public key from its hardware keystore,
whose private key only signs after a strong biometric. The server issues a one-time challenge,
the phone signs it after the fingerprint prompt, and the server verifies the signature. Only
attested events can resolve a held transfer.

Legacy, unattested: the app reports that the prompt passed. Kept for demos and marked
"unattested"; it cannot resolve transfer decisions while NETWORK_REQUIRE_ATTESTED_DEVICE is on.

Not yet done: verifying the Android key-attestation certificate chain, which proves the key lives
in secure hardware rather than in software.
"""
from __future__ import annotations

import base64
import secrets
from datetime import timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.config import Settings
from app.core.errors import Conflict, Forbidden, Gone, Invalid, NotFound
from app.core.timeutil import now
from app.identity.application import customers
from app.identity.application.ports import IdentityUnitOfWork
from app.identity.domain.entities import DeviceKey, StepUpChallenge, VerificationEvent

METHODS = {"fingerprint", "face", "device_credential"}


def _method(method: str) -> None:
    if method not in METHODS:
        raise Invalid(f"method must be one of {sorted(METHODS)}")


def _event_of(uow: IdentityUnitOfWork, event_id: str, customer_id: str, what: str = "event to resolve") -> VerificationEvent:
    ev = uow.events.get(event_id)
    if not ev or ev.customer_id != customer_id:
        raise NotFound(f"{what} not found for this customer")
    return ev


def unattested(uow: IdentityUnitOfWork, customer_id: str, method: str, resolves_event_id: str | None, context: str | None,
               device_id: str | None, device_model: str | None, signature: str | None) -> VerificationEvent:
    customer = customers.load(uow, customer_id)
    _method(method)
    if resolves_event_id:
        context = context or _event_of(uow, resolves_event_id, customer.id).context
    reasons = [f"device biometric ({method}) passed on {device_model or 'unknown device'}"]
    if not signature:
        reasons.append("unattested: client-reported result only (bind to a hardware key before pilot)")
    ev = uow.events.add(VerificationEvent(
        customer_id=customer.id, context=context, modality="device", resolves_event_id=resolves_event_id, match_score=1.0,
        spoof_score=0.0, spoof_model=f"device-biometric:{method}", decision="ACCEPT", reasons=reasons,
        quality={"device_id": device_id, "device_model": device_model, "attested": bool(signature)}))
    uow.commit()
    return ev


def _public_key(der_b64: str) -> ec.EllipticCurvePublicKey:
    try:
        key = serialization.load_der_public_key(base64.b64decode(der_b64))
    except Exception as exc:  # noqa: BLE001
        raise Invalid(f"public_key is not a valid DER public key: {exc}") from exc
    if not isinstance(key, ec.EllipticCurvePublicKey) or key.curve.name != "secp256r1":
        raise Invalid("public_key must be an EC P-256 key")
    return key


def register_key(uow: IdentityUnitOfWork, customer_id: str, public_key: str, label: str) -> tuple[DeviceKey, bool]:
    customer = customers.load(uow, customer_id)
    der = _public_key(public_key).public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    existing = next((k for k in uow.device_keys.active_for(customer.id) if k.public_key_der == der), None)
    if existing:
        return existing, False
    k = uow.device_keys.add(DeviceKey(customer_id=customer.id, label=label, public_key_der=der))
    uow.commit()
    return k, True


def revoke_key(uow: IdentityUnitOfWork, key_id: str) -> None:
    k = uow.device_keys.get(key_id)
    if not k:
        raise NotFound("device key not found")
    k.revoked_at = now()
    uow.commit()


def challenge(uow: IdentityUnitOfWork, customer_id: str, device_key_id: str, resolves_event_id: str | None,
              context: str | None, s: Settings) -> StepUpChallenge:
    customer = customers.load(uow, customer_id)
    k = uow.device_keys.get(device_key_id)
    if not k or k.customer_id != customer.id or k.revoked_at is not None:
        raise NotFound("active device key not found for this customer")
    if resolves_event_id:
        _event_of(uow, resolves_event_id, customer.id)
    ch = StepUpChallenge(customer_id=customer.id, device_key_id=k.id, nonce=secrets.token_urlsafe(32),
                         resolves_event_id=resolves_event_id, context=context,
                         expires_at=now() + timedelta(seconds=s.stepup_challenge_ttl_s))
    ch.payload = f"theone-stepup:v1:{ch.id}:{ch.nonce}:{customer.id}:{resolves_event_id or '-'}"
    uow.challenges.add(ch)
    uow.commit()
    return ch


def attested(uow: IdentityUnitOfWork, challenge_id: str, signature: str, method: str, device_model: str | None) -> VerificationEvent:
    ch = uow.challenges.get(challenge_id)
    if not ch:
        raise NotFound("challenge not found")
    if ch.used_at is not None:
        raise Conflict("challenge already used")
    if ch.expires_at < now():
        raise Gone("challenge expired; request a new one")
    _method(method)
    k = uow.device_keys.get(ch.device_key_id)
    if not k or k.revoked_at is not None:
        raise Forbidden("device key revoked")
    try:
        serialization.load_der_public_key(k.public_key_der).verify(base64.b64decode(signature), ch.payload.encode(),
                                                                    ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, ValueError) as exc:
        raise Invalid("signature does not verify against the registered device key") from exc
    ch.used_at = k.last_used_at = now()
    reasons = [f"device biometric ({method}) unlocked the hardware key on {device_model or 'the registered device'}",
               "attested: challenge signed by the registered device key"]
    ev = uow.events.add(VerificationEvent(
        customer_id=ch.customer_id, context=ch.context, modality="device", resolves_event_id=ch.resolves_event_id,
        match_score=1.0, spoof_score=0.0, spoof_model=f"device-key:{method}", decision="ACCEPT", reasons=reasons,
        quality={"attested": True, "device_key_id": k.id, "challenge_id": ch.id, "device_model": device_model}))
    uow.commit()
    return ev
