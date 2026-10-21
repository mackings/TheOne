"""Add a parsed statement to the money map."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from app.core.config import Settings
from app.core.errors import Invalid
from app.core.timeutil import UTC
from app.network.application.analysis import cache
from app.network.application.ingest import ingest
from app.network.application.ports import NetworkUnitOfWork, NibssConnector
from app.network.domain.statements import BUSINESS, Parsed, check, parse, party_key

WAT_NOON_UTC = timedelta(hours=11)


def _clock(at: str) -> timedelta | None:
    """Time of day printed on the statement (Lagos time), or None."""
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p", "%I:%M%p"):
        try:
            t = datetime.strptime(at.strip().upper(), fmt)
            return timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)
        except ValueError:
            continue
    return None


def to_network(uow: NetworkUnitOfWork, p: Parsed, bank_code: str, settings: Settings, nibss: NibssConnector) -> dict:
    """Add a statement's transfers to the money map, so rings can form from statements.

    The statement's own account is keyed by the bank code you give and its account number.
    The other side is keyed by the account number in the narration when there is one (matched
    to an account TheOne already knows when that is unambiguous), or else by name and bank tag
    as a statement-only account. Fees, bills, reversals and card top-ups are left out. Lines without
    a time are placed at midday Lagos time.
    """
    if not p.account_no:
        raise Invalid("the statement does not show its account number, so it cannot be added to the map")
    # An account first seen as the far side of another statement is re-keyed to its real bank.
    if not uow.accounts.find(bank_code, p.account_no):
        stub = uow.accounts.statement_stubs(p.account_no)
        if len(stub) == 1:
            stub[0].bank_code = bank_code
            uow.flush()

    owner = {"bank_code": bank_code, "account_no": p.account_no}
    accounts = [{**owner, "holder_name": p.holder.title() if p.holder else None}]
    transfers, seen_party = [], {}
    known = {}
    for x in p.lines:
        if x.kind in ("fee", "bill", "reversal", "card") or not x.amount:
            continue
        if x.nuban and x.nuban != p.account_no:
            if x.nuban not in known:
                hits = uow.accounts.bank_codes_for(x.nuban)
                known[x.nuban] = hits[0] if len(hits) == 1 else f"ST-{(x.tag or 'UNK')[:9]}"
            other = {"bank_code": known[x.nuban], "account_no": x.nuban}
        else:
            bc, no = party_key(x)
            other = {"bank_code": bc, "account_no": no}
        k = (other["bank_code"], other["account_no"])
        if k not in seen_party:
            seen_party[k] = True
            accounts.append({**other, "holder_name": x.party.title() if x.party else None,
                             "is_merchant": True if (x.kind == "cash" or BUSINESS.search(x.party or "")) else None})
        base = datetime.combine(x.posted, datetime.min.time())
        clock = _clock(x.at)
        ts = base + clock - timedelta(hours=1) if clock is not None else base + WAT_NOON_UTC + timedelta(seconds=x.i)
        src, dst = (owner, other) if x.direction == "out" else (other, owner)
        ref = "ST-" + hashlib.sha1(f"{bank_code}|{p.account_no}|{x.posted}|{x.i}|{x.amount}|{x.desc}".encode()).hexdigest()[:24]
        transfers.append({"reference": ref, "ts": ts.replace(tzinfo=UTC), "src": src, "dst": dst, "amount_kobo": x.amount,
                          "channel": "statement_cash" if x.kind == "cash" else "statement", "narration": x.desc[:200],
                          "src_name": None, "dst_name": None})
    out = ingest(uow, accounts, transfers, settings, nibss)
    out.pop("_refs", None)
    return {**out, "counterparties": len(seen_party), "with_account_number": sum(1 for k in seen_party if not k[1].startswith("N"))}


def check_text(text: str) -> dict:
    """Mule checks and a payment-check replay for one statement. Nothing is stored."""
    try:
        return check(text)
    except ValueError as e:
        raise Invalid(str(e)) from e


def import_statement(uow: NetworkUnitOfWork, text: str, bank_code: str, s: Settings, nibss: NibssConnector) -> dict:
    """Add a statement's transfers to the money map and re-analyse, so rings can form from statements."""
    p = parse(text)
    if not p.lines:
        raise Invalid("no transactions could be read from this statement")
    out = to_network(uow, p, bank_code, s, nibss)
    a = cache.run(uow)
    owner = uow.accounts.find(bank_code, p.account_no)
    return {**out, "account_id": owner.id if owner else None, "risk_now": round(a.risk(owner.id), 2) if owner else None,
            "ring": next((r.id for r in a.rings if owner and owner.id in r.members), None)}
