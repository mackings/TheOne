"""Sender-side risk, duress protection and attested device step-up."""
import base64
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.timeutil import now
from app.identity.domain.entities import StepUpChallenge
from app.infrastructure.database import SessionLocal
from app.network.application import decisions as decisions_mod
from app.network.domain.entities import AccountIdentifier, Transfer
from helpers.voice import ALICE, BOB, enrol, verify
from helpers.iris import burst
from helpers.network import acct, ingest, ref, tx

HOME = "999"


@pytest.fixture(autouse=True)
def clean(client):
    client.post("/network/reset")
    yield


@pytest.fixture
def lenient_iris(monkeypatch):
    from app.core.config import get_settings

    st = get_settings()
    monkeypatch.setattr(st, "iris_min_focus", 5.0)
    monkeypatch.setattr(st, "iris_min_radius_px", 20)


def decide(client, src, dst, naira, dst_bank=HOME, **extra):
    r = client.post("/network/decide", json={"source": ref(src), "beneficiary": ref(dst, dst_bank),
                                              "amount_kobo": int(naira * 100), **extra})
    assert r.status_code == 200, r.text
    return r.json()


def codes(d, key="sender_signals"):
    return {s["code"] for s in d[key]}


def history(client, src="S", payee="P", n=10, low=10_000, high=20_000, tier=3, customer_id=None, days=60):
    """An ordinary customer who regularly sends modest amounts to one payee."""
    t0 = now() - timedelta(days=days)
    accounts = [acct(src, kyc_tier=tier, opened_at=(t0 - timedelta(days=400)).isoformat(), customer_id=customer_id), acct(payee)]
    step = (days - 2) / n
    # daytime only (11:00 UTC = 12:00 WAT), so night-time rules have a clean baseline
    ingest(client, accounts, [tx(src, payee, low + (high - low) * i / max(n - 1, 1),
                                 (t0 + timedelta(days=step * i)).replace(hour=11, minute=0)) for i in range(n)])
    client.post("/network/analyse")


def alerts(client, kind=None):
    rows = client.get("/network/alerts").json()
    return [a for a in rows if kind is None or a["kind"] == kind]


# ---------------------------------------------------------------- 1. sender-side risk


def test_ordinary_customers_huge_transfer_is_held(client):
    history(client)
    d = decide(client, "S", "P", 50_000_000_000)
    assert d["decision"] == "HOLD"
    assert {"REVIEW_CAP", "AMOUNT_ANOMALY"} <= codes(d)
    assert d["sender_risk"] >= 0.95
    assert any(a["decision_id"] == d["id"] for a in alerts(client, "review_cap"))


def test_normal_payment_is_allowed(client):
    history(client)
    d = decide(client, "S", "P", 15_000)
    assert d["decision"] == "ALLOW" and d["sender_risk"] == 0.0 and d["sender_signals"] == []


def test_amount_anomaly_steps_up_owner_when_enrolled_else_bank_factor(client):
    history(client)
    d = decide(client, "S", "P", 500_000)
    assert "AMOUNT_ANOMALY" in codes(d)
    assert d["decision"] == "STEP_UP_OWNER" and d["step_up_methods"] == ["bank_otp"]
    r = client.post(f"/network/decisions/{d['id']}/resolve", json={"bank_factor_passed": True}).json()
    assert r["status"] == "released"

    client.post("/network/reset")
    owner = enrol(client, "Anomaly Owner", ALICE)
    history(client, customer_id=owner)
    d = decide(client, "S", "P", 500_000)
    assert d["decision"] == "STEP_UP_OWNER" and "voice" in d["step_up_methods"]
    no_otp = client.post(f"/network/decisions/{d['id']}/resolve", json={"bank_factor_passed": True})
    assert no_otp.status_code == 422, "an OTP must not replace an enrolled biometric"
    assert "25 times" in next(s["reason"] for s in d["sender_signals"] if s["code"] == "AMOUNT_ANOMALY")


def test_new_payee_high_value_is_flagged(client):
    history(client)
    d = decide(client, "S", "NEWGUY", 300_000, dst_bank="B04")
    assert "NEW_PAYEE_HIGH_VALUE" in codes(d)


def test_kyc_tier_limit(client):
    history(client, tier=1, low=5_000, high=10_000)
    d = decide(client, "S", "P", 60_000)
    assert d["decision"] == "HOLD" and "KYC_TIER_LIMIT" in codes(d)


def test_rapid_drain_needs_value_and_several_payees(client):
    history(client, low=40_000, high=60_000)
    for _ in range(3):
        decide(client, "S", "P", 5_000)
    assert "RAPID_DRAIN" not in codes(decide(client, "S", "P", 5_000)), "small bills are not a drain"
    client.post("/network/reset")
    history(client, low=40_000, high=60_000)
    for i in range(3):
        assert decide(client, "S", f"X{i}", 45_000, dst_bank="B02")["decision"] == "ALLOW"
    d = decide(client, "S", "X9", 45_000, dst_bank="B02")
    assert "RAPID_DRAIN" in codes(d)


def test_new_device_for_high_value(client):
    history(client, low=100_000, high=200_000)
    decide(client, "S", "P", 15_000, device="phone-old")
    db = SessionLocal()
    for link in db.query(AccountIdentifier).all():
        link.first_seen = now() - timedelta(days=30)
    db.commit()
    db.close()
    assert "NEW_DEVICE_HIGH_VALUE" not in codes(decide(client, "S", "P", 150_000, device="phone-old"))
    d = decide(client, "S", "P", 150_000, device="phone-new")
    assert "NEW_DEVICE_HIGH_VALUE" in codes(d) and d["context"]["device"]["state"] == "new"
    assert "phone-new" not in str(d), "raw device ids must never be echoed back"


def test_location_anomaly(client):
    history(client, low=100_000, high=200_000)
    lagos = {"lat": 6.5244, "lon": 3.3792}
    for _ in range(3):
        decide(client, "S", "P", 10_000, location=lagos)
    d = decide(client, "S", "P", 150_000, location={"lat": 12.0022, "lon": 8.5920})
    assert "LOCATION_ANOMALY" in codes(d)


def test_night_high_value(client, monkeypatch):
    history(client, low=100_000, high=200_000)
    # 01:30 UTC is 02:30 in Lagos.
    night = now().replace(hour=1, minute=30, second=0, microsecond=0)
    if night > now():
        night -= timedelta(days=1)
    monkeypatch.setattr(decisions_mod, "now", lambda: night)
    d = decide(client, "S", "P", 150_000)
    assert "NIGHT_HIGH_VALUE" in codes(d)


def test_safe_limit_lowering_is_immediate_raising_waits(client):
    history(client)
    acc_id = client.get("/network/accounts/search", params={"q": "Holder S"}).json()[0]["id"]
    r = client.put(f"/network/accounts/{acc_id}/safe-limit", json={"limit_kobo": 20_000 * 100}).json()
    assert r["limit_kobo"] == 2_000_000
    d = decide(client, "S", "P", 25_000)
    assert d["decision"] == "HOLD" and any("limit the customer set" in x for x in d["reasons"])
    assert any(a["decision_id"] == d["id"] for a in alerts(client, "safe_limit"))
    r = client.put(f"/network/accounts/{acc_id}/safe-limit", json={"limit_kobo": 1_000_000 * 100}).json()
    assert r["limit_kobo"] == 2_000_000 and r["pending_limit_kobo"] == 100_000_000 and "24 hours" in r["note"]
    assert decide(client, "S", "P", 25_000)["decision"] == "HOLD", "a raise must not apply immediately"
    r = client.put(f"/network/accounts/{acc_id}/safe-limit", json={"limit_kobo": 5_000 * 100}).json()
    assert r["limit_kobo"] == 500_000 and r["pending_limit_kobo"] is None


# ---------------------------------------------------------------- 2. duress


def test_duress_eye_must_differ_from_normal_eye(client, lenient_iris):
    cid = client.post("/customers", json={"display_name": "Duress Dayo"}).json()["id"]
    assert client.post("/iris/duress/enrol", data={"customer_id": cid}, files=burst(11)).status_code == 409
    assert client.post("/iris/enrol", data={"customer_id": cid}, files=burst(11)).status_code == 200
    same = client.post("/iris/duress/enrol", data={"customer_id": cid}, files=burst(11))
    assert same.status_code == 422 and "other eye" in same.json()["detail"]
    ok = client.post("/iris/duress/enrol", data={"customer_id": cid}, files=burst(31))
    assert ok.status_code == 200, ok.text
    assert client.get(f"/customers/{cid}").json()["iris_duress_enrolled"] is True


def test_duress_eye_looks_normal_but_alerts(client, lenient_iris):
    cid = client.post("/customers", json={"display_name": "Duress Dayo"}).json()["id"]
    client.post("/iris/enrol", data={"customer_id": cid}, files=burst(11))
    client.post("/iris/duress/enrol", data={"customer_id": cid}, files=burst(31))

    normal = client.post("/iris/verify", data={"customer_id": cid}, files=burst(11)).json()
    forced = client.post("/iris/verify", data={"customer_id": cid}, files=burst(31)).json()
    assert normal["decision"] == forced["decision"] == "ACCEPT"
    assert set(forced) == set(normal) and "duress" not in str(forced).lower(), "nothing on screen may reveal duress"
    assert client.post("/iris/verify", data={"customer_id": cid}, files=burst(12)).json()["decision"] == "REJECT"

    events = {e["id"]: e for e in client.get(f"/customers/{cid}/events").json()}
    assert events[forced["event_id"]]["duress"] is True and events[normal["event_id"]]["duress"] is False
    a = alerts(client, "duress")
    assert len(a) == 1 and a[0]["event_id"] == forced["event_id"] and a[0]["severity"] == "critical"


def test_duress_on_a_transfer_shows_success_but_holds_it(client, lenient_iris):
    owner = enrol(client, "Forced Femi", ALICE)
    client.post("/iris/enrol", data={"customer_id": owner}, files=burst(11))
    client.post("/iris/duress/enrol", data={"customer_id": owner}, files=burst(31))
    history(client, customer_id=owner)
    d = decide(client, "S", "ROBBER", 500_000, dst_bank="B05")
    assert d["decision"] == "STEP_UP_OWNER"
    ev = client.post("/iris/verify", data={"customer_id": owner}, files=burst(31)).json()
    shown = client.post(f"/network/decisions/{d['id']}/resolve", json={"verification_event_id": ev["event_id"]}).json()
    assert shown["status"] == "released", "the customer's screen must show success"
    assert "duress" not in str(shown).lower()

    sent = client.post(f"/network/decisions/{d['id']}/execute").json()
    assert sent["transfers_added"] == 1, "the app's 'send' must look normal"
    truth = next(x for x in client.get("/network/decisions").json() if x["id"] == d["id"])
    assert truth["status"] == "duress_hold"
    db = SessionLocal()
    assert db.query(Transfer).filter_by(reference=sent["reference"]).count() == 0, "nothing was really sent"
    db.close()
    robber = client.get("/network/accounts/search", params={"q": "ROBBER"}).json()[0]
    assert robber["status"] == "watchlist"
    a = [x for x in alerts(client, "duress") if x["decision_id"] == d["id"]]
    assert a and "held" in a[0]["message"]
    ack = client.post(f"/network/alerts/{a[0]['id']}/ack", json={"actor": "fraud.desk"}).json()
    assert ack["acknowledged_by"] == "fraud.desk"
    assert all(x["id"] != a[0]["id"] for x in alerts(client))


# ---------------------------------------------------------------- 3. attested device step-up


def _device(client, customer_id):
    key = ec.generate_private_key(ec.SECP256R1())
    der = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    r = client.post("/stepup/device/keys", json={"customer_id": customer_id, "public_key": base64.b64encode(der).decode(), "label": "Pixel"})
    assert r.status_code == 201, r.text
    return key, r.json()["device_key_id"]


def _sign(key, payload):
    return base64.b64encode(key.sign(payload.encode(), ec.ECDSA(hashes.SHA256()))).decode()


def test_attested_step_up_signature_checks(client):
    cid = client.post("/customers", json={"display_name": "Key Kemi"}).json()["id"]
    key, kid = _device(client, cid)
    again = client.post("/stepup/device/keys", json={"customer_id": cid, "public_key": base64.b64encode(
        key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).decode()})
    assert again.json() == {"device_key_id": kid, "created": False}

    ch = client.post("/stepup/device/challenge", json={"customer_id": cid, "device_key_id": kid}).json()
    assert ch["payload"].startswith("theone-stepup:v1:")
    other = ec.generate_private_key(ec.SECP256R1())
    assert client.post("/stepup/device/attested", json={"challenge_id": ch["challenge_id"], "signature": _sign(other, ch["payload"])}).status_code == 422
    ok = client.post("/stepup/device/attested", json={"challenge_id": ch["challenge_id"], "signature": _sign(key, ch["payload"])})
    assert ok.status_code == 200 and ok.json()["decision"] == "ACCEPT"
    assert client.post("/stepup/device/attested", json={"challenge_id": ch["challenge_id"], "signature": _sign(key, ch["payload"])}).status_code == 409

    old = client.post("/stepup/device/challenge", json={"customer_id": cid, "device_key_id": kid}).json()
    db = SessionLocal()
    row = db.get(StepUpChallenge, old["challenge_id"])
    row.expires_at = now() - timedelta(seconds=1)
    db.commit()
    db.close()
    assert client.post("/stepup/device/attested", json={"challenge_id": old["challenge_id"], "signature": _sign(key, old["payload"])}).status_code == 410

    bad = client.post("/stepup/device/keys", json={"customer_id": cid, "public_key": base64.b64encode(b"nonsense").decode()})
    assert bad.status_code == 422


def test_only_attested_device_events_resolve_transfers(client):
    owner = enrol(client, "Attested Ade", ALICE)
    history(client, customer_id=owner)
    d = decide(client, "S", "P", 500_000)
    assert d["decision"] == "STEP_UP_OWNER" and "device" in d["step_up_methods"]

    legacy = client.post("/stepup/device", json={"customer_id": owner, "method": "fingerprint"}).json()
    r = client.post(f"/network/decisions/{d['id']}/resolve", json={"verification_event_id": legacy["event_id"]})
    assert r.status_code == 422 and "hardware key" in r.json()["detail"]

    key, kid = _device(client, owner)
    ch = client.post("/stepup/device/challenge", json={"customer_id": owner, "device_key_id": kid}).json()
    ev = client.post("/stepup/device/attested", json={"challenge_id": ch["challenge_id"], "signature": _sign(key, ch["payload"])}).json()
    r = client.post(f"/network/decisions/{d['id']}/resolve", json={"verification_event_id": ev["event_id"]})
    assert r.status_code == 200 and r.json()["status"] == "released"

    d2 = decide(client, "S", "P", 500_000)
    r = client.post(f"/network/decisions/{d2['id']}/resolve", json={"verification_event_id": ev["event_id"]})
    assert r.status_code in (409, 422), "one verification must not approve two transfers"


def test_someone_elses_device_key_cannot_be_challenged(client):
    a = client.post("/customers", json={"display_name": "A"}).json()["id"]
    b = enrol(client, "B", BOB)
    _, kid = _device(client, a)
    assert client.post("/stepup/device/challenge", json={"customer_id": b, "device_key_id": kid}).status_code == 404
