"""Cross-bank tracing: follow money that left a ring to other banks, through NIBSS, and add what
comes back to the money map. Every request is recorded for the audit trail."""
from __future__ import annotations

from datetime import datetime

from app.core.config import Settings
from app.core.timeutil import utc
from app.network.application.analysis import cache
from app.network.application.ingest import ingest
from app.network.application.ports import NetworkUnitOfWork, NibssConnector, NibssError
from app.network.application.queries import ring_graph
from app.network.domain.entities import Trace

CASH = ("pos", "atm", "agent")


def trace_ring(uow: NetworkUnitOfWork, ring_id: str, actor: str, nibss: NibssConnector, s: Settings, depth: int = 2,
               max_accounts: int = 12) -> dict:
    """Follow money that left the ring up to `depth` hops into other banks."""
    a = cache.get(uow)
    g = ring_graph(a, ring_id)
    members = set(g["summary"]["roles"])
    nodes = {n["id"]: n for n in g["nodes"]}
    home = s.network_home_bank_code

    # Start where money crossed to another bank. Cash points are where it left as cash: nothing to follow.
    frontier: dict[tuple[str, str], list[dict]] = {}
    for e in g["edges"]:
        dst = nodes.get(e["dst"])
        if e["src"] in members and dst and dst["bank_code"] != home and dst["role"] not in ("cash_point",):
            frontier.setdefault((dst["bank_code"], dst["account_no"]), []).append(
                {"amount_kobo": e["amount"], "at": e["last"], "from_account": nodes[e["src"]]["account_no"]})
    done: set[tuple[str, str]] = set()
    added = new_accounts = followed = cash = 0
    traced: list[dict] = []
    for hop in range(1, depth + 1):
        nxt: dict[tuple[str, str], list[dict]] = {}
        for (bank_code, account_no), received in list(frontier.items())[: max_accounts - len(done)]:
            if (bank_code, account_no) in done:
                continue
            done.add((bank_code, account_no))
            rec = Trace(ring_id=ring_id, actor=actor[:80], bank_code=bank_code, account_no=account_no, hop=hop,
                             amount_in_kobo=sum(r["amount_kobo"] for r in received), connector=nibss.name)
            try:
                onward = nibss.trace(bank_code, account_no, received)
                rec.status = "answered"
            except NibssError as e:
                rec.status, rec.error, onward = "failed", str(e)[:300], []
            rec.onward_count = len(onward)
            rec.amount_onward_kobo = sum(o["amount_kobo"] for o in onward)
            uow.traces.add(rec)
            accounts, transfers = [], []
            for o in onward:
                d = o["to"]
                if not uow.accounts.find(d["bank_code"], d["account_no"]):
                    new_accounts += 1
                accounts.append({"bank_code": d["bank_code"], "account_no": d["account_no"], "holder_name": d.get("name"),
                                 "is_merchant": True if o.get("channel") in CASH else None})
                transfers.append({"reference": o["reference"], "ts": utc(datetime.fromisoformat(o["at"])),
                                  "src": {"bank_code": bank_code, "account_no": account_no},
                                  "dst": {"bank_code": d["bank_code"], "account_no": d["account_no"]},
                                  "amount_kobo": o["amount_kobo"], "channel": o.get("channel", "nip"),
                                  "narration": f"NIBSS trace hop {hop}"})
                followed += o["amount_kobo"]
                if o.get("channel") in CASH:
                    cash += o["amount_kobo"]
                elif d["bank_code"] != home:
                    nxt.setdefault((d["bank_code"], d["account_no"]), []).append(
                        {"amount_kobo": o["amount_kobo"], "at": o["at"], "from_account": account_no})
            if transfers:
                added += ingest(uow, accounts, transfers, s, nibss)["transfers_added"]
            traced.append({"bank_code": bank_code, "account_no": account_no, "hop": hop, "status": rec.status,
                           "onward": len(onward), "error": rec.error})
        uow.commit()
        frontier = nxt
        if not frontier or len(done) >= max_accounts:
            break

    after = cache.run(uow)
    # A ring that grew may be re-identified: return the one now holding most of the old members.
    best = max(after.rings, key=lambda r: len(members & set(r.members)), default=None)
    return {"accounts_traced": len(done), "requests": traced, "transfers_added": added, "new_accounts": new_accounts,
            "amount_followed": followed, "cash_found": cash, "connector": nibss.name,
            "ring_id": best.id if best and members & set(best.members) else ring_id,
            "ring_size": len(best.members) if best else None}


def trace_log(uow: NetworkUnitOfWork, ring_id: str) -> list[dict]:
    rows = uow.traces.for_ring(ring_id)
    return [{"at": r.created_at.isoformat(), "actor": r.actor, "bank_code": r.bank_code, "account_no": r.account_no,
             "hop": r.hop, "status": r.status, "error": r.error, "amount_in": r.amount_in_kobo, "onward": r.onward_count,
             "amount_onward": r.amount_onward_kobo, "connector": r.connector} for r in rows]
