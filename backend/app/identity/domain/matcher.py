"""Voice template construction and scoring."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def l2_normalize(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    a, b = l2_normalize(a), l2_normalize(b)
    return float(np.clip(np.dot(a, b), -1.0, 1.0))


@dataclass
class TemplateBuild:
    template: np.ndarray
    consistency: float
    min_pairwise: float
    sample_count: int


def build_template(embeddings: list[np.ndarray]) -> TemplateBuild:
    if not embeddings:
        raise ValueError("no embeddings")
    embs = np.stack([l2_normalize(e) for e in embeddings])
    template = l2_normalize(embs.mean(axis=0))
    n = len(embs)
    if n == 1:
        return TemplateBuild(template, 1.0, 1.0, 1)
    sims = embs @ embs.T
    iu = np.triu_indices(n, k=1)
    pair = sims[iu]
    return TemplateBuild(template, float(pair.mean()), float(pair.min()), n)


def update_template(old: np.ndarray, new: np.ndarray, weight: float = 0.1) -> np.ndarray:
    """Adaptive enrolment: blend a verified sample into the template."""
    return l2_normalize((1 - weight) * l2_normalize(old) + weight * l2_normalize(new))
