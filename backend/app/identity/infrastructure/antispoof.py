"""Presentation-attack / synthetic-voice scoring.

IMPORTANT: the shipped scorer is a signal-statistics BASELINE, not a trained
anti-spoofing model. It flags obvious cases (band-limited playback, unnaturally
flat spectra, zero-noise synthetic silence) and is meant to be replaced by a
trained detector such as AASIST or a commercial engine via the same Protocol.
Its score should feed a step-up decision, never a hard reject on its own.
"""
from __future__ import annotations

import numpy as np

from app.identity.application.ports import SpoofResult


class BaselineAntiSpoof:
    name = "baseline-heuristic-v0"

    def score(self, audio: np.ndarray, sample_rate: int) -> SpoofResult:
        x = np.asarray(audio, dtype=np.float32)
        if x.size < sample_rate // 2:
            return SpoofResult(0.5, self.name, {"insufficient_audio": 1.0})

        frame, hop = 512, 256
        n = 1 + (x.size - frame) // hop
        idx = np.arange(frame)[None, :] + hop * np.arange(n)[:, None]
        frames = x[idx] * np.hanning(frame)
        spec = np.abs(np.fft.rfft(frames, axis=1)) + 1e-9
        freqs = np.fft.rfftfreq(frame, 1 / sample_rate)
        power = spec**2
        frame_energy = power.sum(axis=1)
        voiced = frame_energy > np.percentile(frame_energy, 40)

        # 1. High-band energy ratio: telephone/loudspeaker replay and many TTS
        #    vocoders roll off above ~4 kHz.
        hi = power[:, freqs >= 4000].sum(axis=1)
        hi_ratio = float(np.mean(hi[voiced] / frame_energy[voiced])) if voiced.any() else 0.0
        s_highband = float(np.clip((0.02 - hi_ratio) / 0.02, 0, 1))

        # 2. Spectral flatness variability: natural speech varies a lot between
        #    frames; vocoded speech tends to be more uniform.
        geo = np.exp(np.mean(np.log(spec), axis=1))
        arith = np.mean(spec, axis=1)
        flatness = geo / arith
        flat_std = float(np.std(flatness[voiced])) if voiced.any() else 0.0
        s_flatness = float(np.clip((0.08 - flat_std) / 0.08, 0, 1))

        # 3. Noise floor: real recordings have a non-zero, varying noise floor
        #    during pauses; synthetic audio often has digital silence.
        quiet = ~voiced
        if quiet.any():
            floor_db = 10 * np.log10(frame_energy[quiet].mean() + 1e-12)
            s_floor = float(np.clip((-75 - floor_db) / 20, 0, 1))
        else:
            s_floor = 0.0

        score = float(np.clip(0.45 * s_highband + 0.35 * s_flatness + 0.20 * s_floor, 0, 1))
        return SpoofResult(
            score=round(score, 3),
            model=self.name,
            signals={
                "high_band_ratio": round(hi_ratio, 4),
                "flatness_std": round(flat_std, 4),
                "s_highband": round(s_highband, 3),
                "s_flatness": round(s_flatness, 3),
                "s_noise_floor": round(s_floor, 3),
            },
        )
