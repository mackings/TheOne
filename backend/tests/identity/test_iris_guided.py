"""Guided web capture: the browser sends an eye crop plus the iris circle it tracked. Synthetic
eyes stand in for a webcam; each seed is a different iris."""
import json

import cv2
import numpy as np
import pytest

from app.identity.infrastructure import iris_engine as irislib
from helpers.webcam_eyes import capture


def burst(frames):
    files = [("images", (f"f{i}.png", cv2.imencode(".png", img)[1].tobytes(), "image/png")) for i, (img, _) in enumerate(frames)]
    hints = json.dumps([{"cx": h.cx, "cy": h.cy, "r": h.r} for _, h in frames])
    return files, hints


@pytest.fixture
def customer(client):
    return client.post("/customers", json={"display_name": "Iris Guided", "language": "en"}).json()["id"]


def enrol(client, cid, frames, **extra):
    files, hints = burst(frames)
    return client.post("/iris/enrol", data={"customer_id": cid, "hints": hints, "blink": "true", **extra}, files=files)


def verify(client, cid, frames):
    files, hints = burst(frames)
    return client.post("/iris/verify", data={"customer_id": cid, "hints": hints, "blink": "true"}, files=files).json()


def test_same_eye_accepted_other_eye_rejected(client, customer):
    rng = np.random.default_rng(1)
    r = enrol(client, customer, capture(3, 8, rng))
    assert r.status_code == 200, r.text
    t = r.json()["template"]
    assert t["sample_count"] >= 3 and t["consistency_hd"] <= 0.31 and 0.28 <= t["quality"]["accept_hd"] <= 0.34
    ok = verify(client, customer, capture(3, 8, rng))
    assert ok["decision"] == "ACCEPT", ok["reasons"]
    bad = verify(client, customer, capture(77, 8, rng))
    assert bad["decision"] == "REJECT" and bad["hamming_distance"] > bad["accept_hd"]


def test_frames_of_different_eyes_cannot_be_enrolled(client, customer):
    rng = np.random.default_rng(2)
    mixed = capture(4, 3, rng) + capture(5, 3, rng) + capture(6, 2, rng)
    r = enrol(client, customer, mixed)
    assert r.status_code == 422 and "same iris pattern" in r.json()["detail"]


def test_too_small_iris_is_refused_with_guidance(client, customer):
    r = enrol(client, customer, capture(8, 8, np.random.default_rng(3), radius=24))
    assert r.status_code == 422 and "move closer" in r.json()["detail"]


def test_old_single_code_templates_still_verify():
    rng = np.random.default_rng(4)
    codes = [irislib.process_frame(f, min_focus=1, min_radius=10, hint=h) for f, h in capture(9, 4, rng)]
    single = irislib.pack(codes[0])
    assert len(irislib.unpack_many(*single)) == 1
    many = irislib.pack_many(codes[:3])
    assert len(irislib.unpack_many(*many)) == 3
