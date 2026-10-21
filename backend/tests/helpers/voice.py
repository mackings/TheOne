"""Synthetic voices and the enrol/verify calls the voice tests share."""
import io

import numpy as np
import soundfile as sf

SR = 16000


def synth_voice(f0: float, seconds: float = 3.0, seed: int = 0, formant: float = 800.0) -> np.ndarray:
    """Harmonic 'voice' with a formant peak, syllable-like on/off envelope and a low noise floor."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(SR * seconds)) / SR
    sig = np.zeros_like(t)
    for h in range(1, 25):
        f = f0 * h
        if f > 7000:
            break
        amp = 1.0 / h * np.exp(-((f - formant) ** 2) / (2 * 400.0**2)) + 0.05 / h
        sig += amp * np.sin(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi))
    env = ((t % 0.55) < 0.4).astype(np.float32)
    env = np.convolve(env, np.ones(400) / 400, mode="same")
    # Aspiration/breath noise shaped by the envelope so the spectrum is not a bare harmonic comb.
    breath = rng.standard_normal(t.size)
    breath = np.convolve(breath, np.array([1, -0.9]), mode="same")
    breath *= 0.08 * (1 + 0.5 * np.sin(2 * np.pi * 1.3 * t))
    x = (0.3 * sig / np.max(np.abs(sig)) + breath) * env + 0.003 * rng.standard_normal(t.size)
    return x.astype(np.float32)


def wav_bytes(x: np.ndarray, sr: int = SR) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, x, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


ALICE = dict(f0=140.0, formant=700.0)
BOB = dict(f0=230.0, formant=1400.0)


def enrol(client, name, voice, language="en"):
    c = client.post("/customers", json={"display_name": name, "language": language}).json()
    s = client.post("/enrolment/sessions", json={"customer_id": c["id"]}).json()
    assert s["status"] == "in_progress" and len(s["prompts"]) == s["required_samples"]
    assert name in s["guide"]["welcome"]
    for i in range(s["required_samples"]):
        r = client.post(
            f"/enrolment/sessions/{s['id']}/samples",
            data={"step_index": i},
            files={"audio": ("a.wav", wav_bytes(synth_voice(seed=i, **voice)), "audio/wav")},
        )
        assert r.status_code == 200, r.text
        assert r.json()["accepted"], r.json()
    done = client.post(f"/enrolment/sessions/{s['id']}/complete")
    assert done.status_code == 200, done.text
    assert done.json()["template"]["sample_count"] == s["required_samples"]
    return c["id"]


def verify(client, cid, voice, seed=99, context=None):
    data = {"customer_id": cid}
    if context:
        data["context"] = context
    r = client.post(
        "/verify",
        data=data,
        files={"audio": ("v.wav", wav_bytes(synth_voice(seed=seed, **voice)), "audio/wav")},
    )
    assert r.status_code == 200, r.text
    return r.json()
