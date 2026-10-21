"""Group connected suspicious accounts into rings, summarise each ring, and match new rings to known ones."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime

from app.network.domain.engine.types import CASH_CHANNELS, Config, Signal, Snapshot
from app.network.domain.entities import Ring

SAME_RING = 0.5

class _UF:
    def __init__(self):
        self.p: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def find_rings(snap: Snapshot, scores: dict[str, float], cfg: Config) -> list[list[str]]:
    cand = {a for a, s in scores.items() if s >= cfg.ring_min and not snap.accounts[a].is_merchant}
    uf = _UF()
    for a in cand:
        uf.find(a)
        for e in snap.outs.get(a, []):
            if e.dst in cand:
                uf.union(a, e.dst)
        for ident in snap.acct_idents.get(a, ()):
            for b in snap.ident_members.get(ident, ()):
                if b in cand and b != a:
                    uf.union(a, b)
    groups: dict[str, list[str]] = defaultdict(list)
    for a in cand:
        groups[uf.find(a)].append(a)
    rings = [sorted(g) for g in groups.values() if len(g) >= 2 and max(scores[x] for x in g) >= cfg.flag]
    return sorted(rings, key=lambda g: -max(scores[x] for x in g))


def ring_summary(members: list[str], snap: Snapshot, scores: dict[str, float], signals: dict[str, list[Signal]]) -> dict:
    mset = set(members)
    victims: dict[str, int] = defaultdict(int)
    exits: dict[str, int] = defaultdict(int)
    cash_out_total = 0
    stats = {}
    times: list[datetime] = []
    for a in members:
        ins, outs = snap.ins.get(a, []), snap.outs.get(a, [])
        in_out = sum(e.amount for e in ins if e.src not in mset)
        in_mem = sum(e.amount for e in ins if e.src in mset)
        cash = sum(e.amount for e in outs if e.channel in CASH_CHANNELS)
        out_total = sum(e.amount for e in outs)
        cash_out_total += cash
        for e in ins:
            times.append(e.ts)
            if e.src not in mset and not snap.accounts[e.src].is_merchant:
                victims[e.src] += e.amount
        for e in outs:
            times.append(e.ts)
            if e.dst not in mset:
                exits[e.dst] += e.amount
        neighbours = {e.dst for e in outs if e.dst in mset} | {e.src for e in ins if e.src in mset}
        for ident in snap.acct_idents.get(a, ()):
            neighbours |= snap.ident_members.get(ident, set()) & mset
        neighbours.discard(a)
        if out_total and cash / out_total >= 0.5:
            role = "cash_out"
        elif in_out > 0 and in_out >= in_mem:
            role = "collector"
        else:
            role = "layer"
        through = sum(e.amount for e in ins) + out_total
        stats[a] = {"role": role, "throughput": through, "degree": len(neighbours),
                    "centrality": through * (1 + len(neighbours))}
    shared = []
    for ident, accs in snap.ident_members.items():
        inside = accs & mset
        if len(inside) >= 2:
            kind, masked = snap.ident_info.get(ident, ("?", "?"))
            shared.append({"kind": kind, "masked": masked, "accounts": len(inside)})
    top = sorted(members, key=lambda a: -stats[a]["centrality"])
    reason_counts: dict[str, int] = defaultdict(int)
    for a in members:
        for s in signals.get(a, []):
            reason_counts[s.code] += 1
    member_scores = [scores[a] for a in members]
    score = round(0.5 * max(member_scores) + 0.3 * (sum(member_scores) / len(member_scores)) + 0.2 * min(len(members), 10) / 10, 4)
    return {
        "score": score,
        "size": len(members),
        "roles": {a: stats[a]["role"] for a in members},
        "top_connected": top[:5],
        "possible_victims": len(victims),
        "victim_inflow": sum(victims.values()),
        "cash_out_total": cash_out_total,
        "exit_accounts": len(exits),
        "shared_identifiers": shared,
        "typologies": dict(sorted(reason_counts.items(), key=lambda kv: -kv[1])),
        "first_seen": min(times).isoformat() if times else None,
        "last_seen": max(times).isoformat() if times else None,
        "home_members": sum(1 for a in members if snap.accounts[a].home),
    }


def match_ring(members: list[str], known: Iterable[Ring], taken: set[str]) -> Ring | None:
    """The known ring that shares most members with this group (Jaccard at least SAME_RING), so a ring
    keeps its number and analyst status as it grows or shrinks."""
    mset = set(members)
    best, best_j = None, 0.0
    for r in known:
        if r.id in taken:
            continue
        other = set(r.member_ids)
        j = len(mset & other) / len(mset | other)
        if j > best_j:
            best, best_j = r, j
    return best if best is not None and best_j >= SAME_RING else None
