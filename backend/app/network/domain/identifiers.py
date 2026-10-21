"""Identifier hashing. Raw phone numbers, device ids and BVNs are never stored: only an
HMAC (for matching across accounts) and a masked form (for analysts)."""
from __future__ import annotations

import hashlib
import hmac
import re

KINDS = {"phone", "device", "email", "address", "ip", "bvn"}


def normalise(kind: str, value: str) -> str:
    v = value.strip()
    if kind == "phone":
        d = re.sub(r"\D", "", v)
        if d.startswith("234") and len(d) == 13:
            d = "0" + d[3:]
        return d
    if kind in {"email", "device", "address", "ip"}:
        return re.sub(r"\s+", " ", v.lower())
    if kind == "bvn":
        return re.sub(r"\D", "", v)
    return v


def id_hash(kind: str, value: str, pepper: str) -> str:
    msg = f"{kind}:{normalise(kind, value)}".encode()
    return hmac.new(pepper.encode(), msg, hashlib.sha256).hexdigest()


def mask(kind: str, value: str) -> str:
    v = normalise(kind, value)
    if kind in {"phone", "bvn"}:
        return v[:4] + "*" * max(0, len(v) - 7) + v[-3:] if len(v) > 7 else "*" * len(v)
    if kind == "email" and "@" in v:
        user, dom = v.split("@", 1)
        return (user[:1] + "***@" + dom) if user else "***@" + dom
    if kind == "device":
        return v[:4] + "…" + v[-4:] if len(v) > 10 else v[:2] + "…"
    return v[:3] + "…" if len(v) > 3 else "…"
