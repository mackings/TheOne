"""One database transaction, with every module's repositories bound to it."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.identity.infrastructure import repositories as identity
from app.infrastructure.database import SessionLocal
from app.network.infrastructure import data_version
from app.network.infrastructure import repositories as network


class SqlUnitOfWork:
    def __init__(self, session: Session | None = None):
        self.session = session or SessionLocal()
        s = self.session
        self.customers = identity.CustomerRepository(s)
        self.enrolments = identity.EnrolmentRepository(s)
        self.device_keys = identity.DeviceKeyRepository(s)
        self.challenges = identity.ChallengeRepository(s)
        self.continuous_sessions = identity.ContinuousSessionRepository(s)
        self.events = identity.VerificationEventRepository(s)
        self.accounts = network.AccountRepository(s)
        self.identifiers = network.IdentifierRepository(s)
        self.transfers = network.TransferRepository(s)
        self.statements = network.StatementRepository(s)
        self.reports = network.ReportRepository(s)
        self.rings = network.RingRepository(s)
        self.decisions = network.DecisionRepository(s)
        self.actions = network.ActionRepository(s)
        self.safe_limits = network.SafeLimitRepository(s)
        self.alerts = network.AlertRepository(s)
        self.labels = network.LabelRepository(s)
        self.bank_actions = network.BankActionRepository(s)
        self.weights = network.TypologyWeightRepository(s)
        self.models = network.ModelRepository(s)
        self.traces = network.TraceRepository(s)
        self.import_jobs = network.ImportJobRepository(s)
        self.graph = network.SqlGraphReader(s)

    def add(self, entity: Any) -> None:
        self.session.add(entity)

    def delete(self, entity: Any) -> None:
        self.session.delete(entity)

    def flush(self) -> None:
        self.session.flush()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def close(self) -> None:
        self.session.close()

    def data_version(self) -> int:
        return data_version.read(self.session)

    def wipe_network(self) -> None:
        network.wipe_network(self.session)

    def __enter__(self) -> SqlUnitOfWork:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
