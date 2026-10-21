"""Request-scoped dependencies: the unit of work and the external systems the use cases are given."""
from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.infrastructure.unit_of_work import SqlUnitOfWork
from app.network.application.ports import BankConnector, NibssConnector
from app.network.infrastructure import bank, nibss


def new_uow() -> SqlUnitOfWork:
    """A unit of work outside a request, for background tasks."""
    return SqlUnitOfWork()


def get_uow() -> Iterator[SqlUnitOfWork]:
    with SqlUnitOfWork() as uow:
        yield uow


def get_bank(s: Settings = Depends(get_settings)) -> BankConnector:
    return bank.get_connector(s)


def get_nibss(s: Settings = Depends(get_settings)) -> NibssConnector:
    return nibss.get_connector(s)


def get_role(request: Request) -> str:
    return getattr(request.state, "role", "admin")
