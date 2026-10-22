"""The real-time transfer decision, and how a decision is resolved, reviewed and executed."""
from __future__ import annotations

import time
from datetime import timedelta

from app.core.config import Settings, get_settings
from app.core.errors import Conflict, Invalid, NotFound
from app.core.timeutil import now
from app.network.application import bank_actions
from app.network.application.alerts import raise_alert
from app.network.application.analysis import cache
from app.network.application.config import engine_config, sender_rules
from app.network.application.ingest import get_or_create_account, ingest
from app.network.application.ports import BankConnector, NetworkUnitOfWork, NibssConnector
from app.network.domain import decision_policy, sender
from app.network.domain.engine import NAIRA, Config, Signal, naira, noisy_or, signal_dicts
from app.network.domain.entities import Account, AnalystAction, Identifier, TransferDecision
from app.network.domain.identifiers import id_hash, mask


def _live_pass_through(uow: NetworkUnitOfWork, src: Account, amount: int, cfg: Config) -> Signal | None:
    """A check that does not wait for re-analysis: is this payment draining credits that arrived from
    several senders within the fast window?"""
    rows = uow.transfers.received_since(src.id, now() - cfg.fast_window)
    total = sum(a for _, a in rows)
    senders = {s for s, _ in rows}
    if total >= 100_000 * NAIRA and len(senders) >= 3 and amount >= 0.5 * total:
        return Signal("LIVE_PASS_THROUGH", 0.45,
                      f"this transfer moves {amount / total:.0%} of {naira(total)} that arrived from {len(senders)} senders in the last {int(cfg.fast_window.total_seconds() // 60)} minutes",
                      {"recent_inbound": total, "senders": len(senders)})
    return None


def _owner_methods(uow: NetworkUnitOfWork, acc: Account) -> list[str]:
    if not acc.customer_id:
        return []
    c = uow.customers.get(acc.customer_id)
    methods = []
    if c and c.template:
        methods.append("voice")
    if c and c.iris_template:
        methods.append("iris")
    methods.append("device")
    return methods


def _device(uow: NetworkUnitOfWork, src: Account, device: str, s: Settings, at) -> tuple[str, str]:
    """The state of the paying device for this account, registering a device seen for the first time."""
    h = id_hash("device", device, s.network_id_pepper)
    ident = uow.identifiers.find("device", h)
    if ident is None:
        ident = uow.identifiers.add(Identifier(kind="device", value_hash=h, masked=mask("device", device)))
        uow.flush()
    links = uow.identifiers.links(src.id, "device")
    here = next((seen for i, seen in links if i == ident.id), None)
    state = sender.device_state(here, [seen for i, seen in links if i != ident.id], at)
    if here is None:
        uow.identifiers.link(src.id, ident.id, first_seen=at)
    return state, ident.masked


def _history(uow: NetworkUnitOfWork, src: Account, s: Settings, at, device: str | None) -> sender.SenderHistory:
    since = at - timedelta(days=sender.PAYEE_HISTORY_DAYS)
    sent = uow.transfers.sent_between(src.id, since, at)
    payments = [(ts, d, a) for ts, d, a, _ in sent]
    refs = {ref for *_, ref in sent}
    payments += [(ts, None, a) for ts, a, ref in uow.statements.debits_between(src.id, since, at) if ref not in refs]
    return sender.SenderHistory(
        payments=payments,
        approved_recent=uow.decisions.approved_since(src.id, at - timedelta(minutes=sender.BURST_MINUTES)),
        usual_locations=[(c["location"]["lat"], c["location"]["lon"])
                         for c in uow.decisions.recent_contexts(src.id, sender.LOCATION_HISTORY) if c and c.get("location")],
        device=_device(uow, src, device, s, at) if device else None,
    )


def decide(uow: NetworkUnitOfWork, body: dict, s: Settings) -> dict:
    t0 = time.perf_counter()
    cfg = engine_config(s)
    if body.get("reference"):
        prior = uow.decisions.by_reference(body["reference"])
        if prior:
            return decision_out(uow, prior, idempotent=True)
    amount = body["amount_kobo"]
    if amount <= 0:
        raise Invalid("amount_kobo must be positive")
    src = get_or_create_account(uow, body["source"]["bank_code"], body["source"]["account_no"])
    dst = get_or_create_account(uow, body["beneficiary"]["bank_code"], body["beneficiary"]["account_no"], body.get("beneficiary_name"))
    if src.id == dst.id:
        raise Invalid("source and beneficiary are the same account")
    analysis = cache.get(uow, fresh=False)

    src_sigs = list(analysis.signals.get(src.id, []))
    live = _live_pass_through(uow, src, amount, cfg)
    if live:
        src_sigs.append(live)
    src_score = noisy_or(src_sigs) if src_sigs else 0.0
    if src.effective_status() == "cleared":
        src_score = round(src_score * 0.3, 4)
    dst_sigs = list(analysis.signals.get(dst.id, []))
    dst_score = analysis.risk(dst.id)
    at = now()
    sa = sender.assess(src, dst.id, amount, _history(uow, src, s, at, body.get("device")), sender_rules(s), at,
                       location=body.get("location"))
    limit = uow.safe_limits.get(src.id)
    verdict = decision_policy.decide(
        src_status=src.effective_status(), src_score=src_score, dst_status=dst.effective_status(), dst_score=dst_score,
        owner_methods=_owner_methods(uow, src), sender=sa, flag=cfg.flag, hold=cfg.hold,
        sender_stepup=s.network_sender_stepup, safe_limit=limit.current(at) if limit else None)
    if verdict.bank_otp_fallback:
        sa.context["step_up_fallback"] = "bank_otp"

    d = uow.decisions.add(TransferDecision(
        reference=body.get("reference"), src_account_id=src.id, dst_account_id=dst.id, amount_kobo=amount,
        channel=body.get("channel") or "nip", decision=verdict.decision, status=verdict.status, src_score=src_score,
        dst_score=dst_score, sender_score=sa.score, context=sa.context, reasons=verdict.reasons,
        latency_ms=round((time.perf_counter() - t0) * 1000, 2)))
    if verdict.over_safe_limit:
        raise_alert(uow, "safe_limit", f"Transfer of {naira(amount)} above the customer's safe limit was held. "
                    "If the customer did not expect this, treat it as possible coercion.",
                    customer_id=src.customer_id, account_id=src.id, decision_id=d.id, context=sa.context)
    if any(x.code == "REVIEW_CAP" for x in sa.signals):
        raise_alert(uow, "review_cap", f"Transfer of {naira(amount)} reached the single-transfer review cap.",
                    severity="medium", customer_id=src.customer_id, account_id=src.id, decision_id=d.id)
    uow.commit()
    out = decision_out(uow, d)
    out["source_signals"] = signal_dicts(src_sigs)
    out["beneficiary_signals"] = signal_dicts(dst_sigs)
    out["sender_signals"] = signal_dicts(sa.signals)
    out["analysis_age_s"] = round((now() - analysis.computed_at).total_seconds(), 1)
    # The ring the receiver belongs to, where a stopped payment now shows on the money map.
    rid = analysis.ring_of.get(dst.id)
    out["beneficiary_ring"] = ({"id": rid, "number": next((r.number for r in analysis.rings if r.id == rid), None)}
                               if rid else None)
    return out


def decision_out(uow: NetworkUnitOfWork, d: TransferDecision, idempotent: bool = False, client: bool = False) -> dict:
    """client=True is what the customer's app sees: a duress hold looks like a normal release, so a
    coerced customer is never put at risk by a visible refusal."""
    src, dst = uow.accounts.get(d.src_account_id), uow.accounts.get(d.dst_account_id)
    status, note = d.status, d.resolution_note
    if client and status == "duress_hold":
        status, note = "released", "owner verified by iris"
    step_up = []
    if d.decision == "STEP_UP_OWNER":
        step_up = _owner_methods(uow, src) or (["bank_otp"] if (d.context or {}).get("step_up_fallback") else [])
    return {
        "id": d.id, "reference": d.reference, "decision": d.decision, "status": status,
        "source": {"id": src.id, "bank_code": src.bank_code, "account_no": src.account_no, "name": src.holder_name},
        "beneficiary": {"id": dst.id, "bank_code": dst.bank_code, "account_no": dst.account_no, "name": dst.holder_name},
        "amount_kobo": d.amount_kobo, "source_risk": d.src_score, "beneficiary_risk": d.dst_score,
        "sender_risk": d.sender_score or 0.0, "context": None if client else d.context, "reasons": d.reasons,
        "step_up_methods": step_up, "customer_id": src.customer_id, "latency_ms": d.latency_ms,
        "created_at": d.created_at.isoformat(), "resolution_note": note, "idempotent_replay": idempotent,
        "mode": get_settings().network_mode, "source_signals": [], "beneficiary_signals": [], "sender_signals": [],
        "analysis_age_s": None,
    }


def _decision(uow: NetworkUnitOfWork, decision_id: str) -> TransferDecision:
    d = uow.decisions.get(decision_id)
    if not d:
        raise NotFound("decision not found")
    return d


def resolve(uow: NetworkUnitOfWork, decision_id: str, event_id: str | None, customer_confirmed: bool | None,
            bank: BankConnector, s: Settings, bank_factor_passed: bool | None = None) -> dict:
    d = _decision(uow, decision_id)
    if d.status not in {"pending", "pending_review"}:
        raise Conflict(f"decision is already {d.status}")
    src = uow.accounts.get(d.src_account_id)
    duress_actions: list[str] = []
    if d.decision == "STEP_UP_OWNER" and bank_factor_passed:
        if not (d.context or {}).get("step_up_fallback"):
            raise Invalid("this customer has enrolled biometrics; the bank's second factor cannot replace them here")
        d.status, d.resolution_note = "released", "bank second factor confirmed by the bank's channel"
    elif d.decision == "WARN_PAYEE":
        if not customer_confirmed:
            raise Invalid("the sender must confirm they still want to pay after seeing the warning")
        d.status, d.resolution_note = "released", "sender confirmed after payee warning"
    elif d.decision in {"STEP_UP_OWNER", "HOLD"}:
        if not event_id:
            raise Invalid("verification_event_id is required")
        ev = uow.events.get(event_id)
        if not ev or ev.customer_id != src.customer_id or not src.customer_id:
            raise Invalid("verification event does not belong to the source account's owner")
        if ev.decision != "ACCEPT":
            raise Invalid(f"verification event decision is {ev.decision}, not ACCEPT")
        if ev.created_at < d.created_at:
            raise Invalid("verification event happened before this decision")
        if ev.modality == "device" and s.network_require_attested_device and not (ev.quality or {}).get("attested"):
            raise Invalid("device step-up must be signed by the phone's hardware key to resolve a transfer")
        if uow.decisions.resolved_by(ev.id, other_than=d.id):
            raise Conflict("this verification event already resolved another transfer")
        d.resolved_by_event_id = ev.id
        if ev.duress:
            # Silent duress: hold the money, put the beneficiary on the watch-list and alert the fraud desk.
            d.status = "duress_hold"
            d.resolution_note = f"DURESS signal on {ev.modality} verification; transfer held silently"
            dst = uow.accounts.get(d.dst_account_id)
            if dst.status != "confirmed_mule":
                dst.watch(now())
                duress_actions = bank_actions.queue_for(uow, "watchlist_24h", [dst.id], bank, s,
                                                        note="TheOne: duress signal on a payment to this account")
            raise_alert(uow, "duress", f"Customer gave the duress signal while approving {naira(d.amount_kobo)} to "
                        f"{dst.holder_name or dst.account_no} ({dst.bank_code}/{dst.account_no}). The app showed success; "
                        "the transfer is held and the beneficiary is on the 24-hour watchlist. Contact the customer safely.",
                        severity="critical", customer_id=src.customer_id, account_id=src.id, decision_id=d.id,
                        event_id=ev.id, context=d.context)
            cache.bump()
        elif d.decision == "STEP_UP_OWNER":
            d.status, d.resolution_note = "released", f"owner verified by {ev.modality}"
        else:
            # A complicit owner passes biometrics too, so a HOLD never releases on its own.
            d.status, d.resolution_note = "pending_review", f"owner verified by {ev.modality}; analyst review still required"
    else:
        raise Conflict("allowed decisions need no resolution")
    d.resolved_at = now()
    uow.actions.add(AnalystAction(actor="customer", action="resolve", decision_id=d.id, account_ids=[src.id], note=d.resolution_note))
    uow.commit()
    if duress_actions:
        bank_actions.run(uow, duress_actions, bank, s)
    return decision_out(uow, d, client=True)


def review(uow: NetworkUnitOfWork, decision_id: str, outcome: str, actor: str, note: str | None) -> dict:
    d = _decision(uow, decision_id)
    if outcome not in {"release", "block"}:
        raise Invalid("outcome must be release or block")
    if d.status not in {"pending", "pending_review", "duress_hold"}:
        raise Conflict(f"decision is already {d.status}")
    d.status = "released" if outcome == "release" else "blocked"
    d.resolution_note = f"analyst {outcome}: {note}" if note else f"analyst {outcome}"
    d.resolved_at = now()
    uow.actions.add(AnalystAction(actor=actor, action=f"review_{outcome}", decision_id=d.id, account_ids=[d.src_account_id], note=note))
    uow.commit()
    return decision_out(uow, d)


def execute(uow: NetworkUnitOfWork, decision_id: str, s: Settings, nibss: NibssConnector) -> dict:
    """Record that an allowed or released transfer was sent, so it joins the graph and the sender's
    history. A real send returns "_refs" (the new transfer references) for re-analysis."""
    d = _decision(uow, decision_id)
    ref = d.reference or f"DEC-{d.id}"
    if d.status == "duress_hold":
        # The customer's app must not learn of the hold: answer exactly like a normal send and record nothing.
        return {"decision_id": d.id, "reference": ref, "accounts": 0, "transfers_added": 1, "transfers_skipped": 0}
    if d.status not in {"allowed", "released"}:
        raise Conflict("only allowed or released transfers can be executed")
    src, dst = uow.accounts.get(d.src_account_id), uow.accounts.get(d.dst_account_id)
    out = ingest(uow, [], [{"reference": ref, "ts": now(), "src": {"bank_code": src.bank_code, "account_no": src.account_no},
                            "dst": {"bank_code": dst.bank_code, "account_no": dst.account_no},
                            "amount_kobo": d.amount_kobo, "channel": d.channel}], s, nibss)
    return {"decision_id": d.id, "reference": ref, **out}


def list_decisions(uow: NetworkUnitOfWork, limit: int = 50) -> list[dict]:
    return [decision_out(uow, d) for d in uow.decisions.newest(max(1, min(limit, 500)))]
