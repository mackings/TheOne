"""Iris recognition: segmentation, normalisation, log-Gabor iris code, Hamming matching.

This is a classic Daugman/Masek-style pipeline on visible-light images (webcam).
It demonstrates the full flow and gives real, measurable matching. Accuracy on
dark irises in visible light is limited: production deployments must use
near-infrared capture (branch kiosks, NIR-capable phones), where the same code
path applies with far better texture contrast.

Web capture sends a crop around the eye plus the iris circle found by the browser's
face-landmark model (a "hint"). The hint makes segmentation consistent frame to frame,
which matters more than anything else for visible-light matching. Without a hint (the
phone apps, older clients) the Haar-eye + Hough path below is used.

For dark irises in visible light the red channel carries the most texture, so the
iris code is computed from it; segmentation still uses the grey image.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from functools import lru_cache

import cv2
import numpy as np

# The iris is unrolled to a 48 x 360 sheet and encoded as 16 x 256 x 2 bits with a log-Gabor filter.
# Matching tolerates head tilt of about 14 degrees; enrolment keeps up to five agreeing codes.
POLAR_H, POLAR_W = 48, 360
CODE_H, CODE_W = 16, 256
WAVELENGTH = 22.0
SIGMA_F = 0.55
MAX_SHIFT = 10
MODEL_NAME = "iris-loggabor-v0"
MAX_TEMPLATES = 5


class IrisError(ValueError):
    pass


@dataclass
class Circle:
    cx: float
    cy: float
    r: float


@dataclass
class IrisQuality:
    eye_found: bool
    iris_found: bool
    focus: float
    iris_radius_px: float
    mask_coverage: float
    ok: bool
    issues: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class IrisCode:
    """Code bits and the mask of usable bits, with the pupil and iris circles found."""

    bits: np.ndarray
    mask: np.ndarray
    quality: IrisQuality
    circles: tuple[Circle, Circle] | None = None


@lru_cache
def _eye_cascade() -> cv2.CascadeClassifier:
    return cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")


def decode_image(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise IrisError("could not decode image")
    return img


def detect_eye(gray: np.ndarray) -> tuple[int, int, int, int] | None:
    """Largest eye box from the Haar cascade, or None."""
    h, w = gray.shape
    eyes = _eye_cascade().detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(max(24, w // 12),) * 2)
    if len(eyes) == 0:
        return None
    x, y, ew, eh = max(eyes, key=lambda e: e[2] * e[3])
    return int(x), int(y), int(ew), int(eh)


def _ring_mean(img: np.ndarray, c: Circle, r0: float, r1: float) -> float:
    h, w = img.shape
    yy, xx = np.ogrid[:h, :w]
    d = np.sqrt((xx - c.cx) ** 2 + (yy - c.cy) ** 2)
    sel = (d >= r0) & (d < r1)
    return float(img[sel].mean()) if sel.any() else 255.0


def find_iris(gray: np.ndarray) -> Circle | None:
    """Limbus (iris/sclera boundary): the Hough circle with the strongest dark-inside contrast."""
    h, w = gray.shape
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    min_r, max_r = max(10, int(min(h, w) * 0.08)), int(min(h, w) * 0.48)
    circles = cv2.HoughCircles(
        blur, cv2.HOUGH_GRADIENT, dp=1.2, minDist=min(h, w) / 4, param1=110, param2=28, minRadius=min_r, maxRadius=max_r
    )
    if circles is None:
        return None
    best, best_contrast = None, -1.0
    for cx, cy, r in circles[0][:8]:
        c = Circle(float(cx), float(cy), float(r))
        if c.cx - c.r < 0 or c.cy - c.r < 0 or c.cx + c.r > w or c.cy + c.r > h:
            continue
        contrast = _ring_mean(blur, c, c.r * 1.08, c.r * 1.35) - _ring_mean(blur, c, 0, c.r * 0.92)
        if contrast > best_contrast:
            best, best_contrast = c, contrast
    return best if best_contrast > 8 else None


def refine_iris(gray: np.ndarray, hint: Circle) -> Circle:
    """Snap the browser's iris circle to the nearest strong limbus edge, staying close to the hint."""
    h, w = gray.shape
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    lo, hi = max(8, int(hint.r * 0.85)), max(10, int(hint.r * 1.15))
    circles = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT, dp=1.0, minDist=max(4, hint.r), param1=90, param2=18,
                               minRadius=lo, maxRadius=hi)
    best, best_score = hint, -1.0
    if circles is not None:
        for cx, cy, r in circles[0][:12]:
            if np.hypot(cx - hint.cx, cy - hint.cy) > 0.2 * hint.r:
                continue
            c = Circle(float(cx), float(cy), float(r))
            contrast = _ring_mean(blur, c, c.r * 1.08, c.r * 1.3) - _ring_mean(blur, c, c.r * 0.5, c.r * 0.92)
            if contrast > best_score:
                best, best_score = c, contrast
    # Keep the hint when nothing clearly better was found: the landmark model is consistent frame to frame.
    return best if best_score > 6 else hint


def find_pupil(gray: np.ndarray, iris: Circle) -> Circle:
    """Darkest blob inside the iris; falls back to a concentric circle at 0.35 r."""
    h, w = gray.shape
    yy, xx = np.ogrid[:h, :w]
    inside = (xx - iris.cx) ** 2 + (yy - iris.cy) ** 2 <= (iris.r * 0.8) ** 2
    vals = gray[inside]
    if vals.size == 0:
        return Circle(iris.cx, iris.cy, iris.r * 0.35)
    thresh = np.percentile(vals, 18)
    mask = ((gray <= thresh) & inside).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for cnt in contours:
        (cx, cy), r = cv2.minEnclosingCircle(cnt)
        if not 0.15 * iris.r <= r <= 0.65 * iris.r:
            continue
        if np.hypot(cx - iris.cx, cy - iris.cy) > 0.3 * iris.r:
            continue
        area_ratio = cv2.contourArea(cnt) / (np.pi * r * r + 1e-6)
        if area_ratio < 0.5:
            continue
        if best is None or r > best.r:
            best = Circle(float(cx), float(cy), float(r))
    return best or Circle(iris.cx, iris.cy, iris.r * 0.35)


def normalise(gray: np.ndarray, pupil: Circle, iris: Circle) -> tuple[np.ndarray, np.ndarray]:
    """Daugman rubber-sheet: sample the annulus between pupil and limbus into a polar strip."""
    theta = np.linspace(0, 2 * np.pi, POLAR_W, endpoint=False, dtype=np.float32)
    rho = np.linspace(0.05, 0.95, POLAR_H, dtype=np.float32)[:, None]
    xp, yp = pupil.cx + pupil.r * np.cos(theta), pupil.cy + pupil.r * np.sin(theta)
    xi, yi = iris.cx + iris.r * np.cos(theta), iris.cy + iris.r * np.sin(theta)
    map_x = ((1 - rho) * xp[None, :] + rho * xi[None, :]).astype(np.float32)
    map_y = ((1 - rho) * yp[None, :] + rho * yi[None, :]).astype(np.float32)
    polar = cv2.remap(gray, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    h, w = gray.shape
    valid = (map_x >= 0) & (map_x < w - 1) & (map_y >= 0) & (map_y < h - 1)
    specular = polar >= 235
    # Eyelid heuristic: outer 40% of the annulus around the 12 and 6 o'clock directions.
    ang = np.degrees(theta)[None, :]
    near_lids = ((np.abs(ang - 90) <= 35) | (np.abs(ang - 270) <= 35)) & (rho > 0.6)
    mask = valid & ~specular & ~near_lids
    return polar.astype(np.float32), mask


@lru_cache
def _log_gabor(width: int) -> np.ndarray:
    f = np.fft.rfftfreq(width)
    f0 = 1.0 / WAVELENGTH
    with np.errstate(divide="ignore"):
        g = np.exp(-(np.log(f / f0) ** 2) / (2 * np.log(SIGMA_F) ** 2))
    g[0] = 0.0
    return g


def encode(polar: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Phase-quantised 1D log-Gabor response along the angular direction."""
    small = cv2.resize(polar, (CODE_W, CODE_H), interpolation=cv2.INTER_AREA)
    msmall = cv2.resize(mask.astype(np.float32), (CODE_W, CODE_H), interpolation=cv2.INTER_AREA) > 0.6
    small = small - small.mean(axis=1, keepdims=True)
    spec = np.fft.rfft(small, axis=1) * _log_gabor(CODE_W)[None, :]
    resp = np.fft.irfft(spec, n=CODE_W, axis=1)
    # Quadrature pair from the analytic signal via Hilbert transform.
    analytic = np.fft.ifft(np.fft.fft(resp, axis=1) * _hilbert_mask(CODE_W)[None, :], axis=1)
    bits = np.stack([analytic.real > 0, analytic.imag > 0], axis=-1)
    # Suppress bits where the response is too weak to be meaningful.
    weak = np.abs(analytic) < 1e-3
    return bits, msmall & ~weak


@lru_cache
def _hilbert_mask(n: int) -> np.ndarray:
    h = np.zeros(n)
    h[0] = 1
    if n % 2 == 0:
        h[n // 2] = 1
        h[1 : n // 2] = 2
    else:
        h[1 : (n + 1) // 2] = 2
    return h


def hamming(a: IrisCode | tuple, b: IrisCode | tuple) -> tuple[float, int, float]:
    """Min normalised Hamming distance over rotational shifts. Returns (hd, best_shift, valid_fraction)."""
    ba, ma = (a.bits, a.mask) if isinstance(a, IrisCode) else a
    bb, mb = (b.bits, b.mask) if isinstance(b, IrisCode) else b
    best, best_shift, best_valid = 1.0, 0, 0.0
    for s in range(-MAX_SHIFT, MAX_SHIFT + 1):
        rb, rm = np.roll(bb, s, axis=1), np.roll(mb, s, axis=1)
        valid = ma & rm
        n = int(valid.sum())
        if n < 0.15 * CODE_H * CODE_W:
            continue
        hd = float(((ba ^ rb) & valid[..., None]).sum() / (2 * n))
        if hd < best:
            best, best_shift, best_valid = hd, s, n / (CODE_H * CODE_W)
    return best, best_shift, best_valid


def focus_measure(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _texture(img: np.ndarray) -> np.ndarray:
    """Red channel with local contrast enhancement: the richest iris texture in visible light."""
    return cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(img[:, :, 2])


def _iris_focus(gray: np.ndarray, iris: Circle) -> float:
    h, w = gray.shape
    r = int(iris.r)
    x0, y0 = max(0, int(iris.cx) - r), max(0, int(iris.cy) - r)
    patch = gray[y0 : int(iris.cy) + r, x0 : int(iris.cx) + r]
    return focus_measure(patch) if patch.size else 0.0


def process_frame(img: np.ndarray, *, min_focus: float, min_radius: int, hint: Circle | None = None) -> IrisCode:
    """Full pipeline on one frame. Always returns a code object; check `.quality.ok`.
    `hint` is the iris circle (in this image's pixels) from the browser's landmark model."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    issues: list[str] = []
    if hint is not None and hint.r > 4:
        box, x0, y0, roi, troi = True, 0, 0, gray, _texture(img)
        iris = refine_iris(gray, hint)
    else:
        box = detect_eye(gray)
        if box:
            x, y, w, h = box
            pad = int(0.25 * w)
            x0, y0 = max(0, x - pad), max(0, y - pad)
            roi = gray[y0 : y + h + pad, x0 : x + w + pad]
        else:
            x0, y0, roi = 0, 0, gray
        iris = find_iris(roi)
        if iris is None and box is not None:
            x0, y0, roi = 0, 0, gray
            iris = find_iris(roi)
        troi = _texture(img)[y0 : y0 + roi.shape[0], x0 : x0 + roi.shape[1]]
    if iris is None:
        issues.append("no iris found; centre one eye in the guide and move closer")
        q = IrisQuality(box is not None, False, round(focus_measure(roi), 1), 0.0, 0.0, False, issues)
        return IrisCode(np.zeros((CODE_H, CODE_W, 2), bool), np.zeros((CODE_H, CODE_W), bool), q)
    focus = _iris_focus(roi, iris)
    pupil = find_pupil(roi, iris)
    polar, mask = normalise(troi, pupil, iris)
    bits, cmask = encode(polar, mask)
    coverage = float(cmask.mean())
    if focus < min_focus:
        issues.append("image is blurry; hold still and let the camera focus")
    if iris.r < min_radius:
        issues.append(f"iris too small ({iris.r:.0f}px); move closer to the camera")
    if coverage < 0.35:
        issues.append("too much of the iris is covered; open the eye wider")
    q = IrisQuality(bool(box), True, round(focus, 1), round(iris.r, 1), round(coverage, 3), not issues, issues)
    off = Circle(pupil.cx + x0, pupil.cy + y0, pupil.r), Circle(iris.cx + x0, iris.cy + y0, iris.r)
    return IrisCode(bits, cmask, q, off)


def liveness(frames: list[np.ndarray], found: list[bool]) -> dict:
    """Blink detection across a burst plus a static-image check. Demo-grade."""
    n = len(frames)
    detected = sum(found)
    blink = False
    first = next((i for i, f in enumerate(found) if f), None)
    last = next((i for i in range(n - 1, -1, -1) if found[i]), None)
    if first is not None and last is not None and last > first:
        blink = any(not found[i] for i in range(first + 1, last))
    diffs = []
    for a, b in zip(frames[:-1], frames[1:]):
        ga, gb = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
        if ga.shape == gb.shape:
            diffs.append(float(np.abs(ga.astype(np.int16) - gb.astype(np.int16)).mean()))
    motion = float(np.mean(diffs)) if diffs else 0.0
    static = n > 1 and motion < 0.5
    score = 0.9 if static else (0.0 if blink else 0.5)
    return {
        "frames": n,
        "frames_with_eye": detected,
        "blink_detected": blink,
        "mean_motion": round(motion, 2),
        "static_image": static,
        "score": score,
        "model": "blink-liveness-v0",
    }


def pack(code: IrisCode) -> tuple[bytes, bytes]:
    return np.packbits(code.bits.ravel()).tobytes(), np.packbits(code.mask.ravel()).tobytes()


def unpack(bits_b: bytes, mask_b: bytes) -> tuple[np.ndarray, np.ndarray]:
    bits = np.unpackbits(np.frombuffer(bits_b, np.uint8))[: CODE_H * CODE_W * 2].reshape(CODE_H, CODE_W, 2).astype(bool)
    mask = np.unpackbits(np.frombuffer(mask_b, np.uint8))[: CODE_H * CODE_W].reshape(CODE_H, CODE_W).astype(bool)
    return bits, mask


def pick_template(codes: list[IrisCode]) -> tuple[IrisCode, float]:
    """Medoid code (lowest mean HD to the others) and mean pairwise HD as a consistency measure."""
    if len(codes) == 1:
        return codes[0], 0.0
    n = len(codes)
    D = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            D[i, j] = D[j, i] = hamming(codes[i], codes[j])[0]
    i = int(np.argmin(D.sum(axis=1)))
    return codes[i], float(D[np.triu_indices(n, 1)].mean())


# A template can hold several codes from the same enrolment. Stored as a 4-byte header
# (b"IC2" + count) followed by the packed codes; a blob without the header is one code.

_MAGIC = b"IC2"


def pack_many(codes: list) -> tuple[bytes, bytes]:
    parts = [pack(c) if isinstance(c, IrisCode) else (np.packbits(c[0].ravel()).tobytes(), np.packbits(c[1].ravel()).tobytes())
             for c in codes]
    n = bytes([len(parts)])
    return _MAGIC + n + b"".join(p[0] for p in parts), _MAGIC + n + b"".join(p[1] for p in parts)


def unpack_many(bits_b: bytes, mask_b: bytes) -> list[tuple[np.ndarray, np.ndarray]]:
    if not bits_b.startswith(_MAGIC):
        return [unpack(bits_b, mask_b)]
    n = bits_b[3]
    bl, ml = (CODE_H * CODE_W * 2 + 7) // 8, (CODE_H * CODE_W + 7) // 8
    bb, mb = bits_b[4:], mask_b[4:]
    return [unpack(bb[i * bl : (i + 1) * bl], mb[i * ml : (i + 1) * ml]) for i in range(n)]


def pick_templates(codes: list[IrisCode], k: int = MAX_TEMPLATES) -> tuple[list[IrisCode], float]:
    """The k codes that agree with each other best (medoid plus its nearest neighbours), and
    their mean pairwise distance. A high value means the frames did not capture the same pattern."""
    if len(codes) == 1:
        return codes, 0.0
    n = len(codes)
    D = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            D[i, j] = D[j, i] = hamming(codes[i], codes[j])[0]
    medoid = int(np.argmin(D.sum(axis=1)))
    order = [medoid] + [j for j in np.argsort(D[medoid]) if j != medoid]
    keep = order[: max(2, min(k, n))]
    sub_d = [D[a, b] for ia, a in enumerate(keep) for b in keep[ia + 1 :]]
    return [codes[i] for i in keep], float(np.mean(sub_d))


def best_match(templates: list[tuple[np.ndarray, np.ndarray]], codes: list[IrisCode]) -> tuple[float | None, list[float | None]]:
    """Best distance of each usable frame to any stored code; overall best over good frames."""
    per: list[float | None] = []
    for c in codes:
        if not c.quality.iris_found:
            per.append(None)
            continue
        per.append(round(min(hamming(t, (c.bits, c.mask))[0] for t in templates), 4))
    good = [h for h, c in zip(per, codes) if h is not None and c.quality.ok]
    return (min(good) if good else None), per


class OpenCvIrisEngine:
    model_name = MODEL_NAME
    decode_image = staticmethod(decode_image)
    liveness = staticmethod(liveness)
    pick_templates = staticmethod(pick_templates)
    best_match = staticmethod(best_match)
    pack_many = staticmethod(pack_many)
    unpack_many = staticmethod(unpack_many)

    def process_frame(self, frame: np.ndarray, *, min_focus: float, min_radius: int,
                      hint: tuple[float, float, float] | None) -> IrisCode:
        return process_frame(frame, min_focus=min_focus, min_radius=min_radius, hint=Circle(*hint) if hint else None)
