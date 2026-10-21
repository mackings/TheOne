"""Network tables, and the mapping of the domain entities onto them."""
from __future__ import annotations

from sqlalchemy import (JSON, BigInteger, Boolean, Column, Float, ForeignKey, Integer, String, Table, Text,
                        UniqueConstraint)

from app.core.timeutil import new_id, now
from app.infrastructure.database import UtcDateTime, mapper_registry, metadata
from app.network.domain import entities as e


def _id() -> Column:
    return Column("id", String(32), primary_key=True, default=new_id)


def _created(index: bool = False) -> Column:
    return Column("created_at", UtcDateTime(), default=now, index=index)


accounts = Table(
    "net_accounts", metadata,
    _id(),
    Column("bank_code", String(12), index=True, nullable=False),
    Column("account_no", String(20), nullable=False),
    Column("holder_name", String(120), default="", nullable=False),
    Column("bvn_hash", String(64), nullable=True, index=True),
    Column("opened_at", UtcDateTime(), nullable=True),
    Column("kyc_tier", Integer, nullable=True),
    Column("is_merchant", Boolean, default=False, nullable=False),
    Column("customer_id", ForeignKey("customers.id"), nullable=True, index=True),
    Column("status", String(16), default="active", nullable=False),
    Column("status_until", UtcDateTime(), nullable=True),
    Column("synthetic_label", String(16), nullable=True),
    Column("bank_daily_limit_kobo", BigInteger, nullable=True),
    Column("bank_synced_at", UtcDateTime(), nullable=True),
    _created(),
    UniqueConstraint("bank_code", "account_no", name="uq_net_account"),
)

identifiers = Table(
    "net_identifiers", metadata,
    _id(),
    Column("kind", String(12), nullable=False),
    Column("value_hash", String(64), index=True, nullable=False),
    Column("masked", String(40), nullable=False),
    UniqueConstraint("kind", "value_hash", name="uq_net_identifier"),
)

account_identifiers = Table(
    "net_account_identifiers", metadata,
    Column("account_id", ForeignKey("net_accounts.id"), primary_key=True),
    Column("identifier_id", ForeignKey("net_identifiers.id"), primary_key=True, index=True),
    Column("first_seen", UtcDateTime(), default=now, nullable=False),
)

transfers = Table(
    "net_transfers", metadata,
    _id(),
    Column("reference", String(64), unique=True, nullable=False),
    Column("ts", UtcDateTime(), index=True, nullable=False),
    Column("src_account_id", ForeignKey("net_accounts.id"), index=True, nullable=False),
    Column("dst_account_id", ForeignKey("net_accounts.id"), index=True, nullable=False),
    Column("amount_kobo", BigInteger, nullable=False),
    Column("channel", String(12), nullable=False),
    Column("narration", String(140), nullable=True),
)

reports = Table(
    "net_reports", metadata,
    _id(),
    Column("kind", String(20), nullable=False),
    Column("account_id", ForeignKey("net_accounts.id"), index=True, nullable=False),
    Column("transfer_reference", String(64), nullable=True),
    Column("note", String(500), nullable=True),
    Column("reporter", String(80), nullable=True),
    _created(),
)

rings = Table(
    "net_rings", metadata,
    _id(),
    Column("status", String(16), default="open", nullable=False),
    Column("score", Float, nullable=False),
    Column("member_ids", JSON, nullable=False),
    Column("summary", JSON, nullable=False),
    Column("case_no", Integer, nullable=True, unique=True, index=True),
    _created(),
    Column("updated_at", UtcDateTime(), default=now, nullable=False),
)

decisions = Table(
    "net_decisions", metadata,
    _id(),
    Column("reference", String(64), nullable=True, unique=True),
    _created(index=True),
    Column("src_account_id", ForeignKey("net_accounts.id"), index=True, nullable=False),
    Column("dst_account_id", ForeignKey("net_accounts.id"), index=True, nullable=False),
    Column("amount_kobo", BigInteger, nullable=False),
    Column("channel", String(12), nullable=False),
    Column("decision", String(16), nullable=False),
    Column("status", String(16), nullable=False),
    Column("src_score", Float, nullable=False),
    Column("dst_score", Float, nullable=False),
    Column("sender_score", Float, nullable=True),
    Column("context", JSON, nullable=True),
    Column("reasons", JSON, nullable=False),
    Column("latency_ms", Float, nullable=False),
    Column("resolved_by_event_id", String(32), nullable=True),
    Column("resolution_note", String(300), nullable=True),
    Column("resolved_at", UtcDateTime(), nullable=True),
)

actions = Table(
    "net_actions", metadata,
    _id(),
    _created(index=True),
    Column("actor", String(80), nullable=False),
    Column("action", String(24), nullable=False),
    Column("ring_id", String(32), nullable=True, index=True),
    Column("decision_id", String(32), nullable=True),
    Column("account_ids", JSON, default=list, nullable=False),
    Column("note", String(500), nullable=True),
)

safe_limits = Table(
    "net_safe_limits", metadata,
    Column("account_id", ForeignKey("net_accounts.id"), primary_key=True),
    Column("limit_kobo", BigInteger, nullable=False),
    Column("pending_limit_kobo", BigInteger, nullable=True),
    Column("pending_effective_at", UtcDateTime(), nullable=True),
    Column("updated_at", UtcDateTime(), default=now, nullable=False),
)

alerts = Table(
    "net_alerts", metadata,
    _id(),
    _created(index=True),
    Column("kind", String(20), nullable=False),
    Column("severity", String(10), default="high", nullable=False),
    Column("customer_id", String(32), nullable=True, index=True),
    Column("account_id", String(32), nullable=True),
    Column("decision_id", String(32), nullable=True),
    Column("event_id", String(32), nullable=True),
    Column("message", String(500), nullable=False),
    Column("context", JSON, nullable=True),
    Column("acknowledged_by", String(80), nullable=True),
    Column("acknowledged_at", UtcDateTime(), nullable=True),
)

labels = Table(
    "net_labels", metadata,
    Column("account_id", ForeignKey("net_accounts.id"), primary_key=True),
    Column("label", String(10), nullable=False),
    Column("confirmed_at", UtcDateTime(), nullable=True),
    Column("source", String(40), default="import", nullable=False),
    _created(),
)

statement_entries = Table(
    "net_statement_entries", metadata,
    _id(),
    Column("account_id", ForeignKey("net_accounts.id"), index=True, nullable=False),
    Column("reference", String(80), nullable=False),
    Column("ts", UtcDateTime(), index=True, nullable=False),
    Column("amount_kobo", BigInteger, nullable=False),
    Column("direction", String(6), nullable=False),
    Column("channel", String(20), nullable=True),
    Column("narration", String(200), nullable=True),
    UniqueConstraint("account_id", "reference", name="uq_net_statement"),
)

bank_actions = Table(
    "net_bank_actions", metadata,
    _id(),
    _created(index=True),
    Column("kind", String(20), nullable=False),
    Column("account_id", ForeignKey("net_accounts.id"), index=True, nullable=False),
    Column("ring_id", String(32), nullable=True),
    Column("reference", String(64), unique=True, nullable=False),
    Column("request", JSON, nullable=False),
    Column("status", String(12), default="pending", nullable=False),
    Column("attempts", Integer, default=0, nullable=False),
    Column("last_error", String(500), nullable=True),
    Column("response", JSON, nullable=True),
    Column("connector", String(20), default="none", nullable=False),
    Column("done_at", UtcDateTime(), nullable=True),
)

typology_weights = Table(
    "net_typology_weights", metadata,
    Column("code", String(40), primary_key=True),
    Column("base_weight", Float, nullable=False),
    Column("learned_weight", Float, nullable=False),
    Column("mule_count", Integer, nullable=False),
    Column("legit_count", Integer, nullable=False),
    Column("updated_at", UtcDateTime(), default=now, nullable=False),
)

meta = Table(
    "net_meta", metadata,
    Column("key", String(40), primary_key=True),
    Column("value", BigInteger, default=0, nullable=False),
)

models = Table(
    "net_models", metadata,
    Column("key", String(40), primary_key=True),
    Column("payload", Text, nullable=False),
    Column("trained_at", UtcDateTime(), default=now, nullable=False),
)

traces = Table(
    "net_traces", metadata,
    _id(),
    _created(index=True),
    Column("ring_id", String(32), index=True, nullable=False),
    Column("actor", String(80), nullable=False),
    Column("bank_code", String(12), nullable=False),
    Column("account_no", String(20), nullable=False),
    Column("hop", Integer, default=1, nullable=False),
    Column("connector", String(20), nullable=False),
    Column("status", String(12), default="sent", nullable=False),
    Column("error", String(300), nullable=True),
    Column("amount_in_kobo", BigInteger, default=0, nullable=False),
    Column("onward_count", Integer, default=0, nullable=False),
    Column("amount_onward_kobo", BigInteger, default=0, nullable=False),
)

import_jobs = Table(
    "net_import_jobs", metadata,
    _id(),
    _created(index=True),
    Column("finished_at", UtcDateTime(), nullable=True),
    Column("fmt", String(16), nullable=False),
    Column("filename", String(200), default="", nullable=False),
    Column("size_bytes", BigInteger, default=0, nullable=False),
    Column("bytes_read", BigInteger, default=0, nullable=False),
    Column("dry_run", Boolean, default=False, nullable=False),
    Column("status", String(12), default="queued", nullable=False),
    Column("rows", BigInteger, default=0, nullable=False),
    Column("valid", BigInteger, default=0, nullable=False),
    Column("added", BigInteger, default=0, nullable=False),
    Column("skipped", BigInteger, default=0, nullable=False),
    Column("accounts_added", BigInteger, default=0, nullable=False),
    Column("error_count", BigInteger, default=0, nullable=False),
    Column("errors", JSON, nullable=True),
    Column("message", String(300), nullable=True),
    Column("actor", String(80), nullable=True),
)

MAPPINGS = (
    (e.Account, accounts), (e.Identifier, identifiers), (e.AccountIdentifier, account_identifiers),
    (e.Transfer, transfers), (e.Report, reports), (e.Ring, rings), (e.TransferDecision, decisions),
    (e.AnalystAction, actions), (e.SafeLimit, safe_limits), (e.Alert, alerts), (e.Label, labels),
    (e.StatementEntry, statement_entries), (e.BankAction, bank_actions), (e.TypologyWeight, typology_weights),
    (e.TrainedModel, models), (e.Trace, traces), (e.ImportJob, import_jobs),
)


def map_entities() -> None:
    for entity, table in MAPPINGS:
        mapper_registry.map_imperatively(entity, table)


map_entities()
