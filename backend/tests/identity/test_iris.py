import cv2
import numpy as np
import pytest

from app.identity.infrastructure import iris_engine as irislib
from helpers.iris import burst, jpeg, synth_eye


def code(img):
    return irislib.process_frame(img, min_focus=5.0, min_radius=20)


def test_segmentation_finds_iris_and_pupil():
    c = code(synth_eye(1))
    assert c.quality.iris_found, c.quality
    pupil, iris = c.circles
    assert abs(iris.r - 70) < 8 and abs(pupil.r - 26) < 8
    assert np.hypot(iris.cx - 320, iris.cy - 240) < 6


def test_same_identity_matches_and_different_does_not():
    a1, a2 = code(synth_eye(1)), code(synth_eye(1, shift=(9, -5)))
    b = code(synth_eye(2))
    hd_same = irislib.hamming(a1, a2)[0]
    hd_diff = irislib.hamming(a1, b)[0]
    assert hd_same < 0.25, hd_same
    assert hd_diff > 0.38, hd_diff


def test_rotation_tolerance():
    img = synth_eye(3)
    M = cv2.getRotationMatrix2D((320, 240), 8, 1.0)
    rot = cv2.warpAffine(img, M, (640, 480), borderValue=(170, 170, 170))
    assert irislib.hamming(code(img), code(rot))[0] < 0.30


def test_pack_unpack_roundtrip():
    c = code(synth_eye(4))
    bits, mask = irislib.unpack(*irislib.pack(c))
    assert np.array_equal(bits, c.bits) and np.array_equal(mask, c.mask)


def test_liveness_blink_and_static():
    frames = [synth_eye(1, shift=(i, 0)) for i in range(3)] + [synth_eye(1, closed=True)] + [synth_eye(1, shift=(i, 1)) for i in range(3)]
    found = [code(f).quality.iris_found for f in frames]
    live = irislib.liveness(frames, found)
    assert live["blink_detected"] and not live["static_image"]
    static = irislib.liveness([synth_eye(1)] * 5, [True] * 5)
    assert static["static_image"] and static["score"] >= 0.9


@pytest.fixture
def lenient_iris(monkeypatch):
    from app.core.config import get_settings

    st = get_settings()
    monkeypatch.setattr(st, "iris_min_focus", 5.0)
    monkeypatch.setattr(st, "iris_min_radius_px", 20)


def test_iris_api_enrol_verify_and_stepup(client, lenient_iris):
    cid = client.post("/customers", json={"display_name": "Iris Ada"}).json()["id"]
    r = client.post("/iris/enrol", data={"customer_id": cid}, files=burst(11))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["template"]["sample_count"] >= 3 and body["liveness"]["blink_detected"]
    assert client.get(f"/customers/{cid}").json()["iris_enrolled"] is True

    same = client.post("/iris/verify", data={"customer_id": cid}, files=burst(11)).json()
    assert same["decision"] == "ACCEPT", same
    other = client.post("/iris/verify", data={"customer_id": cid}, files=burst(12)).json()
    assert other["decision"] == "REJECT", other

    # Step-up resolution links to a voice event.
    from helpers.voice import synth_voice, wav_bytes

    s = client.post("/enrolment/sessions", json={"customer_id": cid}).json()
    for i in range(s["required_samples"]):
        client.post(f"/enrolment/sessions/{s['id']}/samples", data={"step_index": i},
                    files={"audio": ("a.wav", wav_bytes(synth_voice(140.0, seed=i, formant=700.0)), "audio/wav")})
    client.post(f"/enrolment/sessions/{s['id']}/complete")
    voice = client.post("/verify", data={"customer_id": cid, "context": "high_value_transfer"},
                        files={"audio": ("v.wav", wav_bytes(synth_voice(140.0, seed=9, formant=700.0)), "audio/wav")}).json()
    stepup = client.post("/iris/verify", data={"customer_id": cid, "resolves_event_id": voice["event_id"]}, files=burst(11)).json()
    assert stepup["resolves_event_id"] == voice["event_id"] and stepup["decision"] == "ACCEPT"
    events = client.get(f"/customers/{cid}/events").json()
    assert any(e["modality"] == "iris" and e["resolves_event_id"] == voice["event_id"] for e in events)

    static = client.post("/iris/verify", data={"customer_id": cid}, files=[("images", (f"f{i}.jpg", jpeg(synth_eye(11)), "image/jpeg")) for i in range(4)]).json()
    assert static["decision"] == "REJECT" and static["liveness"]["static_image"]

    assert client.delete(f"/customers/{cid}/iris-template").status_code == 204
    assert client.get(f"/customers/{cid}").json()["iris_enrolled"] is False


def test_iris_verify_without_template(client):
    cid = client.post("/customers", json={"display_name": "NoIris"}).json()["id"]
    r = client.post("/iris/verify", data={"customer_id": cid}, files=burst(5))
    assert r.status_code == 409
