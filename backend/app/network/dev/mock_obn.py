"""A mock Open Banking Nigeria bank for demos and tests, mounted at /mock-obn.

It answers in the OBN reference shapes, backed by TheOne's own network tables, so the connector,
holds and imports can be exercised end to end before any real bank or the OBN registry is live.
Holds and PND blocks are kept in memory (they reset when the server restarts).
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_uow
from app.core.config import Settings, get_settings
from app.core.timeutil import now
from app.network.domain.entities import Account, Transfer
from app.network.infrastructure.tables import accounts, transfers

router = APIRouter(prefix="/mock-obn", tags=["mock OBN bank (demo)"])

STATE: dict = {"tokens": set(), "holds": {}, "pnd": {}, "calls": []}


def reset_state() -> None:
    STATE["tokens"].clear()
    STATE["holds"].clear()
    STATE["pnd"].clear()
    STATE["calls"].clear()


def _auth(authorization: str | None = Header(default=None)) -> None:
    token = (authorization or "").removeprefix("Bearer ").strip()
    if token not in STATE["tokens"]:
        raise HTTPException(401, "invalid or missing bearer token")


def get_db():
    for uow in get_uow():
        yield uow.session


def _touching(acc: Account):
    return or_(transfers.c.src_account_id == acc.id, transfers.c.dst_account_id == acc.id)


def _account(db: Session, account_no: str, s: Settings) -> Account:
    acc = db.scalar(select(Account).where(accounts.c.bank_code == s.network_home_bank_code, accounts.c.account_no == account_no))
    if not acc:
        raise HTTPException(404, "account not found")
    return acc


def _balance_kobo(db: Session, acc: Account) -> int:
    inflow = sum(a for (a,) in db.execute(select(transfers.c.amount_kobo).where(transfers.c.dst_account_id == acc.id)))
    outflow = sum(a for (a,) in db.execute(select(transfers.c.amount_kobo).where(transfers.c.src_account_id == acc.id)))
    # An opening balance, so demo accounts are never empty.
    return max(0, inflow - outflow) + 25_000_00


def _money(kobo: int) -> str:
    return f"{kobo / 100:,.2f}"


@router.post("/access/token")
def token(body: dict, s: Settings = Depends(get_settings)):
    if body.get("client_id") != s.network_obn_client_id or body.get("client_secret") != s.network_obn_client_secret:
        raise HTTPException(401, "invalid client credentials")
    t = secrets.token_urlsafe(24)
    STATE["tokens"].add(t)
    return {"access_token": t, "token_type": "Bearer", "expires_in": 3600}


@router.get("/account/{account_no}", dependencies=[Depends(_auth)])
def get_account(account_no: str, db: Session = Depends(get_db), s: Settings = Depends(get_settings)):
    acc = _account(db, account_no, s)
    last = db.scalar(select(transfers.c.ts).where(_touching(acc)).order_by(transfers.c.ts.desc()).limit(1))
    held = sum(h["amount_kobo"] for h in STATE["holds"].values() if h["account_no"] == account_no)
    bal = _balance_kobo(db, acc) - held
    status = "PND" if account_no in STATE["pnd"] else "Active"
    fmt = lambda d: d.strftime("%Y-%m-%d %H:%M:%S") if d else None  # noqa: E731
    return [{
        "accountNumber": acc.account_no, "customerId": f"C{acc.id[:9].upper()}", "bvn": None,
        "fullName": acc.holder_name, "shortName": (acc.holder_name or "").split(" ")[0], "currency": "NAIRA",
        "accountOpeningDate": fmt(acc.opened_at), "lastTransactionDate": fmt(last), "status": status,
        "bankSortCode": s.network_home_bank_code, "accountBalance": _money(max(bal, 0)), "phoneNumber": None,
        "accountType": "Savings" if (acc.kyc_tier or 3) < 3 else "Current", "kycTier": acc.kyc_tier,
        "accountManagerName": None, "accountManagerPhone": None,
    }]


@router.get("/limit/getCustomerTransactionLimit/{account_no}", dependencies=[Depends(_auth)])
def limits(account_no: str, db: Session = Depends(get_db), s: Settings = Depends(get_settings)):
    acc = _account(db, account_no, s)
    per_day = {1: 50_000, 2: 200_000}.get(acc.kyc_tier or 3, 10_000_000)
    return [{"channel": "ALL", "maxAmountPerTransaction": _money(per_day * 100), "maxCumulativeAmount": _money(per_day * 100),
             "maxTransaction": 50, "outstandingCumulativeAmount": _money(per_day * 100), "outstandingTransaction": "50",
             "periodType": "DAY", "transactionType": "INTER_BANK"}]


@router.api_route("/transaction/getStatement", methods=["GET", "POST"], dependencies=[Depends(_auth)])
def statement(body: dict, db: Session = Depends(get_db), s: Settings = Depends(get_settings)):
    acc = _account(db, body.get("accountNumber", ""), s)
    rows = db.scalars(select(Transfer).where(_touching(acc)).order_by(transfers.c.ts)).all()
    out = []
    for t in rows:
        ts = t.ts
        out.append({"accountNumber": acc.account_no, "amount": _money(t.amount_kobo), "bookDate": ts.isoformat(),
                    "valueDate": ts.isoformat(), "channel": t.channel, "currency": "NAIRA",
                    "debitOrCredit": "DEBIT" if t.src_account_id == acc.id else "CREDIT", "narration": t.narration or "",
                    "referenceId": t.reference, "transactionType": "TRANSFER"})
    return out


@router.post("/transaction/placeHold", dependencies=[Depends(_auth)])
def place_hold(body: dict, db: Session = Depends(get_db), s: Settings = Depends(get_settings)):
    _account(db, body.get("accountNumber", ""), s)
    ref = body.get("holdReferenceId") or secrets.token_hex(8)
    amount = int(round(float(str(body.get("amount", "0")).replace(",", "")) * 100))
    STATE["holds"][ref] = {"account_no": body["accountNumber"], "amount_kobo": amount, "reason": body.get("reason"),
                           "startdate": body.get("startdate"), "enddate": body.get("enddate")}
    STATE["calls"].append(("placeHold", body["accountNumber"], ref))
    return [{"holdReferenceId": ref, "responseCode": "SUCCESSFUL", "responseDescription": "hold placed"}]


@router.post("/transaction/removeHold", dependencies=[Depends(_auth)])
def remove_hold(body: dict):
    ref = body.get("holdReferenceId")
    if ref not in STATE["holds"]:
        # The OBN reference spells this field "repsonseMessage".
        return [{"repsonseMessage": "hold not found", "responseCode": "NOT_FOUND"}]
    STATE["holds"].pop(ref)
    STATE["calls"].append(("removeHold", body.get("accountNumber"), ref))
    return [{"repsonseMessage": "hold removed", "responseCode": "SUCCESSFUL"}]


@router.get("/transaction/getHold/{account_no}", dependencies=[Depends(_auth)])
def get_hold(account_no: str, holdReferenceId: str | None = None):
    return [{"accountNumber": h["account_no"], "amount": _money(h["amount_kobo"]), "holdReferenceId": ref,
             "reason": h["reason"], "startdate": h["startdate"], "enddate": h["enddate"], "responseCode": "SUCCESSFUL"}
            for ref, h in STATE["holds"].items() if h["account_no"] == account_no and (not holdReferenceId or ref == holdReferenceId)]


@router.post("/account/block", dependencies=[Depends(_auth)])
def block(body: dict, db: Session = Depends(get_db), s: Settings = Depends(get_settings)):
    _account(db, body.get("accountNumber", ""), s)
    STATE["pnd"][body["accountNumber"]] = {"type": body.get("blockType", "PND"), "message": body.get("blockMessage"),
                                           "at": now().isoformat()}
    STATE["calls"].append(("block", body["accountNumber"], body.get("blockType")))
    return "SUCCESSFUL"


@router.get("/_state")
def state():
    """Demo only: what the mock bank has been asked to do."""
    return {"holds": STATE["holds"], "pnd": STATE["pnd"], "calls": STATE["calls"][-50:]}
