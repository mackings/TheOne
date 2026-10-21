"""Iris enrolment and verification from a burst of camera frames, and the silent duress eye."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import Settings
from app.core.errors import Conflict, Invalid, NotFound, Unsupported
from app.identity.application import customers
from app.identity.application.ports import Cipher, IdentityUnitOfWork, IrisEngine
from app.identity.domain.entities import IrisDuressTemplate, IrisTemplate, VerificationEvent
from app.identity.domain.policy import Decision
from app.network.application.alerts import raise_alert

MAX_FRAMES = 24
Hint = tuple[float, float, float] | None


@dataclass
class Capture:
    codes: list
    liveness: dict
    guided: bool


@dataclass
class Enrolled:
    template: IrisTemplate
    capture: Capture
    message: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class DuressEnrolled:
    frames_used: int
    consistency_hd: float
    distance_from_normal_eye: float
    liveness: dict
    message: str


@dataclass
class Verified:
    event: VerificationEvent
    hamming_distance: float
    accept_hd: float
    capture: Capture
    distances: list


def _capture(images: list[bytes], hints: list[Hint], client_blink: bool | None, s: Settings, engine: IrisEngine) -> Capture:
    if len(images) < s.iris_min_frames:
        raise Invalid(f"send at least {s.iris_min_frames} frames captured over 1-3 seconds")
    frames = []
    for raw in images[:MAX_FRAMES]:
        try:
            frames.append(engine.decode_image(raw))
        except ValueError as exc:
            raise Unsupported(str(exc)) from exc
    hints = (hints + [None] * len(frames))[:len(frames)]
    codes = [engine.process_frame(f, min_focus=s.iris_min_focus, min_radius=s.iris_min_radius_px, hint=h)
             for f, h in zip(frames, hints)]
    live = engine.liveness(frames, [c.quality.iris_found for c in codes])
    if client_blink and not live["static_image"]:
        # The browser tracks the eyelids with face landmarks, which sees a blink more reliably than frame gaps.
        live["blink_detected"], live["score"], live["model"] = True, 0.0, "blink-liveness-v1 (eyelid landmarks)"
    return Capture(codes, live, any(h is not None for h in hints))


def personal_accept(consistency: float, s: Settings) -> float:
    """This person's accept limit: how well their enrolment frames agreed, plus a margin."""
    return round(min(s.iris_accept_cap, max(s.iris_accept_floor, consistency + s.iris_accept_margin)), 3)


def _clear(codes: list, s: Settings) -> list:
    good = [c for c in codes if c.quality.ok]
    if len(good) < s.iris_min_frames:
        issues = [i for c in codes for i in c.quality.issues]
        top = max(set(issues), key=issues.count) if issues else "the eye was not seen clearly"
        raise Invalid(f"only {len(good)} clear frame{'s' if len(good) != 1 else ''} of {len(codes)}: {top}")
    return good


def _templates(tpl, engine: IrisEngine, cipher: Cipher) -> list:
    return engine.unpack_many(cipher.decrypt_bytes(tpl.code_enc), cipher.decrypt_bytes(tpl.mask_enc))


def enrol(uow: IdentityUnitOfWork, customer_id: str, images: list[bytes], hints: list[Hint], blink: bool | None,
          eye: str | None, s: Settings, engine: IrisEngine, cipher: Cipher) -> Enrolled:
    """Up to five mutually consistent frames become the template. Frames that disagree are refused,
    so a poor capture can never become a template."""
    customer = customers.load(uow, customer_id)
    cap = _capture(images, hints, blink, s, engine)
    templates, consistency = engine.pick_templates(_clear(cap.codes, s))
    if consistency > s.iris_enrol_max_hd:
        raise Invalid(f"the frames did not capture the same iris pattern (agreement {consistency:.2f}, needs "
                      f"{s.iris_enrol_max_hd:.2f} or better). Hold still, in brighter light, and try again")
    warnings = [] if cap.liveness["blink_detected"] else ["no blink detected during capture"]
    if cap.liveness["static_image"]:
        raise Invalid("the frames look like a still photo; use a live camera")
    bits, mask = engine.pack_many(templates)
    if customer.iris_template:
        uow.delete(customer.iris_template)
        uow.flush()
    tpl = IrisTemplate(customer_id=customer.id, code_enc=cipher.encrypt_bytes(bits), mask_enc=cipher.encrypt_bytes(mask),
                       model_name=engine.model_name, sample_count=len(templates), consistency_hd=round(consistency, 4),
                       quality={**templates[0].quality.as_dict(), "accept_hd": personal_accept(consistency, s), "eye": eye,
                                "guided": cap.guided})
    uow.add(tpl)
    uow.commit()
    return Enrolled(tpl, cap, f"Iris registered for {customer.display_name}.", warnings)


def enrol_duress(uow: IdentityUnitOfWork, customer_id: str, images: list[bytes], hints: list[Hint], blink: bool | None,
                 s: Settings, engine: IrisEngine, cipher: Cipher) -> DuressEnrolled:
    """The customer's other eye, as a silent duress signal: it verifies normally on screen, but any
    transfer it approves is held and the fraud desk is alerted."""
    customer = customers.load(uow, customer_id)
    if not customer.iris_template:
        raise Conflict("enrol the normal eye first")
    cap = _capture(images, hints, blink, s, engine)
    templates, consistency = engine.pick_templates(_clear(cap.codes, s))
    if consistency > s.iris_enrol_max_hd:
        raise Invalid(f"the frames did not capture the same iris pattern (agreement {consistency:.2f}); try again")
    dist, _ = engine.best_match(_templates(customer.iris_template, engine, cipher), templates)
    dist = 1.0 if dist is None else dist
    if dist <= personal_accept(customer.iris_template.consistency_hd, s) + 0.03:
        raise Invalid("this looks like your normal eye; present your other eye for the duress signal")
    bits, mask = engine.pack_many(templates)
    if customer.iris_duress:
        uow.delete(customer.iris_duress)
        uow.flush()
    uow.add(IrisDuressTemplate(customer_id=customer.id, code_enc=cipher.encrypt_bytes(bits), mask_enc=cipher.encrypt_bytes(mask),
                               model_name=engine.model_name, consistency_hd=round(consistency, 4)))
    uow.commit()
    return DuressEnrolled(len(templates), round(consistency, 4), round(dist, 4), cap.liveness,
                          "Duress eye registered. Use it only if someone forces you to approve a payment.")


def verify(uow: IdentityUnitOfWork, customer_id: str, resolves_event_id: str | None, context: str | None, images: list[bytes],
           hints: list[Hint], blink: bool | None, s: Settings, engine: IrisEngine, cipher: Cipher) -> Verified:
    """The step-up after a voice STEP_UP. If the enrolled duress eye matches better, the answer looks
    like a normal ACCEPT, but the event is marked as duress and the fraud desk is alerted."""
    customer = customers.load(uow, customer_id)
    tpl = customer.iris_template
    if not tpl:
        raise Conflict("customer has no iris template; enrol first")
    if resolves_event_id:
        voice_ev = uow.events.get(resolves_event_id)
        if not voice_ev or voice_ev.customer_id != customer.id:
            raise NotFound("voice event to resolve not found for this customer")
        context = context or voice_ev.context
    cap = _capture(images, hints, blink, s, engine)
    codes, live = cap.codes, cap.liveness
    accept = (tpl.quality or {}).get("accept_hd", s.iris_accept_hd)
    best, hds = engine.best_match(_templates(tpl, engine, cipher), codes)
    duress = False
    if customer.iris_duress:
        d_accept = personal_accept(customer.iris_duress.consistency_hd, s)
        best_duress, dhds = engine.best_match(_templates(customer.iris_duress, engine, cipher), codes)
        if best_duress is not None and best_duress <= d_accept and (best is None or best_duress < best):
            duress, hds, best = True, dhds, best_duress
    hd = best
    reasons: list[str] = []
    clear = sum(1 for c in codes if c.quality.ok)
    if hd is None:
        hd = 1.0
        issues = [i for c in codes for i in c.quality.issues]
        reasons.append("no clear iris frame in the burst" + (f": {max(set(issues), key=issues.count)}" if issues else ""))
        decision = Decision.REJECT
    elif hd <= accept:
        decision = Decision.ACCEPT
        reasons.append(f"iris matches: distance {hd:.3f} is within this customer's limit of {accept:.2f} ({clear} clear frames)")
    else:
        decision = Decision.REJECT
        reasons.append(f"iris does not match: distance {hd:.3f} is above this customer's limit of {accept:.2f}")
    if live["static_image"]:
        decision = Decision.REJECT
        reasons.append("liveness: frames look like a static image")
    elif not live["blink_detected"]:
        reasons.append("liveness: no blink detected (demo liveness is advisory only)")
    duress = duress and decision == Decision.ACCEPT
    # The wording is identical for duress, so nothing on screen gives it away.
    ev = uow.events.add(VerificationEvent(
        customer_id=customer.id, context=context, modality="iris", resolves_event_id=resolves_event_id,
        match_score=round(1.0 - hd, 4), spoof_score=live["score"], spoof_model=live["model"], decision=decision.value,
        reasons=reasons, quality={"frames": [c.quality.as_dict() for c in codes], "liveness": live}, duress=duress))
    if duress:
        raise_alert(uow, "duress", f"{customer.display_name} presented the duress eye during iris verification"
                    f"{' for ' + context.replace('_', ' ') if context else ''}. Any transfer it approves will be held. "
                    "Contact the customer safely.", severity="critical", customer_id=customer.id, event_id=ev.id)
    uow.commit()
    return Verified(ev, hd, accept, cap, hds)
