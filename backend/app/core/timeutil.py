from __future__ import annotations

import uuid
from datetime import datetime, timezone

UTC = timezone.utc


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid.uuid4().hex


def utc(dt: datetime | None) -> datetime | None:
    """Times from outside (requests, bank files) without a timezone are taken as UTC."""
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
