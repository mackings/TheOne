"""SQLAlchemy implementations of the network repositories."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Generic, TypeVar

from sqlalchemy import delete, func, insert, select, tuple_
from sqlalchemy.orm import Session

from app.network.application.ports import AccountKey
from app.network.domain.engine import AccountView, Config, Edge, Snapshot
from app.network.domain.entities import (Account, AccountIdentifier, AnalystAction, Alert, BankAction, Identifier,
                                         ImportJob, Label, Report, Ring, SafeLimit, StatementEntry, Trace, TrainedModel,
                                         Transfer, TransferDecision, TypologyWeight)
from app.network.infrastructure import tables as t

T = TypeVar("T")
CHUNK = 500


def _chunks(items: list, size: int = CHUNK):
    for i in range(0, len(items), size):
        yield items[i:i + size]


class _Repository(Generic[T]):
    entity: type

    def __init__(self, session: Session):
        self.s = session

    def get(self, key) -> T | None:
        return self.s.get(self.entity, key)

    def add(self, obj: T) -> T:
        self.s.add(obj)
        return obj


def mark_bulk_change(session: Session) -> None:
    """Bulk statements bypass the ORM events, so record the change for every worker's cache."""
    session.info["net_graph_change"] = "other"


class AccountRepository(_Repository[Account]):
    entity = Account

    def find(self, bank_code: str, account_no: str) -> Account | None:
        return self.s.scalar(select(Account).where(t.accounts.c.bank_code == bank_code, t.accounts.c.account_no == account_no))

    def by_customer(self, customer_id: str) -> list[Account]:
        return list(self.s.scalars(select(Account).where(t.accounts.c.customer_id == customer_id)))

    def with_status(self, statuses: set[str]) -> list[Account]:
        return list(self.s.scalars(select(Account).where(t.accounts.c.status.in_(statuses))))

    def with_synthetic_label(self) -> list[Account]:
        return list(self.s.scalars(select(Account).where(t.accounts.c.synthetic_label.is_not(None))))

    def bank_codes_for(self, account_no: str) -> list[str]:
        return list(self.s.scalars(select(t.accounts.c.bank_code).where(t.accounts.c.account_no == account_no)))

    def statement_stubs(self, account_no: str) -> list[Account]:
        return list(self.s.scalars(select(Account).where(t.accounts.c.account_no == account_no,
                                                         t.accounts.c.bank_code.like("ST-%"))))

    def count(self) -> int:
        return self.s.scalar(select(func.count()).select_from(t.accounts)) or 0

    def ids_for(self, keys: list[AccountKey]) -> dict[AccountKey, str]:
        ids: dict[AccountKey, str] = {}
        c = t.accounts.c
        for part in _chunks(keys, 400):
            for aid, bc, no in self.s.execute(select(c.id, c.bank_code, c.account_no).where(tuple_(c.bank_code, c.account_no).in_(part))):
                ids[(bc, no)] = aid
        return ids

    def insert_many(self, rows: list[dict]) -> None:
        if rows:
            self.s.execute(insert(t.accounts), rows)
            mark_bulk_change(self.s)


class IdentifierRepository(_Repository[Identifier]):
    entity = Identifier

    def find(self, kind: str, value_hash: str) -> Identifier | None:
        return self.s.scalar(select(Identifier).where(t.identifiers.c.kind == kind, t.identifiers.c.value_hash == value_hash))

    def is_linked(self, account_id: str, identifier_id: str) -> bool:
        return self.s.get(AccountIdentifier, (account_id, identifier_id)) is not None

    def link(self, account_id: str, identifier_id: str, first_seen: datetime | None = None) -> None:
        link = AccountIdentifier(account_id=account_id, identifier_id=identifier_id)
        if first_seen is not None:
            link.first_seen = first_seen
        self.s.add(link)

    def links(self, account_id: str, kind: str) -> list[tuple[str, datetime]]:
        ai, i = t.account_identifiers.c, t.identifiers.c
        return [(x, y) for x, y in self.s.execute(
            select(ai.identifier_id, ai.first_seen).join(t.identifiers, i.id == ai.identifier_id)
            .where(ai.account_id == account_id, i.kind == kind))]


class TransferRepository(_Repository[Transfer]):
    entity = Transfer

    def insert_many(self, rows: list[dict]) -> None:
        if rows:
            self.s.execute(insert(t.transfers), rows)
            mark_bulk_change(self.s)

    def existing_references(self, references: list[str]) -> set[str]:
        found: set[str] = set()
        for part in _chunks(references, 400):
            found |= set(self.s.scalars(select(t.transfers.c.reference).where(t.transfers.c.reference.in_(part))))
        return found

    def count(self) -> int:
        return self.s.scalar(select(func.count()).select_from(t.transfers)) or 0

    def received_since(self, account_id: str, since: datetime) -> list[tuple[str, int]]:
        c = t.transfers.c
        return [(a, b) for a, b in self.s.execute(select(c.src_account_id, c.amount_kobo)
                                                    .where(c.dst_account_id == account_id, c.ts >= since))]

    def sent_between(self, account_id: str, since: datetime, until: datetime) -> list[tuple[datetime, str, int, str]]:
        c = t.transfers.c
        return [tuple(r) for r in self.s.execute(select(c.ts, c.dst_account_id, c.amount_kobo, c.reference)
                                                 .where(c.src_account_id == account_id, c.ts >= since, c.ts <= until))]

    def first_received_since(self, since: datetime) -> dict[str, datetime]:
        c = t.transfers.c
        first: dict[str, datetime] = {}
        for dst, ts in self.s.execute(select(c.dst_account_id, c.ts).where(c.ts >= since)):
            if dst not in first or ts < first[dst]:
                first[dst] = ts
        return first


class StatementRepository(_Repository[StatementEntry]):
    entity = StatementEntry

    def exists(self, account_id: str, reference: str) -> bool:
        c = t.statement_entries.c
        return self.s.scalar(select(c.id).where(c.account_id == account_id, c.reference == reference)) is not None

    def debits_between(self, account_id: str, since: datetime, until: datetime) -> list[tuple[datetime, int, str]]:
        c = t.statement_entries.c
        return [tuple(r) for r in self.s.execute(select(c.ts, c.amount_kobo, c.reference).where(
            c.account_id == account_id, c.direction == "debit", c.ts >= since, c.ts <= until))]


class ReportRepository(_Repository[Report]):
    entity = Report

    def exists(self, account_id: str, kind: str) -> bool:
        c = t.reports.c
        return self.s.scalar(select(c.id).where(c.account_id == account_id, c.kind == kind)) is not None


class RingRepository(_Repository[Ring]):
    entity = Ring

    def active(self) -> list[Ring]:
        return list(self.s.scalars(select(Ring).where(t.rings.c.status.in_(["open", "confirmed", "dismissed"]))))

    def max_case_no(self) -> int | None:
        return self.s.scalar(select(func.max(t.rings.c.case_no)))

    def id_for_number(self, number: int) -> str | None:
        return self.s.scalar(select(t.rings.c.id).where(t.rings.c.case_no == number))


class DecisionRepository(_Repository[TransferDecision]):
    entity = TransferDecision

    def by_reference(self, reference: str) -> TransferDecision | None:
        return self.s.scalar(select(TransferDecision).where(t.decisions.c.reference == reference))

    def resolved_by(self, event_id: str, other_than: str) -> TransferDecision | None:
        c = t.decisions.c
        return self.s.scalar(select(TransferDecision).where(c.resolved_by_event_id == event_id, c.id != other_than))

    def newest(self, limit: int) -> list[TransferDecision]:
        return list(self.s.scalars(select(TransferDecision).order_by(t.decisions.c.created_at.desc()).limit(limit)))

    def approved_since(self, account_id: str, since: datetime) -> list[tuple[str, int]]:
        c = t.decisions.c
        return [(a, b) for a, b in self.s.execute(select(c.dst_account_id, c.amount_kobo).where(
            c.src_account_id == account_id, c.created_at >= since, c.status.in_(["allowed", "released"])))]

    def recent_contexts(self, account_id: str, limit: int) -> list[dict | None]:
        c = t.decisions.c
        return list(self.s.scalars(select(c.context).where(c.src_account_id == account_id)
                                   .order_by(c.created_at.desc()).limit(limit)))

    def stopped_to(self, account_ids: list[str], limit: int) -> list[TransferDecision]:
        """Payments held on their way to these accounts, or blocked by an analyst; newest first."""
        if not account_ids:
            return []
        c = t.decisions.c
        return list(self.s.scalars(select(TransferDecision).where(
            c.dst_account_id.in_(account_ids), (c.decision == "HOLD") | (c.status == "blocked"))
            .order_by(c.created_at.desc()).limit(limit)))

    def count(self) -> int:
        return self.s.scalar(select(func.count()).select_from(t.decisions)) or 0


class ActionRepository(_Repository[AnalystAction]):
    entity = AnalystAction

    def for_ring(self, ring_id: str) -> list[AnalystAction]:
        return list(self.s.scalars(select(AnalystAction).where(t.actions.c.ring_id == ring_id).order_by(t.actions.c.created_at)))


class SafeLimitRepository(_Repository[SafeLimit]):
    entity = SafeLimit


class AlertRepository(_Repository[Alert]):
    entity = Alert

    def newest(self, open_only: bool, limit: int) -> list[Alert]:
        q = select(Alert).order_by(t.alerts.c.created_at.desc()).limit(limit)
        if open_only:
            q = q.where(t.alerts.c.acknowledged_at.is_(None))
        return list(self.s.scalars(q))

    def open_count(self) -> int:
        return self.s.scalar(select(func.count()).select_from(t.alerts).where(t.alerts.c.acknowledged_at.is_(None))) or 0


class LabelRepository(_Repository[Label]):
    entity = Label

    def all(self) -> list[Label]:
        return list(self.s.scalars(select(Label)))


class BankActionRepository(_Repository[BankAction]):
    entity = BankAction

    def newest(self, status: str | None, limit: int) -> list[BankAction]:
        q = select(BankAction).order_by(t.bank_actions.c.created_at.desc()).limit(limit)
        if status:
            q = q.where(t.bank_actions.c.status == status)
        return list(self.s.scalars(q))

    def for_account(self, account_id: str, kind: str, statuses: set[str]) -> list[BankAction]:
        c = t.bank_actions.c
        return list(self.s.scalars(select(BankAction).where(c.account_id == account_id, c.kind == kind, c.status.in_(statuses))))


class TypologyWeightRepository(_Repository[TypologyWeight]):
    entity = TypologyWeight

    def all(self) -> list[TypologyWeight]:
        return list(self.s.scalars(select(TypologyWeight)))

    def replace_all(self, weights: list[TypologyWeight]) -> None:
        self.s.execute(delete(t.typology_weights))
        self.s.add_all(weights)


class ModelRepository(_Repository[TrainedModel]):
    entity = TrainedModel


class TraceRepository(_Repository[Trace]):
    entity = Trace

    def for_ring(self, ring_id: str) -> list[Trace]:
        return list(self.s.scalars(select(Trace).where(t.traces.c.ring_id == ring_id).order_by(t.traces.c.created_at)))


class ImportJobRepository(_Repository[ImportJob]):
    entity = ImportJob

    def newest(self, limit: int) -> list[ImportJob]:
        return list(self.s.scalars(select(ImportJob).order_by(t.import_jobs.c.created_at.desc()).limit(limit)))


def _view(a: Account, cfg: Config, at: datetime) -> AccountView:
    return AccountView(id=a.id, bank_code=a.bank_code, account_no=a.account_no, name=a.holder_name,
                       home=a.bank_code == cfg.home_bank, opened_at=a.opened_at, kyc_tier=a.kyc_tier,
                       is_merchant=a.is_merchant, customer_id=a.customer_id, status=a.effective_status(at),
                       status_until=a.status_until, label=a.synthetic_label)


def _bvn_link(snap: Snapshot, a: Account) -> None:
    """A BVN shared across accounts is an identifier link too: one person, several accounts."""
    key = "bvn:" + a.bvn_hash
    snap.ident_members.setdefault(key, set()).add(a.id)
    snap.acct_idents.setdefault(a.id, set()).add(key)
    snap.ident_info.setdefault(key, ("bvn", "BVN …" + a.bvn_hash[-4:]))


class SqlGraphReader:
    def __init__(self, session: Session):
        self.s = session

    def load_snapshot(self, cfg: Config, at: datetime) -> Snapshot:
        start = at - timedelta(days=cfg.window_days)
        tc = t.transfers.c
        accounts_rows = list(self.s.scalars(select(Account)))
        rows = self.s.execute(select(tc.ts, tc.src_account_id, tc.dst_account_id, tc.amount_kobo, tc.channel, tc.reference)
                              .where(tc.ts >= start, tc.ts <= at).order_by(tc.ts)).all()
        ins: dict[str, list[Edge]] = defaultdict(list)
        outs: dict[str, list[Edge]] = defaultdict(list)
        for ts, src, dst, amt, ch, ref in rows:
            e = Edge(ts, src, dst, int(amt), ch, ref)
            outs[src].append(e)
            ins[dst].append(e)
        prior_last: dict[str, datetime] = {}
        for col in (tc.src_account_id, tc.dst_account_id):
            for acc, last in self.s.execute(select(col, func.max(tc.ts)).where(tc.ts < start).group_by(col)):
                if acc not in prior_last or last > prior_last[acc]:
                    prior_last[acc] = last
        snap = Snapshot(at=at, window_start=start, accounts={a.id: _view(a, cfg, at) for a in accounts_rows}, ins=ins,
                        outs=outs, ident_members=defaultdict(set), ident_info={}, acct_idents=defaultdict(set),
                        reports=defaultdict(list), prior_last=prior_last, transfer_count=len(rows))
        ai = t.account_identifiers.c
        for acc, ident in self.s.execute(select(ai.account_id, ai.identifier_id)):
            snap.ident_members[ident].add(acc)
            snap.acct_idents[acc].add(ident)
        snap.ident_info.update({i.id: (i.kind, i.masked) for i in self.s.scalars(select(Identifier))})
        for a in accounts_rows:
            if a.bvn_hash:
                _bvn_link(snap, a)
        for acc, kind in self.s.execute(select(t.reports.c.account_id, t.reports.c.kind)):
            snap.reports[acc].append(kind)
        return snap

    def reload_accounts(self, snap: Snapshot, account_ids: set[str], cfg: Config) -> None:
        ai = t.account_identifiers.c
        for part in _chunks(list(account_ids)):
            for acc in self.s.scalars(select(Account).where(t.accounts.c.id.in_(part))):
                snap.accounts[acc.id] = _view(acc, cfg, snap.at)
                if acc.bvn_hash:
                    _bvn_link(snap, acc)
            for acc_id, ident in self.s.execute(select(ai.account_id, ai.identifier_id).where(ai.account_id.in_(part))):
                snap.ident_members.setdefault(ident, set()).add(acc_id)
                snap.acct_idents.setdefault(acc_id, set()).add(ident)
                if ident not in snap.ident_info and (rec := self.s.get(Identifier, ident)):
                    snap.ident_info[ident] = (rec.kind, rec.masked)

    def transfers_by_reference(self, references: list[str]) -> list[Edge]:
        tc = t.transfers.c
        edges = []
        for part in _chunks(references):
            for ts, src, dst, amt, ch, ref in self.s.execute(
                    select(tc.ts, tc.src_account_id, tc.dst_account_id, tc.amount_kobo, tc.channel, tc.reference)
                    .where(tc.reference.in_(part))):
                edges.append(Edge(ts, src, dst, int(amt), ch, ref))
        return edges


NETWORK_TABLES = (t.traces, t.models, t.bank_actions, t.labels, t.statement_entries, t.typology_weights, t.alerts,
                  t.safe_limits, t.actions, t.decisions, t.rings, t.reports, t.transfers, t.account_identifiers,
                  t.identifiers, t.accounts)


def wipe_network(session: Session) -> None:
    for table in NETWORK_TABLES:
        session.execute(delete(table))

