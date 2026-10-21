"""The mule network's business objects. Plain Python: the infrastructure layer maps them onto tables."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.core.timeutil import new_id, now

WATCH_HOURS = 24
FIRST_RING_NO = 100001


@dataclass(eq=False)
class Account:
    bank_code: str
    account_no: str
    holder_name: str = ""
    bvn_hash: str | None = None
    opened_at: datetime | None = None
    kyc_tier: int | None = None
    is_merchant: bool = False
    customer_id: str | None = None
    status: str = "active"
    status_until: datetime | None = None
    synthetic_label: str | None = None
    bank_daily_limit_kobo: int | None = None
    bank_synced_at: datetime | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=now)

    def effective_status(self, at: datetime | None = None) -> str:
        """A watch-list entry lapses on its own; every other status stays until an analyst acts."""
        if self.status == "watchlist" and self.status_until is not None and self.status_until <= (at or now()):
            return "active"
        return self.status

    def watch(self, at: datetime, hours: int = WATCH_HOURS) -> None:
        if self.status != "confirmed_mule":
            self.status, self.status_until = "watchlist", at + timedelta(hours=hours)

    def confirm_mule(self) -> None:
        self.status, self.status_until = "confirmed_mule", None

    def clear(self) -> bool:
        if self.status == "confirmed_mule":
            return False
        self.status, self.status_until = "cleared", None
        return True

    def release(self) -> None:
        if self.status == "watchlist":
            self.status, self.status_until = "active", None


@dataclass(eq=False)
class Identifier:
    kind: str
    value_hash: str
    masked: str
    id: str = field(default_factory=new_id)


@dataclass(eq=False)
class AccountIdentifier:
    account_id: str
    identifier_id: str
    first_seen: datetime = field(default_factory=now)


@dataclass(eq=False)
class Transfer:
    reference: str
    ts: datetime
    src_account_id: str
    dst_account_id: str
    amount_kobo: int
    channel: str
    narration: str | None = None
    id: str = field(default_factory=new_id)


@dataclass(eq=False)
class Report:
    kind: str
    account_id: str
    transfer_reference: str | None = None
    note: str | None = None
    reporter: str | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=now)


@dataclass(eq=False)
class Ring:
    score: float
    member_ids: list
    summary: dict
    status: str = "open"
    case_no: int | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)


@dataclass(eq=False)
class TransferDecision:
    src_account_id: str
    dst_account_id: str
    amount_kobo: int
    channel: str
    decision: str
    status: str
    src_score: float
    dst_score: float
    reasons: list
    latency_ms: float
    reference: str | None = None
    sender_score: float | None = None
    context: dict | None = None
    resolved_by_event_id: str | None = None
    resolution_note: str | None = None
    resolved_at: datetime | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=now)


@dataclass(eq=False)
class AnalystAction:
    actor: str
    action: str
    ring_id: str | None = None
    decision_id: str | None = None
    account_ids: list = field(default_factory=list)
    note: str | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=now)


@dataclass(eq=False)
class SafeLimit:
    """The customer's own daily limit. Lowering applies at once; raising waits a cooling-off period,
    so someone forcing the customer cannot raise it on the spot."""

    account_id: str
    limit_kobo: int
    pending_limit_kobo: int | None = None
    pending_effective_at: datetime | None = None
    updated_at: datetime = field(default_factory=now)

    def current(self, at: datetime | None = None) -> int:
        if self.pending_limit_kobo is not None and self.pending_effective_at and self.pending_effective_at <= (at or now()):
            self.limit_kobo, self.pending_limit_kobo, self.pending_effective_at = self.pending_limit_kobo, None, None
        return self.limit_kobo

    def change(self, limit_kobo: int, at: datetime, cooling_hours: int) -> str:
        self.current(at)
        self.updated_at = at
        if limit_kobo <= self.limit_kobo:
            self.limit_kobo, self.pending_limit_kobo, self.pending_effective_at = limit_kobo, None, None
            return "lowered immediately"
        self.pending_limit_kobo = limit_kobo
        self.pending_effective_at = at + timedelta(hours=cooling_hours)
        return f"increase takes effect in {cooling_hours} hours"


@dataclass(eq=False)
class Alert:
    kind: str
    message: str
    severity: str = "high"
    customer_id: str | None = None
    account_id: str | None = None
    decision_id: str | None = None
    event_id: str | None = None
    context: dict | None = None
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=now)


@dataclass(eq=False)
class Label:
    """An investigation outcome: the account is a mule or legitimate, and when the bank learned it."""

    account_id: str
    label: str
    confirmed_at: datetime | None = None
    source: str = "import"
    created_at: datetime = field(default_factory=now)


@dataclass(eq=False)
class StatementEntry:
    """A statement line. It has no counterparty, so it feeds the sender's history but never the graph."""

    account_id: str
    reference: str
    ts: datetime
    amount_kobo: int
    direction: str
    channel: str | None = None
    narration: str | None = None
    id: str = field(default_factory=new_id)


@dataclass(eq=False)
class BankAction:
    """An outbox entry: recorded first, then sent to the bank, so a failed call stays visible and retryable."""

    kind: str
    account_id: str
    reference: str
    request: dict
    ring_id: str | None = None
    status: str = "pending"
    attempts: int = 0
    last_error: str | None = None
    response: dict | None = None
    connector: str = "none"
    done_at: datetime | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=now)


@dataclass(eq=False)
class TypologyWeight:
    code: str
    base_weight: float
    learned_weight: float
    mule_count: int
    legit_count: int
    updated_at: datetime = field(default_factory=now)


@dataclass(eq=False)
class TrainedModel:
    key: str
    payload: str = ""
    trained_at: datetime = field(default_factory=now)


@dataclass(eq=False)
class Trace:
    """One trace request sent through NIBSS for an account at another bank, and its answer."""

    ring_id: str
    actor: str
    bank_code: str
    account_no: str
    connector: str
    hop: int = 1
    status: str = "sent"
    error: str | None = None
    amount_in_kobo: int = 0
    onward_count: int = 0
    amount_onward_kobo: int = 0
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=now)


@dataclass(eq=False)
class ImportJob:
    fmt: str
    filename: str = ""
    dry_run: bool = False
    size_bytes: int = 0
    bytes_read: int = 0
    status: str = "queued"
    rows: int = 0
    valid: int = 0
    added: int = 0
    skipped: int = 0
    accounts_added: int = 0
    error_count: int = 0
    errors: list | None = None
    message: str | None = None
    actor: str | None = None
    finished_at: datetime | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=now)
