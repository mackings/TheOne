"""Accounts, transfers and a classic mule ring, sent through the API."""
from datetime import timedelta

from app.core.timeutil import now

HOME = "999"


def acct(no, bank=HOME, name=None, **kw):
    return {"bank_code": bank, "account_no": no, "holder_name": name or f"Holder {no}", **kw}


def ref(no, bank=HOME):
    return {"bank_code": bank, "account_no": no}


_n = [0]


def tx(src, dst, naira, ts, channel="nip", src_bank=HOME, dst_bank=HOME):
    _n[0] += 1
    return {"reference": f"T{_n[0]:08d}", "ts": ts.isoformat(), "src": ref(src, src_bank), "dst": ref(dst, dst_bank),
            "amount_kobo": int(naira * 100), "channel": channel}


def ingest(client, accounts=(), transfers=()):
    r = client.post("/network/ingest", json={"accounts": list(accounts), "transfers": list(transfers)})
    assert r.status_code == 200, r.text
    return r.json()


def classic_ring(client, base=None):
    """10 victims pay a new tier-1 collector; it splits round amounts to two layers sharing its
    device; they forward to a cash-out account that withdraws at a POS agent."""
    t = base or now() - timedelta(days=2)
    accounts = [
        acct("C1", name="Collector", opened_at=(t - timedelta(days=6)).isoformat(), kyc_tier=1,
             identifiers=[{"kind": "device", "value": "dev-ring-1"}]),
        acct("L1", name="Layer One", opened_at=(t - timedelta(days=10)).isoformat(), kyc_tier=1,
             identifiers=[{"kind": "device", "value": "dev-ring-1"}]),
        acct("L2", name="Layer Two", opened_at=(t - timedelta(days=10)).isoformat(), kyc_tier=1,
             identifiers=[{"kind": "device", "value": "dev-ring-1"}]),
        acct("X1", name="Cash Out", opened_at=(t - timedelta(days=4)).isoformat(), kyc_tier=1),
        acct("POS1", name="POS Agent Musa", is_merchant=True),
    ] + [acct(f"V{i}", name=f"Victim {i}", opened_at=(t - timedelta(days=900)).isoformat(), kyc_tier=3) for i in range(10)]
    transfers = []
    for i in range(10):
        ts = t + timedelta(hours=i * 2)
        transfers.append(tx(f"V{i}", "C1", 200_000, ts, "mobile"))
        transfers.append(tx("C1", "L1", 100_000, ts + timedelta(minutes=10)))
        transfers.append(tx("C1", "L2", 60_000, ts + timedelta(minutes=12)))
        transfers.append(tx("C1", "L1", 30_000, ts + timedelta(minutes=14)))
        transfers.append(tx("L1", "X1", 128_000, ts + timedelta(minutes=30)))
        transfers.append(tx("L2", "X1", 58_000, ts + timedelta(minutes=33)))
        transfers.append(tx("X1", "POS1", 180_000, ts + timedelta(minutes=70), "pos"))
    ingest(client, accounts, transfers)
    return client.post("/network/analyse").json()


def by_no(client, flagged=False):
    rows = client.get("/network/accounts", params={"flagged": flagged, "limit": 1000}).json()
    return {r["account_no"]: r for r in rows}
