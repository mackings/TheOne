"""A stand-in for NIBSS, so cross-bank tracing can be shown before the bank has NIBSS access.

Trace: for each credit TheOne says reached an account at another bank, the "receiving bank"
reports that most of it moved on within the hour, split across one to three accounts, some at
POS agents. Answers are deterministic for the same question. Small amounts stop the trail.

Watch-list: a BVN is listed if it ends in 000, or was added with POST /mock-nibss/watchlist.
Served only when NETWORK_SIMULATION_ENABLED is true.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/mock-nibss", tags=["mock-nibss"])
LISTED: set[str] = set()

BANKS = ["044", "058", "057", "033", "011", "070", "232", "50515", "999992", "999991"]
FIRST = ["Tobi", "Chiamaka", "Ibrahim", "Blessing", "Uche", "Zainab", "Kunle", "Ngozi", "Musa", "Efe", "Sola", "Aisha"]
LAST = ["Okon", "Adebayo", "Danjuma", "Eze", "Lawal", "Okoro", "Bello", "Nnamdi", "Abubakar", "Etim"]
STOP_BELOW = 20_000 * 100


class Received(BaseModel):
    amount_kobo: int = Field(gt=0)
    at: str
    from_account: str | None = None


class TraceIn(BaseModel):
    bank_code: str
    account_no: str
    received: list[Received] = Field(default_factory=list, max_length=500)


class BvnIn(BaseModel):
    bvn: str = Field(min_length=11, max_length=11)


def _h(*parts: object) -> int:
    return int(hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)


@router.post("/trace")
def trace(body: TraceIn):
    onward = []
    for i, r in enumerate(body.received):
        if r.amount_kobo < STOP_BELOW:
            continue
        seed = _h(body.bank_code, body.account_no, i, r.amount_kobo)
        share = 0.75 + (seed % 21) / 100
        parts = 1 + seed % 3
        left = int(r.amount_kobo * share)
        start = datetime.fromisoformat(r.at.replace("Z", "+00:00"))
        for j in range(parts):
            k = _h(seed, j)
            amt = left // (parts - j) if j < parts - 1 else left
            left -= amt
            cash = k % 4 == 0
            bank = BANKS[k % len(BANKS)]
            name = f"POS Agent {FIRST[k % len(FIRST)]}" if cash else f"{FIRST[k % len(FIRST)]} {LAST[(k // 7) % len(LAST)]}"
            onward.append({
                "reference": f"NIBSS-{_h(body.bank_code, body.account_no, i, j):012x}",
                "at": (start + timedelta(minutes=10 + k % 80)).isoformat(),
                "to": {"bank_code": bank, "account_no": f"{k % 10_000_000_000:010d}", "name": name},
                "amount_kobo": int(amt), "channel": "pos" if cash else "nip",
            })
    return {"account": {"bank_code": body.bank_code, "account_no": body.account_no}, "onward": onward,
            "note": "simulated answer from the mock NIBSS"}


@router.post("/watchlist/check")
def watchlist_check(body: BvnIn):
    return {"listed": body.bvn.endswith("000") or body.bvn in LISTED}


@router.post("/watchlist")
def watchlist_add(body: BvnIn):
    LISTED.add(body.bvn)
    return {"listed": True}
