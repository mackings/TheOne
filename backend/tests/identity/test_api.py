from helpers.voice import ALICE, BOB, enrol, synth_voice, verify, wav_bytes


def test_health(client):
    h = client.get("/health").json()
    assert h["status"] == "ok" and h["embedder"] == "fake"


def test_enrol_and_verify_same_and_other_speaker(client):
    alice = enrol(client, "Alice", ALICE)
    same = verify(client, alice, ALICE)
    other = verify(client, alice, BOB)
    assert same["match_score"] > other["match_score"]
    assert same["decision"] == "ACCEPT", same
    assert other["decision"] != "ACCEPT", other
    events = client.get(f"/customers/{alice}/events").json()
    assert len(events) == 2


def test_bad_quality_sample_is_rejected_with_guidance(client):
    cid = client.post("/customers", json={"display_name": "Quiet", "language": "pcm"}).json()["id"]
    s = client.post("/enrolment/sessions", json={"customer_id": cid}).json()
    import numpy as np

    r = client.post(
        f"/enrolment/sessions/{s['id']}/samples",
        data={"step_index": 0},
        files={"audio": ("a.wav", wav_bytes(np.zeros(16000 * 2, dtype=np.float32)), "audio/wav")},
    )
    body = r.json()
    assert r.status_code == 200 and not body["accepted"]
    assert body["message"].startswith("Make we try am again")
    assert client.get(f"/enrolment/sessions/{s['id']}").json()["next_step"] == 0


def test_complete_requires_all_samples(client):
    cid = client.post("/customers", json={"display_name": "Partial"}).json()["id"]
    s = client.post("/enrolment/sessions", json={"customer_id": cid}).json()
    assert client.post(f"/enrolment/sessions/{s['id']}/complete").status_code == 409


def test_verify_without_template(client):
    cid = client.post("/customers", json={"display_name": "NoTpl"}).json()["id"]
    r = client.post(
        "/verify", data={"customer_id": cid}, files={"audio": ("v.wav", wav_bytes(synth_voice(150)), "audio/wav")}
    )
    assert r.status_code == 409


def test_high_risk_context_in_reasons(client):
    cid = enrol(client, "Risky", ALICE)
    out = verify(client, cid, ALICE, context="high_value_transfer")
    assert any("high-risk context" in r for r in out["reasons"])


def test_continuous_session_degrades_on_speaker_change(client):
    cid = enrol(client, "Cont", ALICE)
    cs = client.post("/verify/continuous/sessions", json={"customer_id": cid}).json()
    url = f"/verify/continuous/sessions/{cs['id']}/chunks"
    for i in range(3):
        r = client.post(url, files={"audio": ("c.wav", wav_bytes(synth_voice(seed=10 + i, seconds=2.0, **ALICE)), "audio/wav")})
        assert r.status_code == 200, r.text
    assert r.json()["status"] == "active" and r.json()["last_decision"] == "ACCEPT"
    for i in range(5):
        r = client.post(url, files={"audio": ("c.wav", wav_bytes(synth_voice(seed=20 + i, seconds=2.0, **BOB)), "audio/wav")})
    body = r.json()
    assert body["status"] == "degraded", body
    assert body["chunk_count"] == 8
    ended = client.post(f"/verify/continuous/sessions/{cs['id']}/end").json()
    assert ended["status"] == "ended"


def test_revoke_template(client):
    cid = enrol(client, "Revoke", ALICE)
    assert client.delete(f"/customers/{cid}/template").status_code == 204
    assert client.get(f"/customers/{cid}").json()["enrolled"] is False


def test_api_key_enforced_when_configured(monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "api_key", "secret-123")
    try:
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as c:
            assert c.get("/health").status_code == 200
            assert c.get("/customers").status_code == 401
            assert c.get("/customers", headers={"X-API-Key": "wrong"}).status_code == 401
            assert c.get("/customers", headers={"X-API-Key": "secret-123"}).status_code == 200
    finally:
        monkeypatch.setattr(settings, "api_key", None)


def test_device_step_up_links_to_voice_event(client):
    cid = enrol(client, "Device Dan", ALICE)
    voice = verify(client, cid, ALICE, context="change_beneficiary")
    r = client.post("/stepup/device", json={"customer_id": cid, "method": "fingerprint", "resolves_event_id": voice["event_id"], "device_model": "Pixel 8"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision"] == "ACCEPT" and body["resolves_event_id"] == voice["event_id"]
    assert any("unattested" in x for x in body["reasons"])
    assert client.post("/stepup/device", json={"customer_id": cid, "method": "retina"}).status_code == 422
    events = client.get(f"/customers/{cid}/events").json()
    assert any(e["modality"] == "device" and e["context"] == "change_beneficiary" for e in events)
