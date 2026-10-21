"""Learning from outcomes: how often each typology fires on confirmed mules versus accounts
confirmed legitimate. The learned weight is a Bayesian estimate shrunk toward the hand-set prior,
so a handful of cases cannot swing it, and it is applied as a multiplier on the rule's weights."""
from __future__ import annotations

from collections import defaultdict

from app.core.config import Settings
from app.core.timeutil import now
from app.network.application.analysis import cache
from app.network.application.config import engine_config
from app.network.application.ingest import get_or_create_account, set_label
from app.network.application.ports import NetworkUnitOfWork
from app.network.domain.engine import LEARNING_EXEMPT, MULT_MAX, MULT_MIN, base_signals
from app.network.domain.entities import TypologyWeight


def labelled(uow: NetworkUnitOfWork) -> dict[str, str]:
    out = {lab.account_id: lab.label for lab in uow.labels.all()}
    for acc in uow.accounts.with_status({"confirmed_mule", "cleared"}):
        out.setdefault(acc.id, "mule" if acc.status == "confirmed_mule" else "legit")
    return out


def compute(uow: NetworkUnitOfWork, s: Settings) -> list[dict]:
    labels = labelled(uow)
    # Learn from the unweighted rules, never from weights already learned.
    cfg = engine_config(s)
    snap = uow.graph.load_snapshot(cfg, now())
    mule, legit, prior_sum, prior_n = defaultdict(int), defaultdict(int), defaultdict(float), defaultdict(int)
    for acc_id, lab in labels.items():
        for sig in base_signals(acc_id, snap, cfg):
            (mule if lab == "mule" else legit)[sig.code] += 1
            prior_sum[sig.code] += sig.weight
            prior_n[sig.code] += 1
    k = s.network_learning_prior_strength
    rows = []
    for code in sorted(set(mule) | set(legit)):
        c, d = mule[code], legit[code]
        prior = prior_sum[code] / prior_n[code]
        learned = (c + prior * k) / (c + d + k)
        learned = round(min(0.97, max(0.02, learned)), 4)
        exempt = code in LEARNING_EXEMPT
        rows.append({"code": code, "mule": c, "legit": d, "prior": round(prior, 4), "learned": learned,
                     "multiplier": None if exempt else round(min(MULT_MAX, max(MULT_MIN, learned / prior)), 3),
                     "capped": (not exempt) and not (MULT_MIN <= learned / prior <= MULT_MAX),
                     "exempt": exempt, "active": (not exempt) and c + d >= s.network_learning_min_samples})
    return rows


def refresh(uow: NetworkUnitOfWork, s: Settings) -> dict:
    rows = compute(uow, s)
    stamp = now()
    uow.weights.replace_all([TypologyWeight(code=r["code"], base_weight=r["prior"], learned_weight=r["learned"],
                                            mule_count=r["mule"], legit_count=r["legit"], updated_at=stamp)
                             for r in rows if r["active"]])
    uow.commit()
    cache.run(uow, s)
    return {"updated": [r for r in rows if r["active"]], "skipped_low_samples": [r["code"] for r in rows if not r["active"]]}


def view(uow: NetworkUnitOfWork, s: Settings) -> dict:
    """Weights in use now, and what the current outcomes would change them to."""
    applied = {w.code: {"learned": w.learned_weight, "prior": w.base_weight,
                        "multiplier": round(min(MULT_MAX, max(MULT_MIN, w.learned_weight / w.base_weight)), 3),
                        "capped": not (MULT_MIN <= w.learned_weight / w.base_weight <= MULT_MAX)}
               for w in uow.weights.all() if w.base_weight > 0}
    return {"enabled": s.network_learning_enabled, "min_samples": s.network_learning_min_samples,
            "applied": applied, "candidates": compute(uow, s)}


def add_labels(uow: NetworkUnitOfWork, labels: list[dict]) -> int:
    """Confirmed investigation outcomes: an account is a mule or legitimate, and when that was known."""
    for lab in labels:
        acc = get_or_create_account(uow, lab["bank_code"], lab["account_no"])
        set_label(uow, acc.id, lab["label"], lab.get("confirmed_at"), lab.get("source") or "import")
    uow.commit()
    return len(labels)


def labels_summary(uow: NetworkUnitOfWork) -> dict:
    rows = [(lab.label, lab.source) for lab in uow.labels.all()]
    out: dict = {}
    for lab, src in rows:
        out.setdefault(lab, {}).setdefault(src, 0)
        out[lab][src] += 1
    return {"total": len(rows), "by_label": out}
