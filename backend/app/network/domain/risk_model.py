"""A trained risk model that runs beside the rules, in shadow.

It learns from outcomes the bank has confirmed (mule or legitimate) which combinations of
behaviour matter most. It never decides anything: rules and analysts still do. Its job is to
show where it agrees with the rules, and where it disagrees, so the bank can judge whether a
trained model is worth switching on.

Model: L2-regularised logistic regression on standardised features. It is small, fast,
needs no extra libraries, and every score can be explained as a sum of feature contributions.
Analyst outcomes and confirmed-mule status are never features, so the model cannot copy the
answer it is trained on.
"""
from __future__ import annotations

import math

import numpy as np

from app.core.timeutil import now
from app.network.domain.engine import CASH_CHANNELS, Analysis
from app.network.domain.explain import PLAIN as RULES

SIG = ["FAN_IN", "PASS_THROUGH", "SPLIT_ROUND", "CASH_OUT", "NEW_ACCOUNT_VELOCITY", "LOW_KYC_HIGH_VALUE",
       "DORMANT_REACTIVATED", "DEVICE_FARM", "SHARED_IDENTIFIER", "FAST_FROM_FLAGGED", "VICTIM_COMPLAINT"]
NUM = ["money_in", "money_out", "credits", "debits", "payers", "payees", "out_vs_in", "account_age", "tier_1",
       "shared_details", "cash_share"]
FEATURES = [f"rule:{c}" for c in SIG] + NUM
PLAIN = {
    "money_in": "How much money came in", "money_out": "How much money went out", "credits": "Number of credits",
    "debits": "Number of payments out", "payers": "Number of different payers", "payees": "Number of different payees",
    "out_vs_in": "Share of incoming money sent out again", "account_age": "How old the account is",
    "tier_1": "Basic-level (tier 1) account", "shared_details": "How many other accounts share its details",
    "cash_share": "Share of money withdrawn as cash",
}
MIN_EACH = 20


def plain_feature(f: str) -> str:
    if f.startswith("rule:"):
        return RULES.get(f[5:], (f[5:], ""))[0]
    return PLAIN.get(f, f)


def features(a: Analysis, acc_id: str) -> np.ndarray:
    snap = a.snapshot
    v = snap.accounts[acc_id]
    ins, outs = snap.ins.get(acc_id, []), snap.outs.get(acc_id, [])
    fired = {s.code for s in a.signals.get(acc_id, [])}
    tin, tout = sum(e.amount for e in ins), sum(e.amount for e in outs)
    shared = set()
    for ident in snap.acct_idents.get(acc_id, ()):
        shared |= snap.ident_members.get(ident, set())
    shared.discard(acc_id)
    age = (snap.at - v.opened_at).days if v.opened_at else 365
    row = [1.0 if c in fired else 0.0 for c in SIG] + [
        math.log1p(tin / 100), math.log1p(tout / 100), math.log1p(len(ins)), math.log1p(len(outs)),
        math.log1p(len({e.src for e in ins})), math.log1p(len({e.dst for e in outs})),
        min(2.0, tout / tin) if tin else 0.0, min(max(age, 0), 365) / 365, 1.0 if v.kyc_tier == 1 else 0.0,
        math.log1p(len(shared)), (sum(e.amount for e in outs if e.channel in CASH_CHANNELS) / tout) if tout else 0.0,
    ]
    return np.array(row, dtype=float)


def _fit(X: np.ndarray, y: np.ndarray, l2: float = 0.05, iters: int = 600) -> tuple[np.ndarray, float]:
    """Class-balanced logistic regression by gradient descent (X already standardised)."""
    n, k = X.shape
    w, b = np.zeros(k), 0.0
    pos = max(1, y.sum())
    cw = np.where(y == 1, n / (2 * pos), n / (2 * max(1, n - pos)))
    lr = 0.5
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(X @ w + b)))
        g = (p - y) * cw
        w -= lr * (X.T @ g / n + l2 * w)
        b -= lr * g.mean()
    return w, b


def _auc(scores: np.ndarray, y: np.ndarray) -> float | None:
    pos, neg = scores[y == 1], scores[y == 0]
    if not len(pos) or not len(neg):
        return None
    order = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    ranks = np.empty(len(order))
    ranks[order] = np.arange(1, len(order) + 1)
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def _pr(flags: np.ndarray, y: np.ndarray) -> dict:
    tp = int((flags & (y == 1)).sum())
    return {"precision": round(tp / flags.sum(), 3) if flags.sum() else None, "recall": round(tp / max(1, (y == 1).sum()), 3),
            "flagged": int(flags.sum()), "legit_flagged": int((flags & (y == 0)).sum())}


def labelled_rows(labels: dict[str, tuple[str, str]], a: Analysis) -> tuple[list[str], np.ndarray, np.ndarray, dict]:
    """labels maps account id to (label, source)."""
    ids = [x for x, (lab, _) in labels.items() if lab in ("mule", "legit") and x in a.snapshot.accounts
           and not a.snapshot.accounts[x].is_merchant]
    sources: dict[str, int] = {}
    for x in ids:
        src = labels[x][1].split(":")[0]
        sources[src] = sources.get(src, 0) + 1
    X = np.array([features(a, x) for x in ids]) if ids else np.zeros((0, len(FEATURES)))
    y = np.array([1 if labels[x][0] == "mule" else 0 for x in ids])
    return ids, X, y, sources


def train(labels: dict[str, tuple[str, str]], a: Analysis, flag: float, seed: int = 7) -> dict:
    ids, X, y, sources = labelled_rows(labels, a)
    if (y == 1).sum() < MIN_EACH or (y == 0).sum() < MIN_EACH:
        raise ValueError(f"training needs at least {MIN_EACH} confirmed mules and {MIN_EACH} confirmed legitimate accounts "
                         f"(have {(y == 1).sum()} and {(y == 0).sum()})")
    rules = np.array([a.scores.get(x, 0.0) for x in ids])

    # 5-fold cross-validation: every account is scored by a model that never saw its outcome.
    rng = np.random.default_rng(seed)
    folds = np.zeros(len(y), dtype=int)
    for cls in (0, 1):
        idx = np.flatnonzero(y == cls)
        rng.shuffle(idx)
        folds[idx] = np.arange(len(idx)) % 5
    held = np.zeros(len(y))
    for f in range(5):
        tr, te = folds != f, folds == f
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
        w, b = _fit((X[tr] - mu) / sd, y[tr])
        held[te] = 1 / (1 + np.exp(-(((X[te] - mu) / sd) @ w + b)))

    mu, sd = X.mean(0), X.std(0) + 1e-9
    w, b = _fit((X - mu) / sd, y)
    order = np.argsort(-np.abs(w))
    payload = {
        "trained_at": now().isoformat(), "features": FEATURES, "mean": mu.tolist(), "std": sd.tolist(), "weights": w.tolist(),
        "bias": float(b), "labels": {"mule": int((y == 1).sum()), "legit": int((y == 0).sum()), "sources": sources},
        "evaluation": {
            "method": "5-fold cross-validation on confirmed outcomes",
            "rules": {"auc": _auc(rules, y), **_pr(rules >= flag, y)},
            "model": {"auc": _auc(held, y), **_pr(held >= 0.5, y)},
        },
        "top_features": [{"feature": plain_feature(FEATURES[i]), "weight": round(float(w[i]), 3),
                          "direction": "raises risk" if w[i] > 0 else "lowers risk"} for i in order[:8]],
    }
    return payload


def score(model: dict, a: Analysis, acc_id: str) -> dict:
    x = features(a, acc_id)
    z = (x - np.array(model["mean"])) / np.array(model["std"])
    contrib = z * np.array(model["weights"])
    p = float(1 / (1 + np.exp(-(contrib.sum() + model["bias"]))))
    top = [i for i in np.argsort(-contrib) if contrib[i] > 0.05][:3]
    return {"score": round(p, 3), "because": [plain_feature(model["features"][i]) for i in top]}


def disagreements(model: dict, a: Analysis, flag: float, limit: int = 8) -> dict:
    """Where the model and the rules see an account very differently: worth an analyst's look."""
    rows = []
    for acc_id, v in a.snapshot.accounts.items():
        if v.is_merchant or not (a.snapshot.ins.get(acc_id) or a.snapshot.outs.get(acc_id)):
            continue
        s = score(model, a, acc_id)
        rows.append((acc_id, s, a.scores.get(acc_id, 0.0)))
    brief = lambda acc_id, s, r: {"account_id": acc_id, "name": a.snapshot.accounts[acc_id].name,  # noqa: E731
                                  "account_no": a.snapshot.accounts[acc_id].account_no, "model": s["score"],
                                  "rules": round(r, 2), "because": s["because"]}
    model_only = sorted((x for x in rows if x[1]["score"] >= 0.7 and x[2] < 0.35), key=lambda x: -x[1]["score"])
    rules_only = sorted((x for x in rows if x[2] >= flag and x[1]["score"] < 0.3), key=lambda x: -x[2])
    agree = sum(1 for x in rows if (x[1]["score"] >= 0.5) == (x[2] >= flag))
    return {"accounts": len(rows), "agreement": round(agree / len(rows), 3) if rows else None,
            "model_only": [brief(*x) for x in model_only[:limit]], "rules_only": [brief(*x) for x in rules_only[:limit]]}
