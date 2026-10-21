"""Synthetic eye images for testing the iris pipeline: each seed is a different iris texture,
and nuisance parameters imitate webcam capture (position, scale, rotation, blur, noise, light,
eyelid cover, JPEG) plus error in the browser's iris circle."""
from __future__ import annotations

import cv2
import numpy as np

from app.identity.infrastructure.iris_engine import Circle


def _texture_fn(seed: int):
    """Iris texture for one synthetic person: radial streaks and rings, plus dark crypts."""
    rng = np.random.default_rng(seed)
    k = 40
    fa = rng.integers(3, 40, k)
    fr = rng.uniform(0.5, 6.0, k)
    ph = rng.uniform(0, 2 * np.pi, k)
    amp = rng.uniform(0.3, 1.0, k)
    blobs = rng.uniform(0, 1, (25, 3))

    def f(theta, rho):
        v = np.zeros_like(theta)
        for i in range(k):
            v += amp[i] * np.sin(fa[i] * theta + fr[i] * 2 * np.pi * rho + ph[i])
        v /= np.sqrt(k)
        for t, r, s in blobs:
            dt = np.angle(np.exp(1j * (theta - t * 2 * np.pi)))
            v -= 1.6 * np.exp(-((dt * 3) ** 2 + ((rho - (0.15 + 0.8 * r)) * 8) ** 2) / (0.05 + 0.1 * s))
        return v

    return f


def synth_eye(seed: int, *, size: int = 360, radius: float = 60, dx: float = 0, dy: float = 0, rot_deg: float = 0,
              blur: float = 0, noise: float = 0, light: float = 1.0, lid: float = 0.0, jpeg: int = 0,
              hint_err: float = 0.0, rng: np.random.Generator | None = None) -> tuple[np.ndarray, Circle]:
    rng = rng or np.random.default_rng(0)
    cx, cy = size / 2 + dx, size / 2 + dy
    yy, xx = np.mgrid[:size, :size].astype(np.float32)
    d = np.hypot(xx - cx, yy - cy)
    theta = np.arctan2(yy - cy, xx - cx) - np.radians(rot_deg)
    pr = radius * 0.38
    rho = np.clip((d - pr) / (radius - pr), 0, 1)
    tex = _texture_fn(seed)(theta, rho)
    # Skin and sclera, a brown iris (BGR) with its texture strongest in red, the pupil, a dark limbal
    # ring, an optional upper eyelid and a specular highlight.
    img = np.zeros((size, size, 3), np.float32)
    img[:] = (205, 210, 225)
    iris = d <= radius
    base = np.array([40, 62, 95], np.float32)
    for ch, gain in zip(range(3), (6, 10, 22)):
        img[..., ch] = np.where(iris, base[ch] + gain * tex, img[..., ch])
    img[d <= pr] = (14, 14, 18)
    ring = (d > radius - 2) & (d <= radius + 2)
    img[ring] = img[ring] * 0.6
    if lid > 0:
        img[yy < cy - radius * (1 - lid)] = (150, 170, 200)
    hx, hy = cx - radius * 0.3, cy - radius * 0.3
    img[np.hypot(xx - hx, yy - hy) < radius * 0.06] = 250
    img *= light
    if blur:
        img = cv2.GaussianBlur(img, (0, 0), blur)
    if noise:
        img += rng.normal(0, noise, img.shape).astype(np.float32)
    out = np.clip(img, 0, 255).astype(np.uint8)
    if jpeg:
        ok, enc = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, jpeg])
        out = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    e = hint_err
    hint = Circle(cx + rng.normal(0, e * radius), cy + rng.normal(0, e * radius), radius * (1 + rng.normal(0, e)))
    return out, hint


def capture(seed: int, n: int, rng: np.random.Generator, radius: float = 50, hard: bool = False):
    """A burst of n frames of one eye with realistic frame-to-frame variation."""
    frames = []
    for _ in range(n):
        frames.append(synth_eye(
            seed, radius=radius * rng.uniform(0.95, 1.05), dx=rng.normal(0, 6), dy=rng.normal(0, 6),
            rot_deg=rng.normal(0, 4), blur=rng.uniform(0.6, 1.6 if hard else 1.0), noise=rng.uniform(3, 9 if hard else 5),
            light=rng.uniform(0.75, 1.15), lid=rng.uniform(0, 0.35 if hard else 0.2), jpeg=int(rng.integers(85, 96)),
            hint_err=0.03 if hard else 0.02, rng=rng))
    return frames
