"""Step 1: importers, the OBN bank connector and real holds at the (mock) bank."""
import json
from datetime import timedelta

import pytest

from app.network.infrastructure import bank
from app.network.dev.mock_obn import STATE
from app.core.timeutil import now
from helpers.network import by_no, classic_ring

HOME = "999"


@pytest.fixture(autouse=True)
def clean(client):
    client.post("/network/reset")
    yield
    bank.set_connector(None)


@pytest.fixture
def obn(client, monkeypatch):
    """Point the real OBN connector at the mock bank served by the same app."""
    from app.core.config import get_settings

    st = get_settings()
    monkeypatch.setattr(st, "network_bank_connector", "obn")
    c = bank.OBNConnector("http://testserver/mock-obn", st.network_obn_client_id, st.network_obn_client_secret, http=client)
    bank.set_connector(c)
    return c


def upload(client, fmt, content, **form):
    files = {"file": ("data", content.encode() if isinstance(content, str) else content)}
    r = client.post(f"/network/import/{fmt}", files=files, data={k: v for k, v in form.items() if v is not None})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- importers


def test_csv_import_with_mapping_reports_bad_rows(client):
    t = (now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
    csv_text = ("TxnRef,When,FromBank,FromAcct,ToBank,ToAcct,Naira,Via,Memo\n"
                f"R1,{t},999,0000000001,058,0000000002,\"25,000.00\",Mobile App,rent\n"
                f"R2,{t},999,0000000001,058,0000000003,abc,USSD,bad amount\n"
                f"R3,not-a-date,999,0000000001,058,0000000004,500,POS,bad date\n"
                f"R4,{t},999,,058,0000000005,500,POS,no source\n")
    mapping = json.dumps({"reference": "TxnRef", "timestamp": "When", "src_bank": "FromBank", "src_account": "FromAcct",
                          "dst_bank": "ToBank", "dst_account": "ToAcct", "amount": "Naira", "channel": "Via", "narration": "Memo"})
    dry = upload(client, "csv", csv_text, mapping=mapping, dry_run="true")
    assert dry["rows"] == 4 and dry["valid"] == 1 and dry.get("transfers_added") is None
    assert {e["row"] for e in dry["errors"]} == {3, 4, 5}
    out = upload(client, "csv", csv_text, mapping=mapping)
    assert out["transfers_added"] == 1
    assert upload(client, "csv", csv_text, mapping=mapping)["transfers_skipped"] == 1, "re-import is idempotent"
    missing = upload(client, "csv", "a,b\n1,2\n")
    assert missing["errors"][0]["row"] == 1 and "missing columns" in missing["errors"][0]["error"]


def test_nip_import_maps_channel_codes(client):
    t = (now() - timedelta(hours=2)).strftime("%d/%m/%Y %H:%M:%S")
    text = ("SessionID,TransactionDate,SourceInstitutionCode,OriginatorAccountNumber,OriginatorAccountName,"
            "DestinationInstitutionCode,BeneficiaryAccountNumber,BeneficiaryAccountName,Amount,ChannelCode,Narration\n"
            f"000058260101,{t},058,0123456789,Ada Obi,999,0987654321,Musa Bello,150000.00,3,school fees\n"
            f"000058260102,{t},058,0123456789,Ada Obi,999,0987654322,POS Agent Bola,20000,4,cash\n")
    out = upload(client, "nip", text)
    assert out["transfers_added"] == 2 and not out["errors"]
    acc = client.get("/network/accounts/search", params={"q": "0987654321"}).json()[0]
    detail = client.get(f"/network/accounts/{acc['id']}").json()
    assert detail["recent"][0]["channel"] == "mobile" and detail["inbound_total"] == 15_000_000


PACS008 = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08"><FIToFICstmrCdtTrf>
<GrpHdr><MsgId>M1</MsgId><CreDtTm>{ts}</CreDtTm><NbOfTxs>2</NbOfTxs></GrpHdr>
<CdtTrfTxInf><PmtId><EndToEndId>E2E-001</EndToEndId></PmtId><IntrBkSttlmAmt Ccy="NGN">350000.00</IntrBkSttlmAmt>
<Dbtr><Nm>Chinedu Eze</Nm></Dbtr><DbtrAcct><Id><Othr><Id>1112223334</Id></Othr></Id></DbtrAcct>
<DbtrAgt><FinInstnId><ClrSysMmbId><MmbId>044</MmbId></ClrSysMmbId></FinInstnId></DbtrAgt>
<CdtrAgt><FinInstnId><ClrSysMmbId><MmbId>999</MmbId></ClrSysMmbId></FinInstnId></CdtrAgt>
<Cdtr><Nm>New Account</Nm></Cdtr><CdtrAcct><Id><Othr><Id>5556667778</Id></Othr></Id></CdtrAcct>
<RmtInf><Ustrd>investment</Ustrd></RmtInf></CdtTrfTxInf>
<CdtTrfTxInf><PmtId><EndToEndId>E2E-002</EndToEndId></PmtId><IntrBkSttlmAmt Ccy="USD">10.00</IntrBkSttlmAmt>
<DbtrAcct><Id><Othr><Id>1</Id></Othr></Id></DbtrAcct></CdtTrfTxInf>
</FIToFICstmrCdtTrf></Document>"""


def test_pacs008_import(client):
    out = upload(client, "pacs008", PACS008.format(ts=(now() - timedelta(hours=1)).isoformat()))
    assert out["transfers_added"] == 1 and out["errors"][0]["row"] == 2 and "USD" in out["errors"][0]["error"]
    bomb = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><x>&b;</x>'
    assert "not valid XML" in upload(client, "pacs008", bomb)["errors"][0]["error"], "entity expansion must be refused"


def test_obn_accounts_and_statement_feed_sender_history(client):
    accounts = [{"accountNumber": "2223334445", "fullName": "Sodiq Fagbola", "bvn": "22212345678", "phoneNumber": "08031234567",
                 "accountOpeningDate": (now() - timedelta(days=900)).strftime("%Y-%m-%d %H:%M:%S"), "status": "Active"},
                {"accountNumber": "12", "fullName": "Bad"}]
    out = upload(client, "obn_accounts", json.dumps(accounts))
    assert out["accounts"] == 1 and out["errors"][0]["row"] == 2
    lines = [{"amount": "20,000.00", "debitOrCredit": "DEBIT", "referenceId": f"S{i}", "narration": "bills", "channel": "mobile",
              "bookDate": (now() - timedelta(days=50 - 5 * i)).replace(hour=11).isoformat()} for i in range(8)]
    upload(client, "obn_statement", json.dumps({"Result": {"value": json.dumps(lines)}}), account_no="2223334445")
    client.post("/network/analyse")
    d = client.post("/network/decide", json={"source": {"bank_code": HOME, "account_no": "2223334445"},
                                              "beneficiary": {"bank_code": "058", "account_no": "0000000009"},
                                              "amount_kobo": 900_000_00}).json()
    reason = next(s["reason"] for s in d["sender_signals"] if s["code"] == "AMOUNT_ANOMALY")
    assert "45 times" in reason, "statement debits (largest ₦20,000) must count as history"


# ---------------------------------------------------------------- bank connector


def ring_id(client):
    classic_ring(client)
    return client.get("/network/rings").json()[0]["id"]


def test_watchlist_places_holds_and_release_removes_them(client, obn):
    rid = ring_id(client)
    out = client.post(f"/network/rings/{rid}/actions", json={"action": "watchlist_24h", "actor": "ada"}).json()
    assert out["bank_actions"] and all(a["status"] == "done" and a["kind"] == "place_hold" for a in out["bank_actions"])
    assert len(STATE["holds"]) == len(out["bank_actions"])
    hold = next(iter(STATE["holds"].values()))
    assert hold["amount_kobo"] > 0 and hold["enddate"], "hold covers the balance and ends in 24 h"

    target = out["accounts"][0]
    out = client.post(f"/network/rings/{rid}/actions", json={"action": "release", "actor": "ada", "account_ids": [target]}).json()
    assert [a["kind"] for a in out["bank_actions"]] == ["remove_hold"] and out["bank_actions"][0]["status"] == "done"
    assert len(STATE["holds"]) == len(client.get("/network/bank-actions", params={"status": "done"}).json()) - 2


def test_confirm_blocks_with_pnd(client, obn):
    rid = ring_id(client)
    out = client.post(f"/network/rings/{rid}/actions", json={"action": "confirm", "actor": "sup"}).json()
    kinds = {a["kind"] for a in out["bank_actions"]}
    assert kinds == {"block_pnd"} and all(a["status"] == "done" for a in out["bank_actions"])
    assert set(STATE["pnd"]) == {by_no(client)[x]["account_no"] for x in ("C1", "L1", "L2", "X1")}
    acct = client.get(f"/mock-obn/_state").json()
    assert all(v["type"] == "PND" for v in acct["pnd"].values())


def test_failed_bank_call_is_recorded_and_retryable(client, obn, monkeypatch):
    rid = ring_id(client)
    monkeypatch.setattr(obn, "base", "http://testserver/mock-obn-down")
    obn._token = None
    out = client.post(f"/network/rings/{rid}/actions", json={"action": "watchlist_24h", "actor": "ada"}).json()
    failed = out["bank_actions"]
    assert failed and all(a["status"] == "failed" and a["last_error"] for a in failed)
    monkeypatch.setattr(obn, "base", "http://testserver/mock-obn")
    obn._token = None
    retried = client.post(f"/network/bank-actions/{failed[0]['id']}/retry").json()
    assert retried["status"] == "done" and retried["attempts"] == 2


def test_shadow_mode_never_touches_the_bank(client, obn, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "network_mode", "shadow")
    rid = ring_id(client)
    out = client.post(f"/network/rings/{rid}/actions", json={"action": "watchlist_24h", "actor": "ada"}).json()
    assert out["bank_actions"] and all(a["status"] == "shadow" for a in out["bank_actions"])
    assert STATE["holds"] == {}


def test_without_connector_actions_are_recorded_for_manual_follow_up(client):
    rid = ring_id(client)
    out = client.post(f"/network/rings/{rid}/actions", json={"action": "confirm", "actor": "sup"}).json()
    assert out["bank_actions"] and all(a["status"] == "recorded" and a["connector"] == "none" for a in out["bank_actions"])


def test_sync_account_pulls_bank_limit_and_uses_it(client, obn):
    t0 = now() - timedelta(days=40)
    client.post("/network/ingest", json={"accounts": [{"bank_code": HOME, "account_no": "4445556667", "holder_name": "Tier Two",
                                                        "kyc_tier": 2, "opened_at": (t0 - timedelta(days=300)).isoformat()}]})
    acc = client.get("/network/accounts/search", params={"q": "4445556667"}).json()[0]
    out = client.post(f"/network/accounts/{acc['id']}/sync").json()
    assert out["daily_limit_kobo"] == 200_000_00 and out["limits_ok"]
    d = client.post("/network/decide", json={"source": {"bank_code": HOME, "account_no": "4445556667"},
                                              "beneficiary": {"bank_code": "058", "account_no": "0000000001"},
                                              "amount_kobo": 250_000_00}).json()
    reason = next(s["reason"] for s in d["sender_signals"] if s["code"] == "KYC_TIER_LIMIT")
    assert "the bank's daily limit" in reason
