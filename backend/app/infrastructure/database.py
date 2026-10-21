"""Database engine, sessions and the mapper registry that maps domain entities onto tables."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import DateTime, MetaData, create_engine
from sqlalchemy.orm import registry, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings
from app.core.timeutil import UTC

metadata = MetaData()
mapper_registry = registry(metadata=metadata)


class UtcDateTime(TypeDecorator):
    """Domain code only sees timezone-aware UTC datetimes; columns without a timezone store naive UTC."""

    impl = DateTime
    cache_ok = True

    def __init__(self, timezone: bool = False):
        super().__init__(timezone=timezone)
        self.aware = timezone

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return value if self.aware else value.replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def make_engine(url: str | None = None):
    url = url or get_settings().sqlalchemy_url
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
    return create_engine(url, **kwargs)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def register_tables() -> None:
    """Import every module's tables, which adds them to `metadata` and maps their entities."""
    import app.identity.infrastructure.tables  # noqa: F401
    import app.network.infrastructure.tables  # noqa: F401


def run_migrations(eng=None) -> str:
    """Bring the database to the latest schema with Alembic and return the head revision."""
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    with (eng or engine).begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    return ScriptDirectory.from_config(cfg).get_current_head()
