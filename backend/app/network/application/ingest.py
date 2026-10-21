"""Getting bank data in: accounts, transfers, statement lines, fraud reports and confirmed outcomes."""
from __future__ import annotations

import logging
from datetime import datetime

from app.core.config import Settings
from app.core.errors import Invalid
from app.core.timeutil import new_id, utc
from app.network.application.analysis import cache
from app.network.application.ports import NetworkUnitOfWork, NibssConnector, NibssError
from app.network.domain.entities import Account, Identifier, Label, Report, StatementEntry, Transfer
from app.network.domain.identifiers import KINDS, id_hash, mask

log = logging.getLogger(__name__)

CHANNELS = {"nip", "mobile", "ussd", "internet", "card", "pos", "atm", "agent", "branch", "statement", "statement_cash"}


def get_or_create_account(uow: NetworkUnitOfWork, bank_code: str, account_no: str, name: str | None = None,
                          seen: dict | None = None) -> Account:
    key = (bank_code, account_no)
    if seen is not None and key in seen:
        return seen[key]
    acc = uow.accounts.find(bank_code, account_no)
    if acc is None:
        acc = uow.accounts.add(Account(bank_code=bank_code, account_no=account_no, holder_name=name or ""))
        uow.flush()
        cache.bump()
    elif name and not acc.holder_name:
        acc.holder_name = name
    if seen is not None:
        seen[key] = acc
    return acc


def check_watchlist(uow: NetworkUnitOfWork, account: Account, bvn: str, nibss: NibssConnector) -> bool:
    """Runs while the raw BVN is in hand; TheOne only ever stores its keyed hash. A hit becomes a report."""
    if nibss.name == "none":
        return False
    try:
        listed = nibss.watchlisted(bvn)
    except NibssError as e:
        log.warning("BVN watch-list check failed: %s", e)
        return False
    if listed and not uow.reports.exists(account.id, "bvn_watchlist"):
        uow.reports.add(Report(kind="bvn_watchlist", account_id=account.id, reporter="NIBSS watch-list",
                               note="BVN is on the industry fraud watch-list"))
    return listed


def upsert_account(uow: NetworkUnitOfWork, a: dict, s: Settings, nibss: NibssConnector, seen: dict,
                   identifiers: dict) -> Account:
    acc = get_or_create_account(uow, a["bank_code"], a["account_no"], a.get("holder_name"), seen)
    if a.get("holder_name"):
        acc.holder_name = a["holder_name"]
    for f in ("kyc_tier", "is_merchant", "synthetic_label"):
        if a.get(f) is not None:
            setattr(acc, f, a[f])
    if a.get("opened_at"):
        acc.opened_at = utc(a["opened_at"])
    if a.get("customer_id"):
        if not uow.customers.get(a["customer_id"]):
            raise Invalid(f"customer {a['customer_id']} not found")
        acc.customer_id = a["customer_id"]
    if a.get("bvn"):
        acc.bvn_hash = id_hash("bvn", a["bvn"], s.network_id_pepper)
        check_watchlist(uow, acc, a["bvn"], nibss)
    for ident in a.get("identifiers") or []:
        kind, value = ident["kind"], ident["value"]
        if kind not in KINDS - {"bvn"}:
            raise Invalid(f"identifier kind must be one of {sorted(KINDS - {'bvn'})}")
        h = id_hash(kind, value, s.network_id_pepper)
        rec = identifiers.get((kind, h)) or uow.identifiers.find(kind, h)
        if rec is None:
            rec = uow.identifiers.add(Identifier(kind=kind, value_hash=h, masked=mask(kind, value)))
            uow.flush()
        identifiers[(kind, h)] = rec
        if not uow.identifiers.is_linked(acc.id, rec.id):
            uow.identifiers.link(acc.id, rec.id)
    return acc


def ingest(uow: NetworkUnitOfWork, accounts: list[dict], transfers: list[dict], s: Settings,
           nibss: NibssConnector) -> dict:
    """Upsert accounts and append transfers. Idempotent on transfer reference; the new references are
    returned under "_refs" for incremental re-analysis."""
    seen: dict = {}
    identifiers: dict = {}
    for a in accounts:
        upsert_account(uow, a, s, nibss, seen, identifiers)
    uow.flush()
    existing = uow.transfers.existing_references([t["reference"] for t in transfers])
    added = skipped = 0
    refs: set[str] = set()
    for t in transfers:
        if t["reference"] in existing or t["reference"] in refs:
            skipped += 1
            continue
        if t["channel"] not in CHANNELS:
            raise Invalid(f"channel must be one of {sorted(CHANNELS)}")
        if t["amount_kobo"] <= 0:
            raise Invalid("amount_kobo must be positive")
        src = get_or_create_account(uow, t["src"]["bank_code"], t["src"]["account_no"], t.get("src_name"), seen)
        dst = get_or_create_account(uow, t["dst"]["bank_code"], t["dst"]["account_no"], t.get("dst_name"), seen)
        if src.id == dst.id:
            raise Invalid(f"transfer {t['reference']} has the same source and destination")
        uow.transfers.add(Transfer(reference=t["reference"], ts=utc(t["ts"]), src_account_id=src.id, dst_account_id=dst.id,
                                   amount_kobo=t["amount_kobo"], channel=t["channel"], narration=t.get("narration")))
        refs.add(t["reference"])
        added += 1
    uow.commit()
    cache.bump()
    return {"accounts": len(accounts), "transfers_added": added, "transfers_skipped": skipped, "_refs": sorted(refs)}


def ingest_statements(uow: NetworkUnitOfWork, entries: list[dict]) -> dict:
    """Statement lines feed the sender's history only: they have no counterparty."""
    seen: dict = {}
    added = skipped = 0
    for e in entries:
        acc = get_or_create_account(uow, e["bank_code"], e["account_no"], None, seen)
        if uow.statements.exists(acc.id, e["reference"]):
            skipped += 1
            continue
        uow.statements.add(StatementEntry(account_id=acc.id, reference=e["reference"], ts=utc(e["ts"]), amount_kobo=e["amount_kobo"],
                                          direction=e["direction"], channel=e.get("channel"), narration=e.get("narration")))
        added += 1
    uow.commit()
    return {"statement_lines_added": added, "statement_lines_skipped": skipped}


def add_report(uow: NetworkUnitOfWork, kind: str, bank_code: str, account_no: str, transfer_reference: str | None,
               note: str | None, reporter: str | None) -> Report:
    if kind not in {"victim_complaint", "confirmed_mule", "cleared"}:
        raise Invalid("kind must be victim_complaint, confirmed_mule or cleared")
    acc = get_or_create_account(uow, bank_code, account_no)
    r = uow.reports.add(Report(kind=kind, account_id=acc.id, transfer_reference=transfer_reference, note=note, reporter=reporter))
    uow.commit()
    cache.bump()
    return r


def set_label(uow: NetworkUnitOfWork, account_id: str, label: str, confirmed_at: datetime | None, source: str) -> None:
    if label not in {"mule", "legit"}:
        raise Invalid("label must be mule or legit")
    row = uow.labels.get(account_id)
    if row is None:
        uow.labels.add(Label(account_id=account_id, label=label, confirmed_at=utc(confirmed_at), source=source))
    else:
        row.label, row.source = label, source
        if confirmed_at:
            row.confirmed_at = utc(confirmed_at)


def ingest_bulk(uow: NetworkUnitOfWork, transfers: list[dict]) -> dict:
    """The fast path for large imports: accounts and transfers are written a batch at a time, with the
    same rules as ingest(). Known references are skipped."""
    names: dict[tuple[str, str], str] = {}
    for t in transfers:
        for side, name in (("src", t.get("src_name")), ("dst", t.get("dst_name"))):
            k = (t[side]["bank_code"][:12], t[side]["account_no"][:20])
            if name or k not in names:
                names[k] = (name or names.get(k) or "")[:120]
    keys = list(names)
    ids = uow.accounts.ids_for(keys)
    new = [{"id": new_id(), "bank_code": k[0], "account_no": k[1], "holder_name": names[k]} for k in keys if k not in ids]
    uow.accounts.insert_many(new)
    ids.update({(r["bank_code"], r["account_no"]): r["id"] for r in new})
    existing = uow.transfers.existing_references([t["reference"] for t in transfers])
    rows, seen, skipped, same = [], set(), 0, []
    for t in transfers:
        ref = t["reference"]
        if ref in existing or ref in seen:
            skipped += 1
            continue
        src = ids[(t["src"]["bank_code"][:12], t["src"]["account_no"][:20])]
        dst = ids[(t["dst"]["bank_code"][:12], t["dst"]["account_no"][:20])]
        if src == dst:
            same.append(ref)
            continue
        seen.add(ref)
        rows.append({"id": new_id(), "reference": ref, "ts": utc(t["ts"]), "src_account_id": src, "dst_account_id": dst,
                     "amount_kobo": t["amount_kobo"], "channel": t["channel"] if t["channel"] in CHANNELS else "nip",
                     "narration": t.get("narration")})
    uow.transfers.insert_many(rows)
    uow.commit()
    if rows or new:
        cache.bump()
    return {"transfers_added": len(rows), "transfers_skipped": skipped, "accounts_added": len(new), "same_account": same}
