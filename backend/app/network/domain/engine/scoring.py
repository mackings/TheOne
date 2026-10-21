"""Steps 2-3: combine signals into a score (noisy-OR, learned weights), then propagate downstream."""
from __future__ import annotations

import bisect

from app.network.domain.engine.types import Config, DAY, DAY_CHANNELS, Signal, Snapshot
from app.network.domain.engine.typologies import (_is_cash_point, sig_cash_out, sig_device_farm, sig_dormant, sig_fan_in,
                                                  sig_new_account, sig_pass_through, sig_reports, sig_shared, sig_split_round)

def noisy_or(signals: list[Signal]) -> float:
    p = 1.0
    for s in signals:
        p *= 1.0 - max(0.0, min(0.99, s.weight))
    return round(1.0 - p, 4)


# Learning may re-weight rules but never lets one behavioural signal flag an account on its own:
# raised weights stop below the flag line, and multipliers stay within [0.25, 2.0]. Reports and
# analyst outcomes are evidence in themselves and are exempt.
LEARNING_EXEMPT = {"VICTIM_COMPLAINT", "CONFIRMED_MULE", "BVN_WATCHLIST", "STATUS_CONFIRMED", "STATUS_CLEARED"}
MULT_MIN, MULT_MAX, SOLO_CAP = 0.25, 2.0, 0.55


def _weighted(sig: Signal, cfg: Config) -> Signal:
    """cfg.weights holds a learned multiplier per signal code (learned precision / hand-set prior)."""
    mult = cfg.weights.get(sig.code)
    if mult is None or sig.code in LEARNING_EXEMPT:
        return sig
    mult = min(MULT_MAX, max(MULT_MIN, mult))
    w = sig.weight * mult
    if mult > 1:
        w = min(w, max(sig.weight, SOLO_CAP))
    sig.weight = round(min(0.97, max(0.01, w)), 4)
    return sig


def base_signals(acc_id: str, snap: Snapshot, cfg: Config) -> list[Signal]:
    """First-pass signals: everything except propagation and analyst status."""
    acc = snap.accounts.get(acc_id)
    if acc is None or _is_cash_point(acc):
        return []
    ins, outs = snap.ins.get(acc_id, []), snap.outs.get(acc_id, [])
    sigs: list[Signal] = []
    if ins or outs:
        for x in (
            sig_fan_in(acc, ins),
            sig_pass_through(ins, outs, cfg.fast_window),
            sig_split_round(ins, outs),
            sig_cash_out(ins, outs),
            sig_dormant(acc_id, ins, outs, snap.prior_last),
        ):
            if x:
                sigs.append(x)
        sigs.extend(sig_new_account(acc, ins, outs, snap.at))
    farm = sig_device_farm(acc_id, snap)
    if farm:
        sigs.append(farm)
    sh = sig_shared(acc_id, snap)
    # Shared identifiers alone (e.g. a family phone) never make an account suspicious.
    if sh and (sigs or sh.weight >= 0.40):
        sigs.append(sh)
    sigs.extend(sig_reports(snap.reports.get(acc_id, [])))
    return [_weighted(x, cfg) for x in sigs]


def propagate(snap: Snapshot, cfg: Config, base: dict[str, list[Signal]], scores: dict[str, float],
              signals: dict[str, list[Signal]], subset: set[str] | None = None) -> None:
    """Downstream propagation, up to three hops: money received quickly from a flagged account.
    Only downstream links count, so a victim who paid a mule is never penalised."""
    accounts = list(subset) if subset is not None else list(snap.accounts)
    for _round in range(3):
        current = dict(scores)
        changed = False
        for acc_id in accounts:
            acc = snap.accounts.get(acc_id)
            if acc is None or acc.is_merchant:
                continue
            upstream: set[str] = set()
            for e in snap.ins.get(acc_id, []):
                if e.src == acc_id or current.get(e.src, 0) < cfg.flag:
                    continue
                src_in = [x.ts for x in snap.ins.get(e.src, [])]
                k = bisect.bisect_right(src_in, e.ts)
                if k and e.ts - src_in[k - 1] <= (DAY if e.channel in DAY_CHANNELS else cfg.fast_window):
                    upstream.add(e.src)
            sigs = list(base.get(acc_id, []))
            if upstream:
                sigs.append(_weighted(Signal("FAST_FROM_FLAGGED", 0.40 if len(upstream) >= 2 else 0.30,
                                             f"received fast-moving funds from {len(upstream)} flagged account{'s' if len(upstream) > 1 else ''}",
                                             {"upstream": sorted(upstream)[:10], "hop_round": _round + 1}), cfg))
            if not sigs:
                if acc_id in scores:
                    scores.pop(acc_id)
                    signals.pop(acc_id, None)
                    changed = True
                continue
            new_score = noisy_or(sigs)
            if new_score != scores.get(acc_id):
                changed = True
            signals[acc_id], scores[acc_id] = sigs, new_score
        if not changed:
            break


def apply_status(snap: Snapshot, scores: dict[str, float], signals: dict[str, list[Signal]],
                 subset: set[str] | None = None) -> None:
    for acc_id in (subset if subset is not None else snap.accounts):
        acc = snap.accounts.get(acc_id)
        if acc is None:
            continue
        if acc.status == "confirmed_mule":
            signals.setdefault(acc_id, []).append(Signal("STATUS_CONFIRMED", 0.99, "confirmed mule by analyst", {}))
            scores[acc_id] = max(scores.get(acc_id, 0), 0.99)
        elif acc.status == "cleared" and acc_id in scores:
            scores[acc_id] = round(scores[acc_id] * 0.3, 4)
            signals[acc_id].append(Signal("STATUS_CLEARED", 0.0, "cleared by analyst review; score suppressed", {}))


def score_accounts(snap: Snapshot, cfg: Config) -> tuple[dict[str, float], dict[str, list[Signal]]]:
    scores, signals, _ = score_all(snap, cfg)
    return scores, signals


def score_all(snap: Snapshot, cfg: Config) -> tuple[dict[str, float], dict[str, list[Signal]], dict[str, list[Signal]]]:
    base = {}
    for acc_id in snap.accounts:
        b = base_signals(acc_id, snap, cfg)
        if b:
            base[acc_id] = b
    scores = {a: noisy_or(v) for a, v in base.items()}
    signals = {a: list(v) for a, v in base.items()}
    propagate(snap, cfg, base, scores, signals)
    apply_status(snap, scores, signals)
    return scores, signals, base
