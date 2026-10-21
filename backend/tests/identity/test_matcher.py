import numpy as np

from app.identity.domain.matcher import build_template, cosine, update_template


def test_cosine_bounds():
    a = np.array([1.0, 0.0])
    assert cosine(a, a) == 1.0
    assert abs(cosine(a, np.array([0.0, 1.0]))) < 1e-6


def test_template_consistency():
    base = np.random.default_rng(1).standard_normal(64)
    embs = [base + 0.05 * np.random.default_rng(i).standard_normal(64) for i in range(3)]
    b = build_template(embs)
    assert b.sample_count == 3
    assert b.consistency > 0.95
    assert abs(np.linalg.norm(b.template) - 1) < 1e-5


def test_update_template_moves_toward_new():
    old = np.array([1.0, 0.0])
    new = np.array([0.0, 1.0])
    upd = update_template(old, new, 0.5)
    assert cosine(upd, new) > cosine(old, new)
