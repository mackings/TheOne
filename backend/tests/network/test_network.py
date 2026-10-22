from datetime import timedelta

import pytest

from app.network.application.analysis import cache
from app.network.domain.identifiers import id_hash, mask, normalise
from app.core.timeutil import now
from helpers.network import HOME, acct, by_no, classic_ring, ingest, ref, tx


@pytest.fixture(autouse=True)
def clean_network(client):
    assert client.post("/network/reset").status_code == 200
    yield


# ---------------------------------------------------------------- identity


def test_identifier_normalisation_and_masking():
    assert normalise("phone", "+234 803 123 4567") == "08031234567"
    assert id_hash("phone", "+2348031234567", "p") == id_hash("phone", "0803 123 4567", "p")
    assert id_hash("phone", "08031234567", "p") != id_hash("phone", "08031234567", "q")
    assert mask("phone", "08031234567") == "0803****567"
    assert "@" in mask("email", "ada@bank.ng") and "ada" not in mask("email", "ada@bank.ng")


# ---------------------------------------------------------------- ingest


def test_ingest_is_idempotent_and_validates(client):
    t = now() - timedelta(hours=3)
    batch = [tx("A1", "A2", 5_000, t)]
    assert ingest(client, [acct("A1"), acct("A2")], batch)["transfers_added"] == 1
    again = ingest(client, [], batch)
    assert again == {"accounts": 0, "transfers_added": 0, "transfers_skipped": 1}
    bad = tx("A1", "A2", 10, t, channel="pigeon")
    assert client.post("/network/ingest", json={"transfers": [bad]}).status_code == 422
    same = tx("A1", "A1", 10, t)
    assert client.post("/network/ingest", json={"transfers": [same]}).status_code == 422


# ---------------------------------------------------------------- detection


def test_classic_ring_is_detected_with_reasons(client):
    summary = classic_ring(client)
    assert summary["rings"] == 1
    flagged = by_no(client, flagged=True)
    assert {"C1", "L1", "L2", "X1"} <= set(flagged)
    codes = {s["code"] for s in flagged["C1"]["signals"]}
    assert {"FAN_IN", "PASS_THROUGH", "SPLIT_ROUND"} <= codes
    assert "CASH_OUT" in {s["code"] for s in flagged["X1"]["signals"]}
    assert all(not no.startswith("V") for no in flagged), "victims must never be flagged for paying a mule"

    ring = client.get("/network/rings").json()[0]
    assert ring["possible_victims"] == 10
    detail = client.get(f"/network/rings/{ring['id']}").json()
    roles = {n["account_no"]: n["role"] for n in detail["nodes"]}
    assert roles["C1"] == "collector" and roles["X1"] == "cash_out" and roles["V0"] == "victim"
    assert roles["POS1"] == "cash_point"
    assert any(l["kind"] == "device" and len(l["accounts"]) == 3 for l in detail["identifier_links"])


def test_legitimate_lookalikes_are_not_flagged(client):
    t = now() - timedelta(days=10)
    accounts = [acct("TRADER", name="Mama Nkechi Provisions", opened_at=(t - timedelta(days=800)).isoformat()),
                acct("SUP", bank="B01", name="Wholesale"),
                acct("FAM1", identifiers=[{"kind": "phone", "value": "08030000001"}]),
                acct("FAM2", identifiers=[{"kind": "phone", "value": "08030000001"}])]
    transfers = []
    # Many small payers over days, then a slow weekly supplier payment.
    for i in range(30):
        accounts.append(acct(f"P{i}"))
        transfers.append(tx(f"P{i}", "TRADER", 8_000, t + timedelta(hours=i * 5), "mobile"))
    transfers.append(tx("TRADER", "SUP", 150_000, t + timedelta(days=7), dst_bank="B01"))
    transfers.append(tx("FAM1", "FAM2", 20_000, t + timedelta(days=1), "mobile"))
    ingest(client, accounts, transfers)
    client.post("/network/analyse")
    flagged = by_no(client, flagged=True)
    assert "TRADER" not in flagged and "FAM1" not in flagged and "FAM2" not in flagged
    trader = by_no(client)["TRADER"]
    # Visible to analysts, but below the flag line.
    assert {s["code"] for s in trader["signals"]} == {"FAN_IN"}


def test_simulation_quality(client):
    r = client.post("/network/simulate", json={"seed": 7, "customers": 400, "rings": 5})
    assert r.status_code == 200, r.text
    e = r.json()["evaluation"]
    assert e["victims_flagged"] == 0
    assert e["precision"] >= 0.9
    # The "slow" ring waits hours between hops and is partly missed by design; its accounts still
    # appear inside a ring for analysts. Recall across the five styles stays above 0.7.
    assert e["recall"] >= 0.7
    assert e["planted_rings_found"] == e["planted_rings"] == 5
    assert client.get("/network/evaluation").json()["recall"] == e["recall"]


def test_ring_identity_survives_reanalysis(client):
    classic_ring(client)
    first = client.get("/network/rings").json()[0]["id"]
    ingest(client, [], [tx("V0", "V1", 1_000, now() - timedelta(hours=1))])
    client.post("/network/analyse")
    assert client.get("/network/rings").json()[0]["id"] == first


# ---------------------------------------------------------------- decisions


def decide(client, src, dst, naira, **kw):
    r = client.post("/network/decide", json={"source": ref(src, kw.get("src_bank", HOME)),
                                              "beneficiary": ref(dst, kw.get("dst_bank", HOME)),
                                              "amount_kobo": int(naira * 100), **({"reference": kw["reference"]} if "reference" in kw else {})})
    assert r.status_code == 200, r.text
    return r.json()


def test_decisions_hold_mules_protect_victims_allow_normal(client):
    classic_ring(client)
    out = decide(client, "C1", "V5", 50_000)
    assert out["decision"] == "HOLD" and out["status"] == "pending_review"
    pay_mule = decide(client, "V3", "C1", 120_000)
    assert pay_mule["decision"] == "HOLD" and "protect" not in pay_mule["reasons"][0]
    assert any("receiver" in r for r in pay_mule["reasons"])
    normal = decide(client, "V1", "V2", 5_000)
    assert normal["decision"] == "ALLOW" and normal["status"] == "allowed"
    assert normal["latency_ms"] < 250
    first = decide(client, "V1", "V2", 5_000, reference="IDEMP-1")
    again = decide(client, "V1", "V2", 5_000, reference="IDEMP-1")
    assert again["id"] == first["id"] and again["idempotent_replay"] is True


def test_live_pass_through_catches_new_mule_before_reanalysis(client):
    t = now()
    ingest(client, [acct("NEW", opened_at=(t - timedelta(days=2)).isoformat(), kyc_tier=1)] + [acct(f"S{i}") for i in range(3)],
           [tx(f"S{i}", "NEW", 400_000, t - timedelta(minutes=40 - i * 10)) for i in range(3)])
    client.post("/network/analyse")
    out = decide(client, "NEW", "ELSEWHERE", 1_150_000, dst_bank="B03")
    assert "LIVE_PASS_THROUGH" in {s["code"] for s in out["source_signals"]}
    assert out["decision"] == "HOLD"
    assert any("no voice or iris" in r for r in out["reasons"])


def _mid_risk_account(client, customer_id):
    """New tier-1 account with many senders but no onward movement: risk ~0.64 (step-up band)."""
    t = now() - timedelta(days=1)
    accounts = [acct("MID", opened_at=(t - timedelta(days=5)).isoformat(), kyc_tier=1, customer_id=customer_id)]
    accounts += [acct(f"M{i}") for i in range(12)]
    ingest(client, accounts, [tx(f"M{i}", "MID", 100_000, t + timedelta(minutes=20 * i)) for i in range(12)])
    client.post("/network/analyse")
    risk = by_no(client)["MID"]["risk"]
    assert 0.6 <= risk < 0.85, risk


def test_step_up_owner_released_by_owner_voice_only(client):
    from helpers.voice import ALICE, BOB, enrol, verify

    owner = enrol(client, "Mid Owner", ALICE)
    other = enrol(client, "Someone Else", BOB)
    _mid_risk_account(client, owner)
    d = decide(client, "MID", "EXT9", 20_000, dst_bank="B02")
    assert d["decision"] == "STEP_UP_OWNER" and "voice" in d["step_up_methods"]

    wrong = verify(client, other, BOB)
    r = client.post(f"/network/decisions/{d['id']}/resolve", json={"verification_event_id": wrong["event_id"]})
    assert r.status_code == 422

    ev = verify(client, owner, ALICE)
    assert ev["decision"] == "ACCEPT"
    r = client.post(f"/network/decisions/{d['id']}/resolve", json={"verification_event_id": ev["event_id"]})
    assert r.status_code == 200 and r.json()["status"] == "released"
    assert client.post(f"/network/decisions/{d['id']}/resolve", json={"verification_event_id": ev["event_id"]}).status_code == 409


def test_hold_is_never_auto_released_by_biometrics(client):
    from helpers.voice import ALICE, enrol, verify

    owner = enrol(client, "Hold Owner", ALICE)
    classic_ring(client)
    acc = by_no(client)["C1"]
    assert client.post(f"/network/accounts/{acc['id']}/link", json={"customer_id": owner}).status_code == 200
    d = decide(client, "C1", "V2", 30_000)
    assert d["decision"] == "HOLD"
    ev = verify(client, owner, ALICE)
    r = client.post(f"/network/decisions/{d['id']}/resolve", json={"verification_event_id": ev["event_id"]}).json()
    assert r["status"] == "pending_review" and "analyst review" in r["resolution_note"]
    r = client.post(f"/network/decisions/{d['id']}/review", json={"outcome": "block", "actor": "analyst.ada"}).json()
    assert r["status"] == "blocked"


def test_warn_payee_needs_sender_confirmation(client):
    _mid_risk_account(client, None)
    d = decide(client, "M0", "MID", 10_000)
    assert d["decision"] == "WARN_PAYEE"
    assert client.post(f"/network/decisions/{d['id']}/resolve", json={}).status_code == 422
    r = client.post(f"/network/decisions/{d['id']}/resolve", json={"customer_confirmed": True}).json()
    assert r["status"] == "released"


# ---------------------------------------------------------------- analyst actions & outputs


def test_ring_actions_watchlist_confirm_evidence_and_report(client):
    classic_ring(client)
    ring = client.get("/network/rings").json()[0]
    r = client.post(f"/network/rings/{ring['id']}/actions", json={"action": "watchlist_24h", "actor": "analyst.ada"})
    assert r.status_code == 200 and len(r.json()["accounts"]) >= 1
    watched = by_no(client, flagged=False)
    target = next(no for no, row in watched.items() if row["status"] == "watchlist")
    d = decide(client, target, "V1", 1_000)
    assert d["decision"] == "HOLD" and "24-hour watch" in d["reasons"][0]

    r = client.post(f"/network/rings/{ring['id']}/actions", json={"action": "confirm", "actor": "analyst.ada", "note": "confirmed with victims"})
    assert r.json()["ring_status"] == "confirmed"
    client.post("/network/analyse")
    after = client.get("/network/rings").json()[0]
    assert after["id"] == ring["id"] and after["status"] == "confirmed"

    page = client.get(f"/network/rings/{ring['id']}/evidence")
    assert page.status_code == 200 and "Mule network evidence pack" in page.text and "confirm" in page.text
    assert "dev-ring-1" not in page.text, "raw identifiers must never appear"
    csv = client.get("/network/report.csv").text
    assert ring["id"] in csv and "999/C1" in csv

    bad = client.post(f"/network/rings/{ring['id']}/actions", json={"action": "watchlist_24h", "actor": "x", "account_ids": ["nope"]})
    assert bad.status_code == 422


def test_watchlist_expires_after_24_hours(client):
    from app.infrastructure.database import SessionLocal
    from app.network.domain.entities import Account

    classic_ring(client)
    ring = client.get("/network/rings").json()[0]
    client.post(f"/network/rings/{ring['id']}/actions", json={"action": "watchlist_24h", "actor": "a", "account_ids": [by_no(client)["X1"]["id"]]})
    db = SessionLocal()
    acc = db.get(Account, by_no(client)["X1"]["id"])
    acc.status_until = now() - timedelta(minutes=1)
    db.commit()
    db.close()
    cache.bump()
    client.post("/network/analyse")
    assert by_no(client)["X1"]["status"] == "active"


def test_device_farm_flags_new_accounts_but_not_families(client):
    t = now() - timedelta(days=3)
    farm = [acct(f"F{i}", opened_at=(t - timedelta(days=10 + i)).isoformat(), kyc_tier=1,
                 identifiers=[{"kind": "device", "value": "farm-device"}]) for i in range(4)]
    spouses = [acct(f"H{i}", opened_at=(t - timedelta(days=12)).isoformat(), identifiers=[{"kind": "device", "value": "home-tab"}]) for i in range(2)]
    senders = [acct(f"Q{i}") for i in range(4)]
    transfers = [tx(f"Q{i}", f"F{i}", 300_000, t + timedelta(hours=i)) for i in range(4)]
    transfers += [tx(f"Q{i}", f"H{i % 2}", 300_000, t + timedelta(hours=i)) for i in range(4)]
    ingest(client, farm + spouses + senders, transfers)
    client.post("/network/analyse")
    rows = by_no(client)
    assert all("DEVICE_FARM" in {s["code"] for s in rows[f"F{i}"]["signals"]} for i in range(4))
    assert all("DEVICE_FARM" not in {s["code"] for s in rows.get(f"H{i}", {"signals": []})["signals"]} for i in range(2))
    assert "agent-assisted onboarding" in next(s["reason"] for s in rows["F0"]["signals"] if s["code"] == "DEVICE_FARM")


def test_ring_number_works_everywhere(client):
    client.post("/network/reset")
    classic_ring(client)
    ring = client.get("/network/rings").json()[0]
    no = str(ring["number"])
    assert no.isdigit() and int(no) >= 100001
    client.post(f"/network/rings/{no}/actions", json={"action": "watchlist_24h", "actor": "ada"})
    by_no, by_id = client.get(f"/network/rings/{no}").json(), client.get(f"/network/rings/{ring['id']}").json()
    assert by_no["id"] == by_id["id"] and by_no["actions"] and by_no["actions"] == by_id["actions"]
    assert f"Ring {no}" in client.get(f"/network/rings/{no}/evidence").text


def test_a_stopped_payment_shows_on_the_ring_it_was_heading_to(client):
    classic_ring(client)
    ring = client.get("/network/rings").json()[0]
    before = client.get(f"/network/rings/{ring['id']}").json()
    # A new customer, not yet on the map, tries to pay the collector.
    ingest(client, [acct("NEWV", name="Ngozi Okeke")])
    held = decide(client, "NEWV", "C1", 120_000)
    assert held["decision"] == "HOLD" and held["beneficiary_ring"]["id"] == ring["id"]
    assert held["beneficiary_ring"]["number"] == ring["number"]
    decide(client, "V1", "V2", 5_000)  # an allowed payment between two ordinary customers stays off the ring

    after = client.get(f"/network/rings/{ring['id']}").json()
    assert [p["decision_id"] for p in after["stopped_payments"]] == [held["id"]]
    stopped = after["stopped_payments"][0]
    assert stopped["amount"] == 12_000_000 and stopped["from"]["name"] == "Ngozi Okeke" and stopped["to"]["name"] == "Collector"
    line = [e for e in after["edges"] if e.get("stopped")]
    assert len(line) == 1 and line[0]["dst"] == held["beneficiary"]["id"] and line[0]["amount"] == 12_000_000
    assert any(n["id"] == held["source"]["id"] and n["role"] == "victim" for n in after["nodes"]), "the sender is drawn on the map"
    # The money never moved, so the ring's own totals are unchanged.
    assert after["summary"]["victim_inflow"] == before["summary"]["victim_inflow"]
    assert after["summary"]["possible_victims"] == before["summary"]["possible_victims"]

    ok = decide(client, "V1", "V2", 5_000)
    assert ok["beneficiary_ring"] is None


def test_name_enquiry_finds_the_account_holder(client):
    classic_ring(client)
    found = client.get("/network/accounts/lookup", params={"bank_code": HOME, "account_no": "C1"})
    assert found.status_code == 200 and found.json()["name"] == "Collector" and found.json()["ring_id"]
    missing = client.get("/network/accounts/lookup", params={"bank_code": "058", "account_no": "C1"})
    assert missing.status_code == 404


def test_simulated_mule_payment_is_stopped_and_forms_a_ring(client):
    body = {"bank_code": "058", "account_no": "0123456789", "account_name": "Samuel Aluko", "amount_kobo": 85_000_000}
    out = client.post("/network/simulate/mule-payment", json=body)
    assert out.status_code == 200, out.text
    d = out.json()
    assert d["decision"] == "HOLD" and d["beneficiary"]["name"] == "Samuel Aluko" and d["beneficiary"]["bank_code"] == "058"
    ring = client.get(f"/network/rings/{d['beneficiary_ring']['id']}").json()
    assert len(ring["summary"]["roles"]) >= 3, "the mule and the accounts on its phone form a ring"
    assert [p["decision_id"] for p in ring["stopped_payments"]] == [d["id"]]
    assert ring["stopped_payments"][0]["from"]["name"] == "Demo Customer"

    # Paying the same account again does not plant its history twice.
    transfers = client.get("/network/stats").json()["transfers"]
    again = client.post("/network/simulate/mule-payment", json=body).json()
    assert again["decision"] == "HOLD" and again["beneficiary_ring"]["id"] == d["beneficiary_ring"]["id"]
    assert client.get("/network/stats").json()["transfers"] == transfers
