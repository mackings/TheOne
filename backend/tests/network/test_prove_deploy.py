"""Steps 2 and 3: backtest, labels, learning; incremental analysis, shared staleness, migrations, roles."""
import random
from datetime import timedelta

import pytest

from app.core.config import get_settings
from app.infrastructure.unit_of_work import SqlUnitOfWork
from app.network.application.analysis import NetworkCache, cache
from app.network.application.config import engine_config
from app.network.domain import engine as eng
from app.network.domain.engine import Config, score_all
from app.network.domain.engine.scoring import _weighted
from app.network.domain.entities import Account
from app.core.timeutil import now
from helpers.network import classic_ring


@pytest.fixture(autouse=True)
def clean(client):
    client.post("/network/reset")
    yield


# ---------------------------------------------------------------- step 2: prove


def test_backtest_reports_recall_lead_time_and_capacity(client):
    client.post("/network/simulate", json={"seed": 42, "customers": 300, "rings": 5})
    bt = client.post("/network/backtest", json={"days": 14, "step_hours": 24, "capacity_per_day": 10}).json()
    assert bt["labels"]["mules"] > 10 and bt["labels"]["legit"] > 10
    assert bt["recall"] >= 0.7 and bt["legit_flagged"] == 0
    assert bt["precision_at_capacity"] >= 0.9
    assert bt["caught_before_confirmation"] >= 1 and bt["median_lead_hours"] is not None
    assert len(bt["series"]) == 14 and bt["series"][-1]["mules_flagged_so_far"] >= 1


def test_backtest_needs_labels(client):
    classic_ring(client)
    r = client.post("/network/backtest", json={"days": 3})
    assert r.status_code == 409 and "labels" in r.json()["detail"]


def test_analyst_outcomes_become_labels(client):
    classic_ring(client)
    ring = client.get("/network/rings").json()[0]
    client.post(f"/network/rings/{ring['id']}/actions", json={"action": "confirm", "actor": "sup"})
    summary = client.get("/network/labels/summary").json()
    assert summary["by_label"]["mule"]["analyst:sup"] == 4


def test_learning_lowers_noisy_rules_with_guardrails(client):
    client.post("/network/simulate", json={"seed": 42, "customers": 300, "rings": 5})
    out = client.post("/network/learning/refresh").json()
    learned = {r["code"]: r for r in out["updated"]}
    assert learned["FAN_IN"]["learned"] < learned["FAN_IN"]["prior"], "fan-in fires on traders and ajo collectors"
    view = client.get("/network/learning").json()
    assert view["applied"]["FAN_IN"]["multiplier"] < 1
    # Guardrail: after learning, no account is flagged on a single behavioural signal.
    a = cache.analysis
    for acc, score in a.scores.items():
        if score >= get_settings().network_flag_threshold:
            sigs = a.signals[acc]
            assert len(sigs) >= 2 or any(s.code in eng.LEARNING_EXEMPT for s in sigs), sigs
    e = client.get("/network/evaluation").json()
    assert e["victims_flagged"] == 0 and e["precision"] >= 0.9


def test_weighted_guardrail_unit():
    cfg = Config(30, timedelta(minutes=120), 0.6, 0.85, 0.5, "999", weights={"LOW_KYC_HIGH_VALUE": 4.9, "FAN_IN": 0.1})
    raised = _weighted(eng.Signal("LOW_KYC_HIGH_VALUE", 0.15, ""), cfg)
    assert raised.weight == 0.30, "multiplier capped at 2x"
    big = _weighted(eng.Signal("LOW_KYC_HIGH_VALUE", 0.45, ""), cfg)
    assert big.weight == 0.55, "raised weight stops below the flag line"
    low = _weighted(eng.Signal("FAN_IN", 0.40, ""), cfg)
    assert low.weight == 0.10, "multiplier floored at 0.25x"
    ex = _weighted(eng.Signal("VICTIM_COMPLAINT", 0.6, ""), Config(30, timedelta(minutes=120), 0.6, 0.85, 0.5, "999", weights={"VICTIM_COMPLAINT": 0.1}))
    assert ex.weight == 0.6


def test_shadow_mode_is_reported_on_decisions(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "network_mode", "shadow")
    classic_ring(client)
    d = client.post("/network/decide", json={"source": {"bank_code": "999", "account_no": "C1"},
                                              "beneficiary": {"bank_code": "999", "account_no": "V1"}, "amount_kobo": 100}).json()
    assert d["mode"] == "shadow" and d["decision"] == "HOLD"


# ---------------------------------------------------------------- step 3: deploy


def _full_scores(a):
    s = get_settings()
    with SqlUnitOfWork() as uow:
        cfg = engine_config(s, a.weights)
        scores, _, _ = score_all(uow.graph.load_snapshot(cfg, a.snapshot.at), cfg)
        return scores


def test_incremental_matches_full_recompute(client):
    client.post("/network/simulate", json={"seed": 11, "customers": 300, "rings": 4})
    rng = random.Random(5)
    for batch_no in range(3):
        a = cache.analysis
        accs = [v for v in a.snapshot.accounts.values() if not v.is_merchant]
        mules = [v for v in accs if v.label == "mule"]
        t = now() - timedelta(hours=2, minutes=batch_no * 10)
        batch = []
        for i in range(30):
            x, y = rng.sample(accs, 2)
            batch.append({"reference": f"B{batch_no}-{i}", "ts": (t + timedelta(seconds=i * 7)).isoformat(),
                          "src": {"bank_code": x.bank_code, "account_no": x.account_no},
                          "dst": {"bank_code": y.bank_code, "account_no": y.account_no},
                          "amount_kobo": rng.choice([10_000, 200_000, 700_000]) * 100, "channel": "nip"})
        m = rng.choice(mules)
        # A burst into a known mule, then out again.
        for i in range(7):
            x = rng.choice(accs)
            batch.append({"reference": f"B{batch_no}-M{i}", "ts": (t + timedelta(minutes=5 + i)).isoformat(),
                          "src": {"bank_code": x.bank_code, "account_no": x.account_no},
                          "dst": {"bank_code": m.bank_code, "account_no": m.account_no}, "amount_kobo": 250_000_00, "channel": "mobile"})
        r = client.post("/network/ingest", json={"transfers": batch})
        assert r.status_code == 200
        inc = cache.analysis
        assert inc.mode == "incremental"
        full = _full_scores(inc)
        diff = {k for k in set(full) | set(inc.scores) if abs(full.get(k, 0) - inc.scores.get(k, 0)) > 1e-9}
        assert not diff, f"batch {batch_no}: {len(diff)} accounts differ"


def test_non_append_changes_force_a_full_rebuild(client):
    classic_ring(client)
    client.post("/network/analyse")
    with SqlUnitOfWork() as uow:
        acc = uow.session.query(Account).filter_by(account_no="C1").one()
        # A change no rebuild has seen yet.
        acc.status = "cleared"
        uow.commit()
    t = now() - timedelta(minutes=5)
    client.post("/network/ingest", json={"transfers": [{"reference": "AFTER-REPORT", "ts": t.isoformat(),
                                                        "src": {"bank_code": "999", "account_no": "V1"},
                                                        "dst": {"bank_code": "999", "account_no": "V2"}, "amount_kobo": 100_00}]})
    assert cache.analysis.mode == "full"
    assert cache.analysis.scores.get(by_id_c1(cache.analysis), 1) < 0.6, "the status change is now reflected"


def test_another_worker_sees_stale_data(client):
    classic_ring(client)
    with SqlUnitOfWork() as uow:
        worker2 = NetworkCache()
        worker2.run(uow)
        assert not worker2.is_stale(uow)
        client.post("/network/reports", json={"bank_code": "999", "account_no": "X1", "kind": "victim_complaint"})
        uow.session.expire_all()
        assert worker2.is_stale(uow), "a write through worker 1 must make worker 2's cache stale"
        worker2.get(uow)
        assert not worker2.is_stale(uow)


def test_migrations_upgrade_an_old_database(tmp_path):
    import sqlite3

    from sqlalchemy import create_engine, inspect

    from app.infrastructure.database import run_migrations

    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE customers (id VARCHAR(32) PRIMARY KEY, external_id VARCHAR(64), display_name VARCHAR(120), language VARCHAR(8), created_at DATETIME)")
    con.execute("INSERT INTO customers VALUES ('c1', NULL, 'Old Customer', 'en', '2026-01-01')")
    con.execute("CREATE TABLE verification_events (id VARCHAR(32) PRIMARY KEY, customer_id VARCHAR(32), continuous_session_id VARCHAR(32), "
                "context VARCHAR(64), modality VARCHAR(8), resolves_event_id VARCHAR(32), match_score FLOAT, spoof_score FLOAT, "
                "spoof_model VARCHAR(64), decision VARCHAR(16), reasons JSON, quality JSON, created_at DATETIME)")
    con.commit()
    con.close()
    e = create_engine(f"sqlite:///{path}")
    assert run_migrations(e) == run_migrations(e) == "0006_ring_numbers"
    insp = inspect(e)
    assert "duress" in {c["name"] for c in insp.get_columns("verification_events")}
    assert {"bank_daily_limit_kobo", "bank_synced_at"} <= {c["name"] for c in insp.get_columns("net_accounts")}
    assert insp.has_table("net_models") and insp.has_table("net_traces") and insp.has_table("net_import_jobs")
    with e.connect() as c:
        assert c.exec_driver_sql("select display_name from customers").scalar() == "Old Customer"


def test_role_permissions(client, monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "api_keys", "sys-key:system,app-key:app,ana-key:analyst,sup-key:supervisor")

    def call(method, path, key, **kw):
        return client.request(method, path, headers={"X-API-Key": key} if key else {}, **kw).status_code

    assert call("GET", "/health", None) == 200
    assert call("GET", "/network/rings", None) == 401
    assert call("GET", "/network/rings", "nope") == 401
    assert call("GET", "/network/rings", "app-key") == 403, "the customer app cannot browse rings"
    assert call("GET", "/network/rings", "ana-key") == 200
    assert call("POST", "/network/ingest", "ana-key", json={}) == 403, "analysts cannot inject data"
    assert call("POST", "/network/ingest", "sys-key", json={}) == 200
    assert call("POST", "/network/simulate", "ana-key", json={}) == 403
    assert call("POST", "/network/decide", "app-key", json={}) == 422, "app may call decide (body invalid here)"
    assert call("POST", "/network/decide", "ana-key", json={}) == 403
    assert call("POST", "/iris/verify", "ana-key") == 403, "staff cannot run customer biometrics"
    assert call("GET", "/customers", "ana-key") == 200

    monkeypatch.setattr(st, "api_keys", "")
    classic_ring(client)
    rid = client.get("/network/rings").json()[0]["id"]
    monkeypatch.setattr(st, "api_keys", "ana-key:analyst,sup-key:supervisor")
    r = client.post(f"/network/rings/{rid}/actions", json={"action": "confirm", "actor": "a"}, headers={"X-API-Key": "ana-key"})
    assert r.status_code == 403 and "supervisor" in r.json()["detail"]
    r = client.post(f"/network/rings/{rid}/actions", json={"action": "watchlist_24h", "actor": "a"}, headers={"X-API-Key": "ana-key"})
    assert r.status_code == 200
    r = client.post(f"/network/rings/{rid}/actions", json={"action": "confirm", "actor": "s"}, headers={"X-API-Key": "sup-key"})
    assert r.status_code == 200


def by_id_c1(a):
    return next(k for k, v in a.snapshot.accounts.items() if v.account_no == "C1")
