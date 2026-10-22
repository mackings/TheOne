"""Simulate a payment to a mule: the console's "Simulate a payment" page.

The account the analyst enters is new to TheOne, so on its own it would look clean. To show what happens when a
customer pays a mule, this plants the history a real mule account would have (strangers paying in, the money split
to accounts on the same phone within minutes, then cashed out at a POS agent), analyses it, and then runs the real
payment check from the demo customer's own account. The planted history is demo data, labelled as simulated, and
planting is idempotent: the same account is only planted once.
"""
from __future__ import annotations

import hashlib
import random
from datetime import timedelta

from app.core.config import Settings
from app.core.timeutil import now
from app.network.application import decisions
from app.network.application.analysis import cache
from app.network.application.ingest import ingest
from app.network.application.ports import NetworkUnitOfWork, NibssConnector
from app.network.dev.simulate import FIRST, LAST

# The customer the console sends from: "your own account" at the demo bank.
YOU = ("1000000001", "Demo Customer")
VICTIMS = 11
NAIRA = 100


def _number(rng: random.Random) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(10))


def _name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


def _your_account(s: Settings) -> tuple[list[dict], list[dict]]:
    """The demo customer, with a few ordinary months of payments so their own habits look normal."""
    home, (no, name) = s.network_home_bank_code, YOU
    t = now()
    accounts = [{"bank_code": home, "account_no": no, "holder_name": name, "opened_at": (t - timedelta(days=900)),
                 "kyc_tier": 3}]
    payees = [("2000000001", "Shoprite Lekki"), ("2000000002", "Ikeja Electric"), ("2000000003", "Bisi Adewale")]
    accounts += [{"bank_code": home, "account_no": p, "holder_name": n, "kyc_tier": 3} for p, n in payees]
    transfers = []
    for i in range(8):
        p, _ = payees[i % len(payees)]
        transfers.append({"reference": f"SIM-YOU-{i}", "ts": (t - timedelta(days=55 - i * 7, hours=3)),
                          "src": {"bank_code": home, "account_no": no}, "dst": {"bank_code": home, "account_no": p},
                          "amount_kobo": (15_000 + 5_000 * (i % 4)) * NAIRA, "channel": "mobile"})
    return accounts, transfers


def _mule_history(s: Settings, bank_code: str, account_no: str, name: str) -> tuple[list[dict], list[dict]]:
    """A classic ring around the mule: victims at our bank pay it, it splits round amounts to two accounts on its
    phone, they pass the money to a cash-out account, which withdraws at a POS agent."""
    seed = int(hashlib.sha256(f"{bank_code}:{account_no}".encode()).hexdigest()[:12], 16)
    rng = random.Random(seed)
    home, t, tag = s.network_home_bank_code, now() - timedelta(hours=20), f"{bank_code}{account_no}"
    device = [{"kind": "device", "value": f"sim-mule-{tag}"}]

    def acct(bank: str, no: str, holder: str, **kw) -> dict:
        return {"bank_code": bank, "account_no": no, "holder_name": holder, **kw}

    mule = acct(bank_code, account_no, name, opened_at=(t - timedelta(days=12)), kyc_tier=1, identifiers=device)
    layers = [acct(bank_code, _number(rng), _name(rng), opened_at=(t - timedelta(days=20)), kyc_tier=1, identifiers=device)
              for _ in range(2)]
    cash_out = acct(bank_code, _number(rng), _name(rng), opened_at=(t - timedelta(days=9)), kyc_tier=1, identifiers=device)
    pos = acct(bank_code, _number(rng), f"POS Agent {_name(rng)}", is_merchant=True)
    victims = [acct(home, _number(rng), _name(rng), opened_at=(t - timedelta(days=rng.randint(400, 3000))), kyc_tier=3)
               for _ in range(VICTIMS)]

    transfers: list[dict] = []

    def pay(src: dict, dst: dict, naira: int, at, channel: str = "nip") -> None:
        transfers.append({"reference": f"SIM-{tag}-{len(transfers)}", "ts": at,
                          "src": {"bank_code": src["bank_code"], "account_no": src["account_no"]},
                          "dst": {"bank_code": dst["bank_code"], "account_no": dst["account_no"]},
                          "amount_kobo": naira * NAIRA, "channel": channel, "narration": "simulated mule activity"})

    for i, v in enumerate(victims):
        at = t + timedelta(minutes=55 * i)
        paid = rng.randrange(150_000, 400_000, 1_000) + rng.randint(1, 999)
        pay(v, mule, paid, at, "mobile")
        first = (paid * 6 // 10) // 5_000 * 5_000
        second = (paid * 3 // 10) // 5_000 * 5_000
        pay(mule, layers[0], first, at + timedelta(minutes=9))
        pay(mule, layers[1], second, at + timedelta(minutes=12))
        pay(layers[0], cash_out, first - 1_000, at + timedelta(minutes=31))
        pay(layers[1], cash_out, second - 1_000, at + timedelta(minutes=34))
        pay(cash_out, pos, first + second - 5_000, at + timedelta(minutes=70), "pos")
    return [mule, *layers, cash_out, pos, *victims], transfers


def simulate(uow: NetworkUnitOfWork, s: Settings, nibss: NibssConnector, body: dict) -> dict:
    """Plant the mule's history (once), re-analyse, then check the payment from the demo customer's account."""
    you_accounts, you_transfers = _your_account(s)
    mule_accounts, mule_transfers = _mule_history(s, body["bank_code"], body["account_no"], body["account_name"])
    out = ingest(uow, you_accounts + mule_accounts, you_transfers + mule_transfers, s, nibss)
    if out["transfers_added"]:
        cache.run(uow)
    return decisions.decide(uow, {
        "source": {"bank_code": s.network_home_bank_code, "account_no": YOU[0]},
        "beneficiary": {"bank_code": body["bank_code"], "account_no": body["account_no"]},
        "beneficiary_name": body["account_name"], "amount_kobo": body["amount_kobo"], "channel": "mobile",
    }, s)
