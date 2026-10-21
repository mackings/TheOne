from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AccountRef(BaseModel):
    bank_code: str = Field(min_length=1, max_length=12)
    account_no: str = Field(min_length=1, max_length=20)


class IdentifierIn(BaseModel):
    kind: str = Field(description="phone | device | email | address | ip")
    value: str = Field(min_length=1, max_length=200)


class AccountIn(AccountRef):
    holder_name: str | None = Field(default=None, max_length=120)
    bvn: str | None = Field(default=None, description="hashed on arrival; never stored raw")
    opened_at: datetime | None = None
    kyc_tier: int | None = Field(default=None, ge=1, le=3)
    is_merchant: bool | None = None
    customer_id: str | None = Field(default=None, description="link to a biometric customer for owner step-up")
    identifiers: list[IdentifierIn] = []


class TransferIn(BaseModel):
    reference: str = Field(min_length=1, max_length=64, description="unique; replays are ignored")
    ts: datetime
    src: AccountRef
    dst: AccountRef
    amount_kobo: int = Field(gt=0)
    channel: str = "nip"
    narration: str | None = Field(default=None, max_length=140)
    src_name: str | None = None
    dst_name: str | None = None


class IngestIn(BaseModel):
    accounts: list[AccountIn] = []
    transfers: list[TransferIn] = Field(default=[], max_length=50_000)


class ReportIn(AccountRef):
    kind: str = Field(description="victim_complaint | confirmed_mule | cleared")
    transfer_reference: str | None = None
    note: str | None = Field(default=None, max_length=500)
    reporter: str | None = Field(default=None, max_length=80)


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: float | None = None


class DecideIn(BaseModel):
    reference: str | None = Field(default=None, max_length=64, description="idempotency key; replays return the first decision")
    source: AccountRef
    beneficiary: AccountRef
    beneficiary_name: str | None = None
    amount_kobo: int = Field(gt=0)
    channel: str = "nip"
    device: str | None = Field(default=None, max_length=200, description="device id from the app; hashed, used for new-device checks")
    location: Location | None = None


class ResolveIn(BaseModel):
    verification_event_id: str | None = None
    customer_confirmed: bool | None = None
    bank_factor_passed: bool | None = Field(default=None, description="set by the bank's channel after its own OTP succeeds; only for customers with no biometrics")


class ReviewIn(BaseModel):
    outcome: str = Field(description="release | block")
    actor: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=500)


class RingActionIn(BaseModel):
    action: str = Field(description="watchlist_24h | confirm | dismiss | release")
    account_ids: list[str] | None = None
    actor: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=500)


class LinkIn(BaseModel):
    customer_id: str


class SimulateIn(BaseModel):
    seed: int = 7
    customers: int = Field(default=600, ge=50, le=5000)
    rings: int = Field(default=5, ge=0, le=30)
    reset: bool = True


class SafeLimitIn(BaseModel):
    limit_kobo: int = Field(gt=0)


class AckIn(BaseModel):
    actor: str = Field(min_length=1, max_length=80)


class LabelIn(AccountRef):
    label: str = Field(description="mule | legit")
    confirmed_at: datetime | None = None
    source: str | None = Field(default=None, max_length=40)


class BacktestIn(BaseModel):
    days: int = Field(default=14, ge=1, le=90)
    step_hours: int = Field(default=12, ge=1, le=168)
    capacity_per_day: int = Field(default=20, ge=1, le=10_000)


class StatementIn(BaseModel):
    """A bank statement as text (pasted, or read from a text export). It is checked, never stored."""
    text: str = Field(min_length=50, max_length=2_000_000)


class StatementImportIn(StatementIn):
    """Add a statement to the money map. bank_code is the bank that issued the statement."""
    bank_code: str = Field(min_length=1, max_length=12)


class TraceIn(BaseModel):
    actor: str = Field(min_length=1, max_length=80)
    depth: int = Field(default=2, ge=1, le=3)
