"""SQLAlchemy implementations of the identity repositories."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.identity.domain.entities import ContinuousSession, Customer, DeviceKey, EnrolmentSession, StepUpChallenge, VerificationEvent
from app.identity.infrastructure import tables as t


class _Repository:
    entity: type

    def __init__(self, session: Session):
        self.s = session

    def get(self, key):
        return self.s.get(self.entity, key)

    def add(self, obj):
        self.s.add(obj)
        return obj


class CustomerRepository(_Repository):
    entity = Customer

    def by_external_id(self, external_id: str) -> Customer | None:
        return self.s.scalar(select(Customer).where(t.customers.c.external_id == external_id))

    def newest_first(self) -> list[Customer]:
        return list(self.s.scalars(select(Customer).order_by(t.customers.c.created_at.desc())))


class EnrolmentRepository(_Repository):
    entity = EnrolmentSession


class DeviceKeyRepository(_Repository):
    entity = DeviceKey

    def active_for(self, customer_id: str) -> list[DeviceKey]:
        c = t.device_keys.c
        return list(self.s.scalars(select(DeviceKey).where(c.customer_id == customer_id, c.revoked_at.is_(None))))


class ChallengeRepository(_Repository):
    entity = StepUpChallenge


class ContinuousSessionRepository(_Repository):
    entity = ContinuousSession

    def open_for(self, customer_id: str) -> list[ContinuousSession]:
        c = t.continuous_sessions.c
        return list(self.s.scalars(select(ContinuousSession).where(c.customer_id == customer_id, c.status != "ended")))


class VerificationEventRepository(_Repository):
    entity = VerificationEvent

    def for_customer(self, customer_id: str, limit: int) -> list[VerificationEvent]:
        c = t.verification_events.c
        return list(self.s.scalars(select(VerificationEvent).where(c.customer_id == customer_id)
                                   .order_by(c.created_at.desc()).limit(limit)))
