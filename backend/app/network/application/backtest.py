"""Backtest: replay the transfer history at regular checkpoints, as if TheOne had been running,
and score the alerts against outcomes the bank already confirmed.

Questions it answers:
  * what share of confirmed mules would have been flagged, and how many hours before the bank
    confirmed them (lead time)?
  * of the alerts an analyst team could actually review per day, how many were real mules?
  * which typologies fire on legitimate accounts?
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import timedelta

from app.core.config import Settings
from app.core.errors import Conflict
from app.core.timeutil import now
from app.network.application.analysis import learned_weights
from app.network.application.config import engine_config
from app.network.application.ports import NetworkUnitOfWork
from app.network.domain.engine import score_all


def run(uow: NetworkUnitOfWork, s: Settings, days: int = 14, step_hours: int = 12, capacity_per_day: int = 20) -> dict:
    t0 = time.perf_counter()
    labels = {lab.account_id: (lab.label, lab.confirmed_at) for lab in uow.labels.all()}
    if not labels:
        raise Conflict("no labels: import confirmed outcomes with POST /network/labels (or run a simulation)")
    cfg = engine_config(s, learned_weights(uow, s))
    end = now()
    start = end - timedelta(days=days)
    steps = max(1, int(days * 24 / step_hours))
    per_step_capacity = max(1, round(capacity_per_day * step_hours / 24))
    first_flag: dict[str, object] = {}
    first_score: dict[str, float] = {}
    reviewed: set[str] = set()
    series = []
    final_signals: dict = {}
    # Checkpoint 0: what was already flaggable when the window opened. Those accounts are known at
    # the start, so they count toward recall but not toward lead time or alert volume.
    snap0 = uow.graph.load_snapshot(cfg, start)
    scores0, _, _ = score_all(snap0, cfg)
    at_start = {a for a, sc in scores0.items() if sc >= cfg.flag}
    for k in range(1, steps + 1):
        at = start + timedelta(hours=step_hours * k)
        snap = uow.graph.load_snapshot(cfg, at)
        scores, signals, _ = score_all(snap, cfg)
        new = [a for a, sc in scores.items() if sc >= cfg.flag and a not in first_flag and a not in at_start]
        for a in new:
            first_flag[a], first_score[a] = at, scores[a]
        queue = sorted(new, key=lambda a: -scores[a])[:per_step_capacity]
        reviewed |= set(queue)
        series.append({"at": at.isoformat(), "new_alerts": len(new), "reviewed": len(queue),
                       "mules_flagged_so_far": sum(1 for a in first_flag if labels.get(a, ("",))[0] == "mule")})
        final_signals = signals
    mules = {a for a, (lab, _) in labels.items() if lab == "mule"}
    legit = {a for a, (lab, _) in labels.items() if lab == "legit"}
    new_flags = set(first_flag)
    flagged = new_flags | at_start
    caught = flagged & mules
    leads = []
    for a in new_flags & mules:
        confirmed = labels[a][1]
        # Only cases the bank confirmed inside the window.
        if confirmed and confirmed >= start:
            leads.append((confirmed - first_flag[a]).total_seconds() / 3600)
    leads.sort()
    by_code: dict[str, dict[str, int]] = defaultdict(lambda: {"mule": 0, "legit": 0, "unlabelled": 0})
    for a in flagged:
        lab = labels.get(a, ("unlabelled", None))[0]
        for sig in final_signals.get(a, []):
            by_code[sig.code]["mule" if lab == "mule" else "legit" if lab == "legit" else "unlabelled"] += 1
    labelled_flagged = flagged & (mules | legit)
    return {
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": days, "step_hours": step_hours,
                   "checkpoints": steps, "capacity_per_day": capacity_per_day},
        "labels": {"mules": len(mules), "legit": len(legit)},
        "alerts": len(new_flags), "alerts_per_day": round(len(new_flags) / days, 1),
        "already_flagged_at_start": len(at_start), "lead_time_cases": len(leads),
        "recall": round(len(caught) / len(mules), 3) if mules else None,
        "precision_labelled": round(len(caught) / len(labelled_flagged), 3) if labelled_flagged else None,
        "flagged_unlabelled": len(flagged - mules - legit),
        "legit_flagged": len(flagged & legit),
        "precision_at_capacity": round(len(reviewed & mules) / len(reviewed), 3) if reviewed else None,
        "caught_before_confirmation": sum(1 for x in leads if x > 0),
        "median_lead_hours": round(leads[len(leads) // 2], 1) if leads else None,
        "missed_mules": len(mules - flagged),
        "typologies": dict(sorted(by_code.items(), key=lambda kv: -(kv[1]["mule"] + kv[1]["legit"]))),
        "series": series,
        "duration_s": round(time.perf_counter() - t0, 2),
    }
