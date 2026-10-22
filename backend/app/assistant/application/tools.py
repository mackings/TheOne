"""The assistant's read-only tools. Each runs on the server in a transaction of its own and returns
small, masked facts for the model to speak from."""
from __future__ import annotations

import logging
from difflib import SequenceMatcher
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


# How closely a misheard name must resemble an account name to count as a close match, and the lead an account on a
# ring's money map gets over a look-alike elsewhere (Ogunleye heard as Ogugua scores 0.69; Emeka Obi scores 0.67).
CLOSE_NAME = 0.65
ON_MAP_BONUS = 0.05


def _ring_maps(a) -> dict[str, list[tuple[object, str]]]:
    """Every account on a ring's money map (members, victims, cash points, accounts at other banks), with its ring and role."""
    out: dict[str, list[tuple[object, str]]] = {}
    for r in a.rings:
        for n in queries.ring_graph(a, r.id)["nodes"]:
            out.setdefault(n["id"], []).append((r.number or r.id[:8], n["role"]))
    return out


def _find_accounts(a, query: str, limit: int = 5) -> tuple[list[str], bool]:
    """Accounts by name or the last digits of the number, and whether the match is exact. Spoken questions arrive
    misheard, or with two names run together, so when nothing matches exactly, a name also matches when it resembles a
    run of words in the query. That looser search covers flagged accounts and accounts on a ring's money map, where
    questions land, and its answers are only the closest names, for Ziva to check with the analyst."""
    q = " ".join(query.lower().replace(",", " ").split()).lstrip("…")
    if not q:
        return [], True
    maps = _ring_maps(a)
    hits = [v for v in a.snapshot.accounts.values() if q in v.name.lower() or v.account_no.endswith(q)]
    if hits:
        # Common names repeat across banks: the one on a ring's money map is the one being asked about.
        hits.sort(key=lambda v: (v.id not in maps, -a.risk(v.id)))
        return [v.id for v in hits[:limit]], True
    words = q.split()
    scored = []
    for acc_id in set(a.scores) | set(maps):
        name = a.snapshot.accounts[acc_id].name.lower()
        n = len(name.split())
        if not n:
            continue
        best = max(SequenceMatcher(None, name, " ".join(words[i:i + n])).ratio() for i in range(max(1, len(words) - n + 1)))
        if best >= CLOSE_NAME:
            scored.append((best + (ON_MAP_BONUS if acc_id in maps else 0), a.risk(acc_id), acc_id))
    scored.sort(reverse=True)
    return [x[-1] for x in scored[:limit]], False


def _brief(a, acc_id: str) -> dict:
    v = a.snapshot.accounts[acc_id]
    ring = next((r.number or r.id[:8] for r in a.rings if acc_id in r.members), None)
    return {"name": v.name, "account": mask(v.account_no), "bank": v.bank_code, "our_customer": v.home,
            "risk": round(a.risk(acc_id), 2), "risk_band": BAND(a.risk(acc_id)), "status": v.status, "ring": ring}


def _when(ts) -> str:
    return ts.astimezone(explain.WAT).strftime("%-d %b %Y, %H:%M")


def _who(a, acc_id: str) -> str:
    v = a.snapshot.accounts[acc_id]
    return f"{v.name or 'unknown'} ({'our bank' if v.home else 'bank ' + v.bank_code}, {mask(v.account_no)})"


def _involvement(a, acc_id: str) -> dict:
    """How one account is connected: its place on each ring's money map, who paid it, whom it paid, and when."""
    def side(edges, key: str) -> list[dict]:
        agg: dict[str, list] = {}
        for e in edges:
            x = agg.setdefault(getattr(e, key), [0, 0, e.ts, e.ts])
            x[0], x[1], x[2], x[3] = x[0] + e.amount, x[1] + 1, min(x[2], e.ts), max(x[3], e.ts)
        return [{"account": _who(a, other), "amount": naira(total), "payments": count, "first": _when(first), "last": _when(last)}
                for other, (total, count, first, last) in sorted(agg.items(), key=lambda kv: -kv[1][0])[:8]]

    ins, outs = a.snapshot.ins.get(acc_id, []), a.snapshot.outs.get(acc_id, [])
    return {"on_ring_maps": [{"ring": ring, "place": explain.ROLE.get(role, (role, ""))[0], "meaning": explain.ROLE.get(role, ("", ""))[1]}
                             for ring, role in _ring_maps(a).get(acc_id, [])],
            "found_by_nibss_trace": any(e.ref.startswith("NIBSS-") for e in ins),
            "money_in_from": side(ins, "src"), "money_out_to": side(outs, "dst")}


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
    sm = g["summary"]
    nodes = {n["id"]: n for n in g["nodes"]}
    members = sorted((n for n in g["nodes"] if n["id"] in sm["roles"]), key=lambda n: -n["risk"])
    found: dict[str, int] = {}
    for n in members:
        for sg in n["signals"]:
            found[sg["code"]] = found.get(sg["code"], 0) + 1
    actions = queries.ring_actions(uow, g["id"])

    def who(acc_id: str) -> str:
        n = nodes[acc_id]
        role = explain.ROLE.get(n["role"], (n["role"], ""))[0].lower()
        return f"{n['name'] or 'unknown'} ({mask(n['account_no'])}, {role})"

    return {"ring": g.get("number") or g["id"][:8], "status": g["status"], "risk": round(g["score"], 2), "risk_band": BAND(g["score"]),
            "accounts_in_ring": sm["size"], "people_who_paid_in": sm["possible_victims"],
            "money_paid_in": naira(sm["victim_inflow"]), "taken_out_as_cash": naira(sm["cash_out_total"]),
            "first_seen": (sm["first_seen"] or "")[:10], "last_seen": (sm["last_seen"] or "")[:10],
            "what_happened": [f"{t}. {b}" for t, b in explain.story(g)],
            "evidence": [{"finding": _plain(c), "accounts": k} for c, k in sorted(found.items(), key=lambda kv: -kv[1])[:6]],
            "members": [{"name": n["name"], "account": mask(n["account_no"]), "role": ROLE.get(n["role"], n["role"]),
                         "risk": round(n["risk"], 2), "status": n["status"]} for n in members[:10]],
            "biggest_money_flows": [{"from": who(e["src"]), "to": who(e["dst"]), "amount": naira(e["amount"]),
                                     "payments": e["count"], "by": e["channels"]}
                                    for e in sorted(g["edges"], key=lambda e: -e["amount"])[:15]],
            # Small sums that left for other banks never make the biggest flows, so they are listed on their own.
            "money_to_other_banks": [{"from": who(e["src"]), "to": who(e["dst"]), "bank": nodes[e["dst"]]["bank_code"],
                                      "amount": naira(e["amount"]), "payments": e["count"]}
                                     for e in sorted(g["edges"], key=lambda e: -e["amount"])
                                     if nodes[e["dst"]]["role"] in ("exit", "traced")][:20],
            "analyst_actions": [{"action": x["action"], "by": x["actor"], "at": x["at"][:16]} for x in actions[-5:]]}


CLOSE_ONLY = "no exact match; these are the closest names to what was heard, so check with the analyst before going on"


def t_find_account(uow, s, query: str, **_) -> dict:
    a = cache.get(uow)
    ids, exact = _find_accounts(a, query)
    if not ids:
        return {"matches": [], "note": f"no account matches '{query}'"}
    return {"matches": [_brief(a, x) for x in ids], **({} if exact else {"note": CLOSE_ONLY})}


def t_explain_account(uow, s, query: str, **_) -> dict:
    a = cache.get(uow)
    ids, exact = _find_accounts(a, query)
    if not ids:
        return {"note": f"no account matches '{query}'"}
    d = queries.account_detail(uow, ids[0])
    out = {**({} if exact else {"note": CLOSE_ONLY}), **_brief(a, ids[0]), "kyc_tier": d["kyc_tier"], "opened": (d["opened_at"] or "")[:10],
           "money_in_30_days": naira(d["inbound_total"]), "money_out_30_days": naira(d["outbound_total"]),
           "why_flagged": [{"finding": _plain(x["code"]), "seen": x["reason"]} for x in d["signals"]],
           **_involvement(a, ids[0])}
    if len(ids) > 1:
        maps = _ring_maps(a)
        out["other_matches"] = [{**_brief(a, x), "on_ring_maps": [f"ring {ring}: {explain.ROLE.get(role, (role, ''))[0]}"
                                                                  for ring, role in maps.get(x, [])]} for x in ids[1:]]
    return out


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
    "find_account": (t_find_account, "Find accounts by a name or the last digits of the account number, including accounts at "
                     "other banks found by NIBSS traces. One name per call; close or misheard spellings still match.", {
        **_p(query={"type": "STRING"}), "required": ["query"]}),
    "explain_account": (t_explain_account, "One account in detail, at our bank or another: why it was flagged, where it sits on "
                        "each ring's money map, who paid it and whom it paid, with amounts and times. One name per call.", {
        **_p(query={"type": "STRING", "description": "one person's name, or the last digits of the account number"}), "required": ["query"]}),
    "list_alerts": (t_list_alerts, "Fraud-desk alerts such as duress signals and safe-limit breaches.", _p(
        open_only={"type": "BOOLEAN"}, limit={"type": "INTEGER"})),
    "list_decisions": (t_list_decisions, "Recent payment decisions made before money left.", _p(
        decision={"type": "STRING", "enum": ["ALLOW", "WARN_PAYEE", "STEP_UP_OWNER", "HOLD"], "description": "leave out for all"}, limit={"type": "INTEGER"})),
    "open_page": (t_open_page, "Show a page in the console the analyst is using.", {
        **_p(page={"type": "STRING", "enum": [*PAGES, "ring"]}, ring={"type": "STRING", "description": "needed when page is ring"}),
        "required": ["page"]}),
}


def ring_facts(uow: NetworkUnitOfWork, s: Settings, ring: str) -> dict:
    """What a call that opens on one ring starts from. `ring` is the ring's id or number."""
    g = queries.ring_graph(cache.get(uow), ring)
    return t_get_ring(uow, s, ring=str(g.get("number") or g["id"]))


SCREENS = {"/overview": "the overview: flagged accounts, open rings and payments checked", "/network": "the list of mule rings",
           "/network/accounts": "the list of flagged accounts", "/network/alerts": "fraud-desk alerts",
           "/network/decisions": "payments checked before the money left", "/network/ops": "data imports and the bank connection",
           "/customers": "customers and their biometrics", "/settings": "settings", "/simulation": "the how-it-works simulation",
           "/enrol": "voice enrolment", "/verify": "voice verification", "/iris": "iris enrolment and verification"}


def current_page(uow: NetworkUnitOfWork, s: Settings, page: dict | None) -> dict:
    """What the analyst has on screen right now, as the console last reported it."""
    if not page or not page.get("path"):
        return {"note": "the console has not said which page is open"}
    path = page["path"].rstrip("/") or "/"
    out: dict = {"page": SCREENS.get(path, path)}
    if path.startswith("/network/rings/"):
        a = cache.get(uow)
        g = queries.ring_graph(a, path.rsplit("/", 1)[1])
        out |= {"page": f"ring {g.get('number') or g['id'][:8]}, with its story and money flow map",
                "ring": g.get("number") or g["id"][:8], "tip": "call get_ring with this ring for its facts"}
        if page.get("account") and page["account"] in a.snapshot.accounts:
            out["selected_account"] = {**_brief(a, page["account"]), **_involvement(a, page["account"])}
    return out


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
