"""The assistant's read-only tools. Each runs on the server in a transaction of its own and returns
small, masked facts for the model to speak from."""
from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings
from app.core.errors import AppError
from app.network.application import alerts, decisions, queries
from app.network.application.analysis import cache
from app.network.application.ports import NetworkUnitOfWork, UnitOfWorkFactory
from app.network.domain import explain
from app.network.domain.engine import naira

log = logging.getLogger("theone.assistant")

BAND = lambda s: "high" if s >= 0.85 else "elevated" if s >= 0.6 else "watch" if s >= 0.35 else "low"  # noqa: E731
ROLE = {"collector": "collector (first to receive victims' money)", "layer": "layering (passes money on)",
        "cash_out": "cash-out (withdraws or sends out)"}


def mask(no: str | None) -> str:
    return f"…{no[-4:]}" if no and len(no) > 4 else (no or "")


def _plain(code: str) -> str:
    return explain.PLAIN.get(code, (code.replace("_", " ").lower(), ""))[0]


def _ring_id(a, prefix: str) -> str:
    p = (prefix or "").strip().lower().replace("ring", "").replace("#", "").strip()
    hits = [r.id for r in a.rings if p.isdigit() and r.number == int(p)] if p else []
    hits = hits or ([r.id for r in a.rings if r.id.lower().startswith(p)] if p else [])
    if len(hits) != 1:
        raise LookupError(f"no single ring starts with '{prefix}'" if not hits else f"'{prefix}' matches {len(hits)} rings")
    return hits[0]


def _find_accounts(a, query: str, limit: int = 5) -> list[str]:
    q = query.lower().strip().lstrip("…")
    hits = [v for v in a.snapshot.accounts.values() if q and (q in v.name.lower() or v.account_no.endswith(q))]
    hits.sort(key=lambda v: -a.risk(v.id))
    return [v.id for v in hits[:limit]]


def _brief(a, acc_id: str) -> dict:
    v = a.snapshot.accounts[acc_id]
    ring = next((r.number or r.id[:8] for r in a.rings if acc_id in r.members), None)
    return {"name": v.name, "account": mask(v.account_no), "our_customer": v.home, "risk": round(a.risk(acc_id), 2),
            "risk_band": BAND(a.risk(acc_id)), "status": v.status, "ring": ring}


def t_overview(uow: NetworkUnitOfWork, s: Settings, **_) -> dict:
    o = queries.summary_out(cache.get(uow), s)
    open_alerts = uow.alerts.open_count()
    return {"flagged_accounts": o["flagged_accounts"], "accounts_scored": o["accounts"], "open_rings": o["open_rings"],
            "confirmed_rings": o["confirmed_rings"], "open_alerts": open_alerts, "mode": o["mode"],
            "bank_link": o["bank_connector"], "transfers_last_30_days": o["transfers_in_window"]}


def t_list_rings(uow, s, status: str = "open", min_risk: float = 0.0, limit: int = 5, **_) -> dict:
    rows = [r for r in queries.list_rings(cache.get(uow)) if (status in ("", "all") or r["status"] == status) and r["score"] >= min_risk]
    rows.sort(key=lambda r: -r["score"])
    return {"rings": [{"ring": r.get("number") or r["id"][:8], "risk": round(r["score"], 2), "risk_band": BAND(r["score"]), "status": r["status"],
                       "accounts": r["size"], "possible_victims": r["possible_victims"], "paid_in": naira(r["victim_inflow"]),
                       "withdrawn_as_cash": naira(r["cash_out_total"]),
                       "main_patterns": [_plain(c) for c in list(r["typologies"])[:2]]} for r in rows[: max(1, min(limit, 10))]],
            "total_matching": len(rows)}


def t_get_ring(uow, s, ring: str, **_) -> dict:
    a = cache.get(uow)
    g = queries.ring_graph(a, _ring_id(a, ring))
    members = sorted((n for n in g["nodes"] if n["id"] in g["summary"]["roles"]), key=lambda n: -n["risk"])
    found: dict[str, int] = {}
    for n in members:
        for sg in n["signals"]:
            found[sg["code"]] = found.get(sg["code"], 0) + 1
    actions = queries.ring_actions(uow, g["id"])
    return {"ring": g.get("number") or g["id"][:8], "status": g["status"], "risk": round(g["score"], 2), "risk_band": BAND(g["score"]),
            "what_happened": [f"{t}. {b}" for t, b in explain.story(g)],
            "evidence": [{"finding": _plain(c), "accounts": k} for c, k in sorted(found.items(), key=lambda kv: -kv[1])[:6]],
            "members": [{"name": n["name"], "account": mask(n["account_no"]), "role": ROLE.get(n["role"], n["role"]),
                         "risk": round(n["risk"], 2), "status": n["status"]} for n in members[:10]],
            "analyst_actions": [{"action": x["action"], "by": x["actor"], "at": x["at"][:16]} for x in actions[-5:]]}


def t_find_account(uow, s, query: str, **_) -> dict:
    a = cache.get(uow)
    ids = _find_accounts(a, query)
    return {"matches": [_brief(a, x) for x in ids]} if ids else {"matches": [], "note": f"no account matches '{query}'"}


def t_explain_account(uow, s, query: str, **_) -> dict:
    a = cache.get(uow)
    ids = _find_accounts(a, query, 1)
    if not ids:
        return {"note": f"no account matches '{query}'"}
    d = queries.account_detail(uow, ids[0])
    return {**_brief(a, ids[0]), "kyc_tier": d["kyc_tier"], "opened": (d["opened_at"] or "")[:10],
            "money_in_30_days": naira(d["inbound_total"]), "money_out_30_days": naira(d["outbound_total"]),
            "why_flagged": [{"finding": _plain(x["code"]), "seen": x["reason"]} for x in d["signals"]]}


def t_list_alerts(uow, s, open_only: bool = True, limit: int = 5, **_) -> dict:
    rows = alerts.list_alerts(uow, open_only, max(1, min(limit, 10)))
    return {"alerts": [{"kind": x["kind"], "severity": x["severity"], "message": x["message"], "raised": x["created_at"][:16],
                        "acknowledged": bool(x.get("acknowledged_at") or x.get("acknowledged_by"))} for x in rows]}


def t_list_decisions(uow, s, decision: str = "", limit: int = 5, **_) -> dict:
    rows = [x for x in decisions.list_decisions(uow, 100) if not decision or x["decision"] == decision.upper()]
    return {"decisions": [{"when": x["created_at"][:16], "decision": x["decision"], "status": x["status"],
                           "amount": naira(x["amount_kobo"]), "from": x["source"]["name"] or mask(x["source"]["account_no"]),
                           "to": x["beneficiary"]["name"] or mask(x["beneficiary"]["account_no"]),
                           "main_reason": (x["reasons"] or [""])[0]} for x in rows[: max(1, min(limit, 10))]]}


PAGES = {"overview": "/overview", "alerts": "/network/alerts", "decisions": "/network/decisions", "rings": "/network",
         "accounts": "/network/accounts", "data": "/network/ops", "customers": "/customers"}


def t_open_page(uow, s, page: str, ring: str = "", **_) -> dict:
    if page == "ring":
        a = cache.get(uow)
        return {"ok": True, "_ui": {"navigate": f"/network/rings/{_ring_id(a, ring)}"}}
    if page not in PAGES:
        raise LookupError(f"unknown page '{page}'")
    return {"ok": True, "_ui": {"navigate": PAGES[page]}}


def _p(**props) -> dict | None:
    return {"type": "OBJECT", "properties": props} if props else None


TOOLS: dict[str, tuple[Any, str, dict]] = {
    "get_overview": (t_overview, "Headline numbers: flagged accounts, open rings, open alerts, operating mode.", _p()),
    "list_rings": (t_list_rings, "Mule rings, highest risk first.", _p(
        status={"type": "STRING", "description": "open, confirmed, dismissed or all", "enum": ["open", "confirmed", "dismissed", "all"]},
        min_risk={"type": "NUMBER", "description": "0 to 1; 0.6 is elevated, 0.85 high"},
        limit={"type": "INTEGER"})),
    "get_ring": (t_get_ring, "One ring: what happened in plain words, the evidence, its members and analyst actions.", {
        **_p(ring={"type": "STRING", "description": "ring number, e.g. 100004"}), "required": ["ring"]}),
    "find_account": (t_find_account, "Find accounts by a name or the last digits of the account number.", {
        **_p(query={"type": "STRING"}), "required": ["query"]}),
    "explain_account": (t_explain_account, "Why one account was flagged, with its money in and out.", {
        **_p(query={"type": "STRING", "description": "name or last digits of the account number"}), "required": ["query"]}),
    "list_alerts": (t_list_alerts, "Fraud-desk alerts such as duress signals and safe-limit breaches.", _p(
        open_only={"type": "BOOLEAN"}, limit={"type": "INTEGER"})),
    "list_decisions": (t_list_decisions, "Recent payment decisions made before money left.", _p(
        decision={"type": "STRING", "enum": ["ALLOW", "WARN_PAYEE", "STEP_UP_OWNER", "HOLD"], "description": "leave out for all"}, limit={"type": "INTEGER"})),
    "open_page": (t_open_page, "Show a page in the console the analyst is using.", {
        **_p(page={"type": "STRING", "enum": [*PAGES, "ring"]}, ring={"type": "STRING", "description": "needed when page is ring"}),
        "required": ["page"]}),
}


def ring_facts(uow: NetworkUnitOfWork, s: Settings, ring: str) -> dict:
    """Everything a voice briefing on one ring starts from: the story, the evidence, the members and the
    biggest money movements on its map."""
    g = queries.ring_graph(cache.get(uow), ring)
    sm = g["summary"]
    nodes = {n["id"]: n for n in g["nodes"]}

    def who(acc_id: str) -> str:
        n = nodes[acc_id]
        role = explain.ROLE.get(n["role"], (n["role"], ""))[0].lower()
        return f"{n['name'] or 'unknown'} ({mask(n['account_no'])}, {role})"

    flows = sorted(g["edges"], key=lambda e: -e["amount"])[:15]
    return {**t_get_ring(uow, s, ring=str(g.get("number") or g["id"])),
            "accounts_in_ring": sm["size"], "people_who_paid_in": sm["possible_victims"],
            "money_paid_in": naira(sm["victim_inflow"]), "taken_out_as_cash": naira(sm["cash_out_total"]),
            "first_seen": (sm["first_seen"] or "")[:10], "last_seen": (sm["last_seen"] or "")[:10],
            "biggest_money_flows": [{"from": who(e["src"]), "to": who(e["dst"]), "amount": naira(e["amount"]),
                                     "payments": e["count"], "by": e["channels"]} for e in flows]}


def run_tool(name: str, args: dict | None, s: Settings, new_uow: UnitOfWorkFactory) -> tuple[dict, dict | None]:
    """Run one tool in a transaction of its own. Returns (result for the model, UI action or None)."""
    fn = TOOLS.get(name, (None,))[0]
    if fn is None:
        return {"error": f"unknown tool {name}"}, None
    uow = new_uow()
    try:
        out = fn(uow, s, **(args or {}))
    except (LookupError, AppError) as e:
        out = {"error": getattr(e, "detail", None) or str(e)}
    # Never pass internal errors to the model.
    except Exception:
        log.exception("assistant tool %s failed", name)
        out = {"error": "that lookup failed"}
    finally:
        uow.close()
    ui = out.pop("_ui", None) if isinstance(out, dict) else None
    return out, ui


def describe(name: str, args: dict | None) -> str:
    a = args or {}
    return {"get_overview": "Checked the overview", "list_rings": "Listed rings", "get_ring": f"Looked up ring {a.get('ring', '')}",
            "find_account": f"Searched accounts for “{a.get('query', '')}”", "explain_account": f"Explained {a.get('query', '')}",
            "list_alerts": "Checked alerts", "list_decisions": "Checked payment decisions",
            "open_page": f"Opened {a.get('page', '')} {a.get('ring', '')}".strip()}.get(name, name)
