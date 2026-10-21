"""Cross-bank tracing and the BVN watch-list through NIBSS (against the mock NIBSS)."""
from datetime import timedelta

import pytest

from app.core.config import get_settings
from app.network.infrastructure import nibss
from app.core.timeutil import now
from helpers.network import acct, classic_ring, ingest, tx


@pytest.fixture(autouse=True)
def clean(client):
    client.post("/network/reset")
    yield
    nibss.set_connector(None)


@pytest.fixture
def mock_nibss(client, monkeypatch):
    """Point the real HTTP connector at the mock NIBSS served by the same app."""
    monkeypatch.setattr(get_settings(), "network_nibss_connector", "http")
    nibss.set_connector(nibss.HttpNibss("http://testserver/mock-nibss", "test", http=client))


def ring_leaving_the_bank(client) -> str:
    classic_ring(client)
    t = now() - timedelta(hours=20)
    # the cash-out account also sends money to an account at another bank
    ingest(client, [acct("OUT1", bank="058", name="Far Away")],
           [tx("X1", "OUT1", 300_000, t + timedelta(minutes=5 * i), dst_bank="058") for i in range(3)])
    client.post("/network/analyse")
    return client.get("/network/rings").json()[0]["id"]


def test_trace_follows_money_into_other_banks(client, mock_nibss):
    rid = ring_leaving_the_bank(client)
    before = client.get(f"/network/rings/{rid}").json()
    out = client.post(f"/network/rings/{rid}/trace", json={"actor": "ada"}).json()
    assert out["accounts_traced"] >= 2 and out["transfers_added"] > 0 and out["new_accounts"] > 0, out
    assert out["amount_followed"] > 0 and {r["hop"] for r in out["requests"]} >= {1, 2}
    after = client.get(f"/network/rings/{out['ring_id']}").json()
    assert len(after["nodes"]) > len(before["nodes"]), "the money map now reaches past our bank"
    log = client.get(f"/network/rings/{rid}/traces").json()
    assert log and all(x["actor"] == "ada" and x["status"] == "answered" for x in log)
    again = client.post(f"/network/rings/{out['ring_id']}/trace", json={"actor": "ada"}).json()
    assert again["transfers_added"] == 0, "the same answers are not added twice"


def test_trace_without_nibss_is_recorded_as_failed(client):
    rid = ring_leaving_the_bank(client)
    out = client.post(f"/network/rings/{rid}/trace", json={"actor": "ada"}).json()
    assert out["requests"] and all(r["status"] == "failed" for r in out["requests"]) and out["transfers_added"] == 0


def test_bvn_watchlist_hit_becomes_evidence(client, mock_nibss):
    ingest(client, [acct("W1", name="Listed Person", bvn="22222222000"), acct("W2", name="Clean Person", bvn="22222222123")])
    client.post("/network/analyse")
    rows = {r["account_no"]: r for r in client.get("/network/accounts", params={"flagged": False, "limit": 100}).json()}
    sigs = {s["code"] for s in client.get(f"/network/accounts/{rows['W1']['id']}").json()["signals"]}
    assert "BVN_WATCHLIST" in sigs
    assert "W2" not in rows or not client.get(f"/network/accounts/{rows['W2']['id']}").json()["signals"]


def test_trace_is_staff_only(client, monkeypatch):
    rid = ring_leaving_the_bank(client)
    monkeypatch.setattr(get_settings(), "api_keys", "app-key:app,ana-key:analyst")
    assert client.post(f"/network/rings/{rid}/trace", json={"actor": "x"}, headers={"X-API-Key": "app-key"}).status_code == 403
    assert client.post(f"/network/rings/{rid}/trace", json={"actor": "x"}, headers={"X-API-Key": "ana-key"}).status_code == 200
