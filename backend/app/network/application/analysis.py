"""The current analysis of the network, kept fresh incrementally and consistent across server workers.

Every commit that changes graph data bumps a shared data version. A worker whose analysis was built
at an older version rebuilds. New transfers ingested by this process are applied incrementally when
nothing else changed in between; anything else (status changes, reports, another worker's writes, an
expired window) triggers a full rebuild, so incremental results never drift from a full recompute."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

from app.core.config import Settings, get_settings
from app.core.timeutil import now
from app.network.application.config import engine_config
from app.network.application.ports import NetworkUnitOfWork
from app.network.domain.engine import (Analysis, Config, RingResult, Signal, Snapshot, apply_status, base_signals,
                                       find_rings, match_ring, noisy_or, propagate, ring_summary, score_all)
from app.network.domain.entities import FIRST_RING_NO, Ring

log = logging.getLogger(__name__)


def learned_weights(uow: NetworkUnitOfWork, s: Settings) -> dict[str, float]:
    if not s.network_learning_enabled:
        return {}
    return {w.code: w.learned_weight / w.base_weight for w in uow.weights.all() if w.base_weight > 0}


def save_rings(uow: NetworkUnitOfWork, groups: list[list[str]], snap: Snapshot, scores: dict[str, float],
               signals: dict[str, list[Signal]]) -> list[RingResult]:
    """Store the rings found, keeping each known ring's id, number and analyst status as it changes."""
    known = uow.rings.active()
    taken: set[str] = set()
    stamp = now()
    next_no = (uow.rings.max_case_no() or FIRST_RING_NO - 1) + 1
    results = []
    for members in groups:
        summary = ring_summary(members, snap, scores, signals)
        ring = match_ring(members, known, taken)
        if ring is not None:
            ring.member_ids, ring.score, ring.summary, ring.updated_at = members, summary["score"], summary, stamp
            taken.add(ring.id)
        else:
            ring = uow.rings.add(Ring(score=summary["score"], member_ids=members, summary=summary, case_no=next_no))
            next_no += 1
        if ring.case_no is None:
            ring.case_no, next_no = next_no, next_no + 1
        results.append(RingResult(ring.id, ring.status, ring.score, members, summary, ring.case_no))
    for r in known:
        if r.id not in taken and r.status == "open":
            r.status, r.updated_at = "stale", stamp
    uow.commit()
    return sorted(results, key=lambda r: -r.score)


class NetworkCache:
    def __init__(self):
        self.lock = threading.RLock()
        self.version = 0
        self.local_appends = 0
        self.local_others = 0
        self.analysis: Analysis | None = None

    def bump(self) -> None:
        self.version += 1

    def reset(self) -> None:
        with self.lock:
            self.version += 1
            self.analysis = None

    def is_stale(self, uow: NetworkUnitOfWork | None = None) -> bool:
        a = self.analysis
        if a is None or a.version != self.version:
            return True
        return uow is not None and uow.data_version() != a.db_version

    def run(self, uow: NetworkUnitOfWork, settings: Settings | None = None, at: datetime | None = None) -> Analysis:
        s = settings or get_settings()
        with self.lock:
            version, dbv = self.version, uow.data_version()
            appends, others = self.local_appends, self.local_others
            weights = learned_weights(uow, s)
            cfg = engine_config(s, weights)
            t0 = time.perf_counter()
            snap = uow.graph.load_snapshot(cfg, at or now())
            scores, signals, base = score_all(snap, cfg)
            rings = save_rings(uow, find_rings(snap, scores, cfg), snap, scores, signals)
            self.analysis = Analysis(version, now(), round((time.perf_counter() - t0) * 1000, 1), snap, scores, signals, rings,
                                     {a: r.id for r in rings for a in r.members}, base=base, db_version=dbv,
                                     local_appends=appends, local_others=others, loaded_at=now(), mode="full", weights=weights)
            log.info("network analysis (full): %d accounts, %d transfers, %d flagged, %d rings in %.0f ms",
                     len(snap.accounts), snap.transfer_count, sum(1 for x in scores.values() if x >= cfg.flag),
                     len(rings), self.analysis.duration_ms)
            return self.analysis

    def get(self, uow: NetworkUnitOfWork, *, fresh: bool = True) -> Analysis:
        """fresh=True recomputes when data changed; fresh=False only computes when nothing is cached."""
        if self.analysis is None or (fresh and self.is_stale(uow)):
            return self.run(uow)
        return self.analysis

    def apply_ingest(self, uow: NetworkUnitOfWork, references: list[str], settings: Settings | None = None) -> Analysis:
        """Apply newly ingested transfers without a full rebuild, when that is provably safe."""
        s = settings or get_settings()
        with self.lock:
            a = self.analysis
            if a is None or not references:
                return self.get(uow)
            dbv = uow.data_version()
            safe = (a.loaded_at is not None and (now() - a.loaded_at).total_seconds() < s.network_full_rebuild_s
                    and self.local_others == a.local_others
                    and dbv - a.db_version == self.local_appends - a.local_appends)
            if not safe:
                return self.run(uow, s)
            t0 = time.perf_counter()
            snap = a.snapshot
            cfg = engine_config(s, a.weights)
            found = uow.graph.transfers_by_reference(references)
            have = {e.ref for lst in snap.outs.values() for e in lst} if len(found) < 50 else None
            edges = []
            for e in found:
                if e.ts < snap.window_start:
                    return self.run(uow, s)
                if e.ts > snap.at or (have is not None and e.ref in have):
                    continue
                edges.append(e)
            touched = {e.src for e in edges} | {e.dst for e in edges}
            if touched:
                uow.graph.reload_accounts(snap, touched, cfg)
            for e in edges:
                snap.outs.setdefault(e.src, []).append(e)
                snap.ins.setdefault(e.dst, []).append(e)
            for acc in touched:
                snap.outs.get(acc, []).sort(key=lambda x: x.ts)
                snap.ins.get(acc, []).sort(key=lambda x: x.ts)
            snap.transfer_count += len(edges)
            self._rescore(a, snap, cfg, touched)
            a.rings = save_rings(uow, find_rings(snap, a.scores, cfg), snap, a.scores, a.signals)
            a.ring_of = {acc: r.id for r in a.rings for acc in r.members}
            a.db_version, a.local_appends, a.version = uow.data_version(), self.local_appends, self.version
            a.computed_at, a.mode = now(), "incremental"
            a.duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            log.info("network analysis (incremental): %d new transfers in %.0f ms", len(edges), a.duration_ms)
            return a

    @staticmethod
    def _rescore(a: Analysis, snap: Snapshot, cfg: Config, touched: set[str]) -> None:
        """First-pass signals change for the endpoints and their identifier co-members; propagation can
        then change anything up to three hops downstream of those."""
        seeds = set(touched)
        for acc in list(touched):
            for ident in snap.acct_idents.get(acc, ()):
                seeds |= snap.ident_members.get(ident, set())
        for acc in seeds:
            b = base_signals(acc, snap, cfg)
            if b:
                a.base[acc] = b
            else:
                a.base.pop(acc, None)
        region, frontier = set(seeds), set(seeds)
        for _ in range(3):
            frontier = {e.dst for x in frontier for e in snap.outs.get(x, [])} - region
            region |= frontier
        for acc in region:
            if acc in a.base:
                a.signals[acc] = list(a.base[acc])
                a.scores[acc] = noisy_or(a.base[acc])
            else:
                a.signals.pop(acc, None)
                a.scores.pop(acc, None)
        propagate(snap, cfg, a.base, a.scores, a.signals, subset=region)
        apply_status(snap, a.scores, a.signals, subset=region)


cache = NetworkCache()
