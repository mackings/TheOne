"""Shared shapes for the analysis: transfers as edges, signals, account views, the snapshot and the result."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

CASH_CHANNELS = {"pos", "atm", "agent", "statement_cash"}
# Statement transfers carry a date but no time, so "fast" means within a day for them.
DAY_CHANNELS = {"statement", "statement_cash"}
DAY = timedelta(days=1)
# Amounts are in kobo: 100 kobo to the naira.
NAIRA = 100


def naira(kobo: int) -> str:
    return f"₦{kobo / NAIRA:,.0f}"


@dataclass(frozen=True)
class Edge:
    ts: datetime
    src: str
    dst: str
    amount: int
    channel: str
    ref: str


@dataclass
class Signal:
    code: str
    weight: float
    reason: str
    evidence: dict = field(default_factory=dict)


@dataclass
class AccountView:
    id: str
    bank_code: str
    account_no: str
    name: str
    home: bool
    opened_at: datetime | None
    kyc_tier: int | None
    is_merchant: bool
    customer_id: str | None
    status: str
    status_until: datetime | None
    label: str | None

    @property
    def display(self) -> str:
        return f"{self.name or 'Unknown'} · {self.bank_code}/{self.account_no}"


@dataclass
class Config:
    window_days: int
    fast_window: timedelta
    flag: float
    hold: float
    ring_min: float
    home_bank: str
    weights: dict[str, float] = field(default_factory=dict)


@dataclass
class Snapshot:
    """The transfer graph for one time window. Identifiers (phones, devices, BVNs) are indexed both
    ways, and prior_last holds each account's last activity before the window."""

    at: datetime
    window_start: datetime
    accounts: dict[str, AccountView]
    ins: dict[str, list[Edge]]
    outs: dict[str, list[Edge]]
    ident_members: dict[str, set[str]]
    ident_info: dict[str, tuple[str, str]]
    acct_idents: dict[str, set[str]]
    reports: dict[str, list[str]]
    prior_last: dict[str, datetime]
    transfer_count: int


@dataclass
class RingResult:
    """A ring found by the analysis. `number` is the ring number people quote, e.g. 100004."""

    id: str
    status: str
    score: float
    members: list[str]
    summary: dict
    number: int | None = None


@dataclass
class Analysis:
    """Scores, signals and rings for every account. `base` keeps the first-pass signals so new transfers
    can be applied incrementally; `mode` says whether this was a full or an incremental run."""

    version: int
    computed_at: datetime
    duration_ms: float
    snapshot: Snapshot
    scores: dict[str, float]
    signals: dict[str, list[Signal]]
    rings: list[RingResult]
    ring_of: dict[str, str]
    base: dict[str, list[Signal]] = field(default_factory=dict)
    db_version: int = 0
    local_appends: int = 0
    local_others: int = 0
    loaded_at: datetime | None = None
    mode: str = "full"
    weights: dict[str, float] = field(default_factory=dict)

    def risk(self, account_id: str) -> float:
        return self.scores.get(account_id, 0.0)


def signal_dicts(sigs: list[Signal]) -> list[dict]:
    return [asdict(s) for s in sorted(sigs, key=lambda s: -s.weight)]
