"""Customers and their consent: create, list, and revoke biometric templates."""
from __future__ import annotations

from app.core.errors import Conflict, Invalid, NotFound
from app.core.timeutil import now
from app.identity.application.ports import IdentityUnitOfWork
from app.identity.domain.entities import Customer, VerificationEvent
from app.identity.domain.prompts import LANGUAGES


def load(uow: IdentityUnitOfWork, customer_id: str) -> Customer:
    c = uow.customers.get(customer_id)
    if not c:
        raise NotFound("customer not found")
    return c


def create(uow: IdentityUnitOfWork, display_name: str, external_id: str | None, language: str) -> Customer:
    if language not in LANGUAGES:
        raise Invalid(f"unsupported language; choose one of {sorted(LANGUAGES)}")
    if external_id and uow.customers.by_external_id(external_id):
        raise Conflict("external_id already exists")
    c = uow.customers.add(Customer(display_name=display_name, external_id=external_id, language=language))
    uow.commit()
    return c


def all_customers(uow: IdentityUnitOfWork) -> list[Customer]:
    return uow.customers.newest_first()


def events(uow: IdentityUnitOfWork, customer_id: str, limit: int) -> list[VerificationEvent]:
    load(uow, customer_id)
    return uow.events.for_customer(customer_id, limit)


def revoke_voice(uow: IdentityUnitOfWork, customer_id: str) -> None:
    """Withdrawing consent deletes the voice template and ends any live call verification."""
    c = load(uow, customer_id)
    if c.template:
        uow.delete(c.template)
    for s in uow.continuous_sessions.open_for(customer_id):
        s.status, s.ended_at = "ended", now()
    uow.commit()


def revoke_iris(uow: IdentityUnitOfWork, customer_id: str) -> None:
    c = load(uow, customer_id)
    if c.iris_template:
        uow.delete(c.iris_template)
        uow.commit()


def revoke_iris_duress(uow: IdentityUnitOfWork, customer_id: str) -> None:
    c = load(uow, customer_id)
    if c.iris_duress:
        uow.delete(c.iris_duress)
        uow.commit()
