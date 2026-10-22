"""Assistant: read-only tools over TheOne data, the text chat loop, and access rules.

Gemini is replaced by a fake client, so these tests never call Google."""
from types import SimpleNamespace

import pytest
from starlette.websockets import WebSocketDisconnect

from app.api.deps import new_uow
from app.assistant.application import tools
from app.assistant.infrastructure import gemini
from app.core.config import get_settings
from helpers.network import classic_ring


@pytest.fixture(autouse=True)
def clean(client):
    client.post("/network/reset")
    yield


def test_tools_answer_from_theone_data(client):
    classic_ring(client)
    s = get_settings()
    o, _ = tools.run_tool("get_overview", {}, s, new_uow)
    assert o["open_rings"] >= 1 and o["flagged_accounts"] >= 1
    rings, _ = tools.run_tool("list_rings", {"limit": 3}, s, new_uow)
    rid = rings["rings"][0]["ring"]
    ring, _ = tools.run_tool("get_ring", {"ring": str(rid)}, s, new_uow)
    assert ring["ring"] == rid and ring["what_happened"] and ring["members"]
    acc, _ = tools.run_tool("explain_account", {"query": "Collector"}, s, new_uow)
    assert acc["name"] == "Collector" and acc["why_flagged"]
    _, ui = tools.run_tool("open_page", {"page": "ring", "ring": f"ring {rid}"}, s, new_uow)
    assert ui["navigate"].startswith("/network/rings/")
    bad, _ = tools.run_tool("get_ring", {"ring": "zzzz"}, s, new_uow)
    assert "error" in bad


def test_account_numbers_are_masked():
    assert tools.mask("0043602762") == "…2762"


class FakeModels:
    def __init__(self):
        self.calls = 0

    def generate_content(self, model, contents, config):
        self.calls += 1
        # First the model asks for data.
        if self.calls == 1:
            call = SimpleNamespace(name="get_overview", args={})
            return SimpleNamespace(function_calls=[call], text=None,
                                   candidates=[SimpleNamespace(content=contents[-1])])
        return SimpleNamespace(function_calls=[], text="There is one open ring.", candidates=[])


def test_chat_runs_tools_then_answers(client, monkeypatch):
    classic_ring(client)
    fake = SimpleNamespace(models=FakeModels())
    monkeypatch.setattr(gemini, "client", lambda s: fake)
    r = client.post("/assistant/chat", json={"messages": [{"role": "user", "text": "How many open rings?"}]}).json()
    assert r["reply"] == "There is one open ring." and r["steps"] == ["Checked the overview"]


def test_access_rules(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "api_keys", "app-key:app,ana-key:analyst")
    monkeypatch.setattr(gemini, "client", lambda s: SimpleNamespace(models=FakeModels()))
    body = {"messages": [{"role": "user", "text": "hi"}]}
    assert client.post("/assistant/chat", json=body, headers={"X-API-Key": "app-key"}).status_code == 403
    assert client.post("/assistant/chat", json=body).status_code == 401
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/assistant/live?key=app-key") as ws:
            ws.receive_json()
    assert e.value.code == 4403


def test_ring_briefing_starts_from_the_ring_facts(client):
    import json

    from app.assistant.application.prompt import ring_briefing
    from app.assistant.application.tools import ring_facts

    classic_ring(client)
    ring = client.get("/network/rings").json()[0]
    uow = new_uow()
    try:
        facts = ring_facts(uow, get_settings(), str(ring["number"]))
    finally:
        uow.close()
    assert facts["ring"] == ring["number"] and facts["what_happened"] and facts["biggest_money_flows"]
    assert {"from", "to", "amount", "payments", "by"} <= set(facts["biggest_money_flows"][0])
    prompt = ring_briefing(str(facts["ring"]), json.dumps(facts, ensure_ascii=False))
    assert prompt.startswith("Your voice matters most") and "Nigerian accent" in prompt and "not Pidgin" in prompt
    assert str(ring["number"]) in prompt and facts["money_paid_in"] in prompt


def test_ziva_knows_the_page_the_analyst_is_on(client):
    from app.assistant.application.tools import current_page

    classic_ring(client)
    ring = client.get("/network/rings").json()[0]
    member = ring["top_connected"][0]["id"]
    uow = new_uow()
    try:
        assert "not said" in current_page(uow, get_settings(), {})["note"]
        assert current_page(uow, get_settings(), {"path": "/network/alerts"})["page"] == "fraud-desk alerts"
        on_ring = current_page(uow, get_settings(), {"path": f"/network/rings/{ring['number']}", "account": member})
    finally:
        uow.close()
    assert on_ring["ring"] == ring["number"] and on_ring["selected_account"]["name"]


def test_ziva_sees_money_traced_into_other_banks(client, monkeypatch):
    from datetime import timedelta

    from app.core.timeutil import now
    from app.network.infrastructure import nibss
    from helpers.network import acct, ingest, tx

    classic_ring(client)
    t = now() - timedelta(hours=20)
    ingest(client, [acct("OUT1", bank="058", name="Far Away")],
           [tx("X1", "OUT1", 300_000, t + timedelta(minutes=5 * i), dst_bank="058") for i in range(3)])
    client.post("/network/analyse")
    monkeypatch.setattr(get_settings(), "network_nibss_connector", "http")
    nibss.set_connector(nibss.HttpNibss("http://testserver/mock-nibss", "test", http=client))
    try:
        rid = client.get("/network/rings").json()[0]["id"]
        assert client.post(f"/network/rings/{rid}/trace", json={"actor": "ada"}).json()["transfers_added"] > 0
    finally:
        nibss.set_connector(None)

    s = get_settings()
    ring = client.get("/network/rings").json()[0]
    facts, _ = tools.run_tool("get_ring", {"ring": str(ring["number"])}, s, new_uow)
    onward = [x for x in facts["money_to_other_banks"] if x["from"].startswith("Far Away")]
    assert any(x["to"].startswith("Far Away") for x in facts["money_to_other_banks"]) and onward, facts["money_to_other_banks"]

    # An account found only by the NIBSS trace can be looked up by name, with how it is connected.
    name = onward[0]["to"].split(" (")[0]
    acc, _ = tools.run_tool("explain_account", {"query": name}, s, new_uow)
    assert acc["name"] == name and acc["found_by_nibss_trace"]
    assert acc["money_in_from"][0]["account"].startswith("Far Away") and acc["money_in_from"][0]["first"]
    assert any(m["place"] == "Traced at another bank" for m in acc["on_ring_maps"])


def test_misheard_names_still_find_the_account(client):
    classic_ring(client)
    s = get_settings()
    # Two names run together, both slightly misheard, as voice transcripts arrive.
    found, _ = tools.run_tool("find_account", {"query": "Collecter and Layer Too"}, s, new_uow)
    assert {"Collector", "Layer Two"} <= {m["name"] for m in found["matches"]}
    assert "closest" in found["note"], "a loose match is flagged so Ziva checks it with the analyst"
    exact, _ = tools.run_tool("find_account", {"query": "Layer Two"}, s, new_uow)
    assert exact["matches"][0]["name"] == "Layer Two" and "note" not in exact
    none, _ = tools.run_tool("find_account", {"query": "Zebedee Quorn"}, s, new_uow)
    assert none["matches"] == []
