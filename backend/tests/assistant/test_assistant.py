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
