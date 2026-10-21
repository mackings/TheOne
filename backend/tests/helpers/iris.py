"""Simple synthetic eyes (a clean camera image) and frame bursts for the iris API tests."""
import cv2
import numpy as np


def synth_eye(identity: int, *, size=(480, 640), iris_r=70, pupil_r=26, shift=(0, 0), closed=False, noise=4.0):
    """Synthetic eye: skin background, white sclera ellipse, textured dark iris, black pupil."""
    rng = np.random.default_rng(identity)
    h, w = size
    img = np.full((h, w), 170, np.uint8)
    cx, cy = w // 2 + shift[0], h // 2 + shift[1]
    cv2.ellipse(img, (cx, cy), (int(iris_r * 2.2), int(iris_r * 1.3)), 0, 0, 360, 245, -1)
    if closed:
        cv2.ellipse(img, (cx, cy), (int(iris_r * 2.2), int(iris_r * 1.3)), 0, 0, 360, 160, -1)
        out = cv2.GaussianBlur(img, (5, 5), 0)
        return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
    yy, xx = np.mgrid[:h, :w]
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    ang = np.arctan2(yy - cy, xx - cx)
    rad = d / iris_r
    tex = np.zeros_like(d)
    # Texture unique to this synthetic identity.
    for k in range(6):
        tex += rng.uniform(0.5, 1.0) * np.sin(rng.integers(6, 40) * ang + rng.uniform(0, 6.28) + rng.integers(2, 9) * rad * 6.28)
    iris_px = np.clip(70 + 35 * tex / 6 * 3, 20, 140).astype(np.uint8)
    in_iris = d <= iris_r
    img[in_iris] = iris_px[in_iris]
    img[d <= pupil_r] = 8
    img = np.clip(img.astype(np.float32) + np.random.default_rng(identity * 7 + shift[0]).normal(0, noise, img.shape), 0, 255).astype(np.uint8)
    img = cv2.GaussianBlur(img, (3, 3), 0)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def jpeg(img) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    assert ok
    return buf.tobytes()


def burst(identity, n=5, blink=True):
    frames = [synth_eye(identity, shift=(i * 2, i % 2)) for i in range(n)]
    if blink:
        frames.insert(2, synth_eye(identity, closed=True))
    return [("images", (f"f{i}.jpg", jpeg(f), "image/jpeg")) for i, f in enumerate(frames)]
