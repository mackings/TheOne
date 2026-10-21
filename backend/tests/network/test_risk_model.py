"""The shadow risk model: training needs outcomes, cross-validated comparison with the rules,
per-account explanations, and it never changes decisions."""
from app.network.domain import risk_model
from helpers.network import classic_ring


def test_needs_outcomes_first(client):
    client.post("/network/reset")
    classic_ring(client)
    r = client.post("/network/model/train")
    assert r.status_code == 409 and "at least" in r.json()["detail"]
    assert client.get("/network/model").json()["trained"] is False


def test_trains_compares_and_explains(client):
    client.post("/network/reset")
    client.post("/network/simulate", json={"seed": 42, "customers": 300, "rings": 5})
    before = client.get("/network/accounts", params={"limit": 1000}).json()
    out = client.post("/network/model/train").json()
    ev = out["evaluation"]
    assert out["labels"]["mule"] >= risk_model.MIN_EACH and out["labels"]["legit"] >= risk_model.MIN_EACH
    assert ev["model"]["auc"] > 0.8 and ev["rules"]["auc"] is not None
    assert out["top_features"] and all("rule:" not in f["feature"] for f in out["top_features"])
    view = client.get("/network/model").json()
    assert view["trained"] and "agreement" in view["disagreements"]
    acc = client.get(f"/network/accounts/{before[0]['id']}").json()
    assert 0 <= acc["model"]["score"] <= 1
    after = client.get("/network/accounts", params={"limit": 1000}).json()
    assert [a["risk"] for a in before] == [a["risk"] for a in after], "the model runs in shadow: rule scores are unchanged"


def test_status_features_never_used():
    assert not any(f.endswith(("STATUS_CONFIRMED", "STATUS_CLEARED", "CONFIRMED_MULE")) for f in risk_model.FEATURES)


def test_train_needs_supervisor(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "api_keys", "ana-key:analyst")
    assert client.post("/network/model/train", headers={"X-API-Key": "ana-key"}).status_code == 403
