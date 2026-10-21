"""How well detection did on simulated data, where the planted mules are known."""
from __future__ import annotations

from app.core.config import Settings
from app.core.errors import Conflict
from app.network.domain.engine import Analysis


def evaluate(a: Analysis, s: Settings) -> dict:
    accs = a.snapshot.accounts
    labelled = [v for v in accs.values() if v.label]
    if not labelled:
        raise Conflict("no synthetic labels: evaluation needs simulated data")
    mules = {v.id for v in accs.values() if v.label == "mule"}
    victims = {v.id for v in accs.values() if v.label == "victim"}
    flagged = {x for x, sc in a.scores.items() if sc >= s.network_flag_threshold}
    tp = len(flagged & mules)
    in_rings = set(a.ring_of)
    # A planted ring is "found" when one detected ring holds at least half of its home-bank mules.
    planted: dict[str, set[str]] = {}
    for x in mules:
        if accs[x].home:
            planted.setdefault(_planted_group(a, x, mules), set()).add(x)
    found = 0
    for group in planted.values():
        best = max((len(group & set(r.members)) for r in a.rings), default=0)
        if best >= max(1, len(group) // 2):
            found += 1
    return {
        "mules": len(mules), "flagged": len(flagged), "true_positives": tp,
        "precision": round(tp / len(flagged), 3) if flagged else None,
        "recall": round(tp / len(mules), 3) if mules else None,
        "home_mule_recall": round(len(flagged & {x for x in mules if accs[x].home}) / max(1, sum(1 for x in mules if accs[x].home)), 3),
        "victims": len(victims), "victims_flagged": len(flagged & victims),
        "false_positives": sorted([{"id": x, "name": accs[x].name, "risk": a.scores[x]} for x in flagged - mules],
                                  key=lambda d: -d["risk"])[:20],
        "planted_rings": len(planted), "planted_rings_found": found,
        "detected_rings": len(a.rings), "ring_accounts": len(in_rings),
        "ring_precision": round(len(in_rings & mules) / len(in_rings), 3) if in_rings else None,
    }


def _planted_group(a: Analysis, acc: str, mules: set[str]) -> str:
    """Connected component of mule accounts via transfers or identifiers (ground-truth ring)."""
    snap, seen, stack = a.snapshot, {acc}, [acc]
    while stack:
        x = stack.pop()
        nb = {e.dst for e in snap.outs.get(x, [])} | {e.src for e in snap.ins.get(x, [])}
        for ident in snap.acct_idents.get(x, ()):
            nb |= snap.ident_members.get(ident, set())
        for y in nb & mules:
            if y not in seen:
                seen.add(y)
                stack.append(y)
    return min(seen)
