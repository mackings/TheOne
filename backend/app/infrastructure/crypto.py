"""Encryption of biometric templates at rest (NDPA 2023): raw embeddings never leave the process unencrypted."""
from __future__ import annotations

import logging
from functools import lru_cache

import numpy as np
from cryptography.fernet import Fernet

from app.core.config import BACKEND_DIR, get_settings

log = logging.getLogger(__name__)
DEV_KEY_FILE = BACKEND_DIR / ".dev_template_key"


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().template_encryption_key
    if not key:
        if DEV_KEY_FILE.exists():
            key = DEV_KEY_FILE.read_text().strip()
        else:
            key = Fernet.generate_key().decode()
            DEV_KEY_FILE.write_text(key)
            DEV_KEY_FILE.chmod(0o600)
        log.warning("TEMPLATE_ENCRYPTION_KEY not set; using development key at %s", DEV_KEY_FILE)
    return Fernet(key.encode() if isinstance(key, str) else key)


class FernetCipher:
    def encrypt_vector(self, vec: np.ndarray) -> bytes:
        return _fernet().encrypt(np.asarray(vec, dtype=np.float32).tobytes())

    def decrypt_vector(self, blob: bytes, dim: int) -> np.ndarray:
        vec = np.frombuffer(_fernet().decrypt(blob), dtype=np.float32)
        if vec.shape[0] != dim:
            raise ValueError(f"template dimension mismatch: expected {dim}, got {vec.shape[0]}")
        return vec.copy()

    def encrypt_bytes(self, raw: bytes) -> bytes:
        return _fernet().encrypt(raw)

    def decrypt_bytes(self, blob: bytes) -> bytes:
        return _fernet().decrypt(blob)


cipher = FernetCipher()
