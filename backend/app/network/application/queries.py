"""Read views over the current analysis: the summary, rings and their money maps, and accounts.
The API and the assistant both read through these, so they always agree."""
from __future__ import annotations

from app.core.config import Settings
from app.core.errors import NotFound
from app.network.application import model
from app.network.application.analysis import cache
from app.network.application.ports import NetworkUnitOfWork, UnitOfWorkFactory
from app.network.domain.engine import CASH_CHANNELS, Analysis, signal_dicts


def refresh(new_uow: UnitOfWorkFactory, references: list[str] | None = None) -> None:
    """Re-analyse after a write, in a transaction of its own (runs as a background task)."""
    uow = new_uow()
    try:
        if references:
            cache.apply_ingest(uow, references)
        else:
            cache.run(uow)
    finally:
        uow.close()


def account_brief(a: Analysis, acc_id: str, uow: NetworkUnitOfWork | None = None) -> dict:
    v = a.snapshot.accounts.get(acc_id)
    if v is None and uow is not None:
        row = uow.accounts.get(acc_id)
        name, bank, no, home = (row.holder_name, row.bank_code, row.account_no, False) if row else ("?", "?", "?", False)
        status = row.effective_status() if row else "active"
    else:
        name, bank, no, home, status = v.name, v.bank_code, v.account_no, v.home, v.status
    return {"id": acc_id, "name": name, "bank_code": bank, "account_no": no, "home": home, "status": status,
            "risk": a.risk(acc_id), "ring_id": (rid := a.ring_of.get(acc_id)),
            "ring_number": next((r.number for r in a.rings if r.id == rid), None) if rid else None}


def summary_out(a: Analysis, s: Settings) -> dict:
    flagged = [x for x, sc in a.scores.items() if sc >= s.network_flag_threshold]
    return {
        "computed_at": a.computed_at.isoformat(), "duration_ms": a.duration_ms,
        "accounts": len(a.snapshot.accounts), "home_accounts": sum(1 for v in a.snapshot.accounts.values() if v.home),
        "transfers_in_window": a.snapshot.transfer_count, "window_days": s.network_window_days,
        "flagged_accounts": len(flagged),
        "open_rings": sum(1 for r in a.rings if r.status == "open"),
        "confirmed_rings": sum(1 for r in a.rings if r.status == "confirmed"),
        "rings": len(a.rings),
        "thresholds": {"flag": s.network_flag_threshold, "hold": s.network_hold_threshold, "ring_min": s.network_ring_min_score,
                       "fast_window_min": s.network_fast_window_min},
        "home_bank": {"code": s.network_home_bank_code, "name": s.network_home_bank_name},
        "simulation_enabled": s.network_simulation_enabled,
        "mode": s.network_mode, "bank_connector": s.network_bank_connector, "nibss_connector": s.network_nibss_connector,
        "analysis_mode": a.mode, "learning_enabled": s.network_learning_enabled, "learned_rules": len(a.weights),
        "has_synthetic_labels": any(v.label for v in a.snapshot.accounts.values()),
        "stale": cache.is_stale(),
    }


def list_rings(a: Analysis, status: str | None = None) -> list[dict]:
    out = []
    for r in a.rings:
        if status and r.status != status:
            continue
        sm = r.summary
        out.append({"id": r.id, "number": r.number, "status": r.status, "score": r.score, "size": sm["size"],
                    "possible_victims": sm["possible_victims"], "victim_inflow": sm["victim_inflow"],
                    "cash_out_total": sm["cash_out_total"], "typologies": sm["typologies"],
                    "first_seen": sm["first_seen"], "last_seen": sm["last_seen"],
                    "top_connected": [account_brief(a, x) for x in sm["top_connected"]]})
    return out


def ring_graph(a: Analysis, ring_id: str) -> dict:
    """The ring's money map. ring_id is the internal id or the ring number (e.g. 100004)."""
    ring = next((r for r in a.rings if r.id == ring_id or (ring_id.isdigit() and r.number == int(ring_id))), None)
    if ring is None:
        raise NotFound("ring not found in the current analysis")
    snap, mset = a.snapshot, set(ring.members)
    nodes: dict[str, dict] = {}
    edges: dict[tuple[str, str], dict] = {}

    def node(acc_id: str, role: str) -> None:
        if acc_id in nodes:
            return
        v = snap.accounts[acc_id]
        nodes[acc_id] = {"id": acc_id, "name": v.name, "bank_code": v.bank_code, "account_no": v.account_no,
                         "home": v.home, "role": role, "risk": a.risk(acc_id), "status": v.status,
                         "signals": signal_dicts(a.signals.get(acc_id, [])) if acc_id in mset else []}

    def edge(e) -> None:
        k = (e.src, e.dst)
        x = edges.setdefault(k, {"src": e.src, "dst": e.dst, "amount": 0, "count": 0, "channels": set(),
                                 "first": e.ts, "last": e.ts})
        x["amount"] += e.amount
        x["count"] += 1
        x["channels"].add(e.channel)
        x["first"], x["last"] = min(x["first"], e.ts), max(x["last"], e.ts)

    for acc in ring.members:
        node(acc, ring.summary["roles"].get(acc, "layer"))
    for acc in ring.members:
        for e in snap.ins.get(acc, []):
            if e.src not in mset:
                node(e.src, "victim" if not snap.accounts[e.src].is_merchant else "source")
            edge(e)
        for e in snap.outs.get(acc, []):
            if e.dst not in mset:
                dv = snap.accounts[e.dst]
                node(e.dst, "cash_point" if e.channel in CASH_CHANNELS or dv.is_merchant else "exit")
            edge(e)
    # Follow money past the ring's exits into other banks, where NIBSS traced it, up to three hops.
    frontier = [x for x, n in nodes.items() if n["role"] == "exit"]
    for _hop in range(3):
        nxt = []
        for acc in frontier:
            for e in snap.outs.get(acc, []):
                if not e.ref.startswith("NIBSS-") or e.dst in mset:
                    continue
                if e.dst not in nodes:
                    if len(nodes) > 120:
                        break
                    node(e.dst, "cash_point" if e.channel in CASH_CHANNELS or snap.accounts[e.dst].is_merchant else "traced")
                    nxt.append(e.dst)
                edge(e)
        frontier = nxt
    links = []
    for ident, accs in snap.ident_members.items():
        inside = sorted(accs & mset)
        if len(inside) >= 2:
            kind, masked = snap.ident_info.get(ident, ("?", "?"))
            links.append({"kind": kind, "masked": masked, "accounts": inside})
    return {
        "id": ring.id, "number": ring.number, "status": ring.status, "score": ring.score, "summary": ring.summary,
        "nodes": list(nodes.values()),
        "edges": [{**e, "channels": sorted(e["channels"]), "first": e["first"].isoformat(), "last": e["last"].isoformat()}
                  for e in edges.values()],
        "identifier_links": links,
    }


def ring_actions(uow: NetworkUnitOfWork, ring_id: str) -> list[dict]:
    """What analysts did on this ring, oldest first."""
    return [{"at": x.created_at.isoformat(), "actor": x.actor, "action": x.action, "accounts": x.account_ids, "note": x.note}
            for x in uow.actions.for_ring(ring_id)]


def ring_detail(uow: NetworkUnitOfWork, ring_id: str) -> dict:
    a = cache.get(uow)
    g = ring_graph(a, ring_id)
    g["actions"] = ring_actions(uow, g["id"])
    g["stopped_payments"] = add_stopped(uow, a, g)
    return g


STOPPED_SHOWN = 50


def add_stopped(uow: NetworkUnitOfWork, a: Analysis, g: dict) -> list[dict]:
    """Payments TheOne held on their way into the ring. Each goes on the money map as a "stopped" line from its
    sender, but never into the ring's totals: the money did not move."""
    members = sorted(g["summary"]["roles"])
    nodes = {n["id"]: n for n in g["nodes"]}
    lines: dict[tuple[str, str], dict] = {}
    out = []
    for d in uow.decisions.stopped_to(members, STOPPED_SHOWN):
        src, dst = account_brief(a, d.src_account_id, uow), account_brief(a, d.dst_account_id, uow)
        if d.src_account_id not in nodes:
            nodes[d.src_account_id] = {**{k: src[k] for k in ("id", "name", "bank_code", "account_no", "home", "status", "risk")},
                                       "role": "victim", "signals": []}
            g["nodes"].append(nodes[d.src_account_id])
        at = d.created_at.isoformat()
        e = lines.setdefault((d.src_account_id, d.dst_account_id), {
            "src": d.src_account_id, "dst": d.dst_account_id, "amount": 0, "count": 0, "channels": [d.channel],
            "first": at, "last": at, "stopped": True})
        e["amount"] += d.amount_kobo
        e["count"] += 1
        e["first"], e["last"] = min(e["first"], at), max(e["last"], at)
        out.append({"decision_id": d.id, "at": at, "amount": d.amount_kobo, "status": d.status,
                    "from": src, "to": dst, "reason": (d.reasons or [""])[0]})
    g["edges"].extend(lines.values())
    return out


def ring_key(uow: NetworkUnitOfWork, ring_id: str) -> str:
    """Accept a ring number (e.g. 100004) wherever a ring id is expected."""
    if ring_id.isdigit() and (rid := uow.rings.id_for_number(int(ring_id))):
        return rid
    return ring_id


def list_accounts(a: Analysis, s: Settings, flagged: bool = True, limit: int = 100) -> list[dict]:
    ids = [x for x, sc in a.scores.items() if not flagged or sc >= s.network_flag_threshold]
    ids.sort(key=lambda x: -a.scores[x])
    return [{**account_brief(a, x), "signals": signal_dicts(a.signals.get(x, []))} for x in ids[: max(1, min(limit, 1000))]]


def search_accounts(a: Analysis, q: str, limit: int = 20) -> list[dict]:
    ql = q.lower().strip()
    hits = [v for v in a.snapshot.accounts.values() if ql in v.name.lower() or ql in v.account_no.lower()]
    hits.sort(key=lambda v: -a.risk(v.id))
    return [account_brief(a, v.id) for v in hits[: max(1, min(limit, 100))]]


def lookup_account(uow: NetworkUnitOfWork, bank_code: str, account_no: str) -> dict:
    acc = uow.accounts.find(bank_code.strip(), account_no.strip())
    if acc is None:
        raise NotFound("no account with that number at this bank")
    return account_brief(cache.get(uow), acc.id, uow)


def account_detail(uow: NetworkUnitOfWork, account_id: str) -> dict:
    a = cache.get(uow)
    v = a.snapshot.accounts.get(account_id)
    if not v:
        raise NotFound("account not found")
    ins, outs = a.snapshot.ins.get(account_id, []), a.snapshot.outs.get(account_id, [])
    recent = sorted(ins + outs, key=lambda e: e.ts, reverse=True)[:50]
    return {**account_brief(a, account_id), "is_merchant": v.is_merchant, "kyc_tier": v.kyc_tier,
            "opened_at": v.opened_at.isoformat() if v.opened_at else None, "customer_id": v.customer_id,
            "signals": signal_dicts(a.signals.get(account_id, [])),
            "model": model.score_account(uow, a, account_id) if not v.is_merchant else None,
            "inbound_total": sum(e.amount for e in ins), "outbound_total": sum(e.amount for e in outs),
            "recent": [{"ts": e.ts.isoformat(), "direction": "in" if e.dst == account_id else "out",
                        "counterparty": account_brief(a, e.src if e.dst == account_id else e.dst),
                        "amount": e.amount, "channel": e.channel, "reference": e.ref} for e in recent]}


def stats(uow: NetworkUnitOfWork) -> dict:
    return {"accounts": uow.accounts.count(), "transfers": uow.transfers.count(), "decisions": uow.decisions.count()}
