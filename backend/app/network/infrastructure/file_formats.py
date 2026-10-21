"""Bank data importers. Each parser turns a file into TheOne's ingest shapes and reports every
bad row with its row number instead of failing the whole file.

Formats:
  csv       generic transfers; columns renamed with a mapping
  nip       NIBSS NIP-style session records (column names and channel codes are configurable
            assumptions: confirm them against the bank's actual NIP export)
  pacs008   ISO 20022 FIToFICustomerCreditTransfer XML (parsed with defusedxml)
  obn_accounts / obn_statement   Open Banking Nigeria Account objects and statement lines
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from defusedxml import ElementTree as SafeET

from app.network.application import ports

CSV_FIELDS = {
    "reference": "reference", "timestamp": "timestamp", "src_bank": "src_bank", "src_account": "src_account",
    "src_name": "src_name", "dst_bank": "dst_bank", "dst_account": "dst_account", "dst_name": "dst_name",
    "amount": "amount", "channel": "channel", "narration": "narration",
}

NIP_FIELDS = {
    "reference": "SessionID", "timestamp": "TransactionDate", "src_bank": "SourceInstitutionCode",
    "src_account": "OriginatorAccountNumber", "src_name": "OriginatorAccountName", "dst_bank": "DestinationInstitutionCode",
    "dst_account": "BeneficiaryAccountNumber", "dst_name": "BeneficiaryAccountName", "amount": "Amount",
    "channel": "ChannelCode", "narration": "Narration",
}

# Commonly cited NIP channel codes. Treat as an assumption until checked against the NIBSS spec.
NIP_CHANNELS = {"1": "branch", "2": "internet", "3": "mobile", "4": "pos", "5": "atm", "6": "internet",
                "7": "nip", "8": "ussd", "9": "nip"}
CHANNEL_WORDS = {"mobile": "mobile", "app": "mobile", "ussd": "ussd", "internet": "internet", "web": "internet",
                 "pos": "pos", "atm": "atm", "agent": "agent", "branch": "branch", "teller": "branch", "card": "card",
                 "nip": "nip", "transfer": "nip"}


@dataclass
class ParseResult:
    accounts: list[dict] = field(default_factory=list)
    transfers: list[dict] = field(default_factory=list)
    statements: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    rows: int = 0

    def error(self, row: int, msg: str) -> None:
        if len(self.errors) < 200:
            self.errors.append({"row": row, "error": msg})


def parse_amount_kobo(v) -> int:
    s = str(v).strip().replace(",", "").replace("₦", "").replace("NGN", "").strip()
    try:
        d = Decimal(s)
    except InvalidOperation as exc:
        raise ValueError(f"amount {v!r} is not a number") from exc
    if d <= 0:
        raise ValueError(f"amount {v!r} must be positive")
    return int((d * 100).to_integral_value())


def parse_time(v, utc_offset_hours: int) -> datetime:
    s = str(v).strip()
    if not s:
        raise ValueError("timestamp is empty")
    s2 = s.replace("Z", "+00:00")
    dt = None
    try:
        dt = datetime.fromisoformat(s2)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y%m%d%H%M%S", "%d-%b-%Y %H:%M:%S"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        raise ValueError(f"timestamp {v!r} is not a recognised date")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone(timedelta(hours=utc_offset_hours)))
    return dt.astimezone(timezone.utc)


def channel_of(v, nip_codes: bool = False) -> str:
    s = str(v or "").strip().lower()
    if nip_codes and s in NIP_CHANNELS:
        return NIP_CHANNELS[s]
    for word, ch in CHANNEL_WORDS.items():
        if word in s:
            return ch
    return "nip"


def _rows_to_transfers(reader, mapping: dict, res: ParseResult, offset: int, nip_codes: bool, default_bank: str | None,
                       start: int = 2) -> None:
    for i, row in enumerate(reader, start=start):
        res.rows += 1
        get = lambda k: (row.get(mapping.get(k, k)) or "").strip()  # noqa: E731
        try:
            ref = get("reference")
            if not ref:
                raise ValueError("reference is empty")
            src_bank, dst_bank = get("src_bank") or default_bank, get("dst_bank") or default_bank
            src_acc, dst_acc = get("src_account"), get("dst_account")
            if not (src_bank and src_acc and dst_bank and dst_acc):
                raise ValueError("source and destination bank code and account number are required")
            amount = row.get(mapping.get("amount_kobo", "amount_kobo"))
            kobo = int(amount) if amount not in (None, "") else parse_amount_kobo(get("amount"))
            res.transfers.append({
                "reference": ref[:64], "ts": parse_time(get("timestamp"), offset),
                "src": {"bank_code": src_bank, "account_no": src_acc}, "dst": {"bank_code": dst_bank, "account_no": dst_acc},
                "src_name": get("src_name") or None, "dst_name": get("dst_name") or None,
                "amount_kobo": kobo, "channel": channel_of(get("channel"), nip_codes), "narration": get("narration")[:140] or None,
            })
        except (ValueError, TypeError) as exc:
            res.error(i, str(exc))


def parse_csv(text: str, mapping: dict | None, offset: int, default_bank: str | None = None) -> ParseResult:
    res = ParseResult()
    m = {**CSV_FIELDS, **(mapping or {})}
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    missing = [m[k] for k in ("reference", "timestamp", "src_account", "dst_account") if m[k] not in (reader.fieldnames or [])]
    if missing:
        res.error(1, f"missing columns: {', '.join(missing)} (found: {', '.join(reader.fieldnames or [])})")
        return res
    _rows_to_transfers(reader, m, res, offset, nip_codes=False, default_bank=default_bank)
    return res


def parse_nip(text: str, mapping: dict | None, offset: int) -> ParseResult:
    res = ParseResult()
    m = {**NIP_FIELDS, **(mapping or {})}
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    missing = [m[k] for k in ("reference", "timestamp", "src_bank", "src_account", "dst_bank", "dst_account", "amount")
               if m[k] not in (reader.fieldnames or [])]
    if missing:
        res.error(1, f"missing NIP columns: {', '.join(missing)}")
        return res
    _rows_to_transfers(reader, m, res, offset, nip_codes=True, default_bank=None)
    return res


def _strip_ns(el) -> None:
    for e in el.iter():
        if isinstance(e.tag, str) and "}" in e.tag:
            e.tag = e.tag.split("}", 1)[1]


def _txt(el, path: str) -> str | None:
    x = el.find(path)
    return x.text.strip() if x is not None and x.text else None


def _party(tx, role: str) -> tuple[str | None, str | None, str | None]:
    acct = _txt(tx, f"{role}Acct/Id/Othr/Id") or _txt(tx, f"{role}Acct/Id/IBAN")
    bank = (_txt(tx, f"{role}Agt/FinInstnId/ClrSysMmbId/MmbId") or _txt(tx, f"{role}Agt/FinInstnId/Othr/Id")
            or _txt(tx, f"{role}Agt/FinInstnId/BICFI"))
    return bank, acct, _txt(tx, f"{role}/Nm")


def parse_pacs008(text: str, offset: int) -> ParseResult:
    res = ParseResult()
    try:
        root = SafeET.fromstring(text.encode() if isinstance(text, str) else text)
    except Exception as exc:  # noqa: BLE001  (defusedxml raises several types)
        res.error(1, f"not valid XML: {exc}")
        return res
    _strip_ns(root)
    created = _txt(root, ".//GrpHdr/CreDtTm")
    for i, tx in enumerate(root.iter("CdtTrfTxInf"), start=1):
        res.rows += 1
        try:
            ref = _txt(tx, "PmtId/EndToEndId") or _txt(tx, "PmtId/TxId") or _txt(tx, "PmtId/InstrId")
            if not ref:
                raise ValueError("no EndToEndId, TxId or InstrId")
            amt_el = tx.find("IntrBkSttlmAmt")
            if amt_el is None or not amt_el.text:
                raise ValueError("no IntrBkSttlmAmt")
            if (amt_el.get("Ccy") or "NGN") != "NGN":
                raise ValueError(f"currency {amt_el.get('Ccy')} is not NGN")
            ts = _txt(tx, "AccptncDtTm") or created or _txt(tx, "IntrBkSttlmDt") or _txt(root, ".//GrpHdr/IntrBkSttlmDt")
            dbank, dacc, dname = _party(tx, "Dbtr")
            cbank, cacc, cname = _party(tx, "Cdtr")
            if not (dbank and dacc and cbank and cacc):
                raise ValueError("debtor and creditor need an account id and an agent identifier")
            res.transfers.append({
                "reference": ref[:64], "ts": parse_time(ts, offset), "src": {"bank_code": dbank, "account_no": dacc},
                "dst": {"bank_code": cbank, "account_no": cacc}, "src_name": dname, "dst_name": cname,
                "amount_kobo": parse_amount_kobo(amt_el.text), "channel": "nip",
                "narration": (_txt(tx, "RmtInf/Ustrd") or "")[:140] or None,
            })
        except (ValueError, TypeError) as exc:
            res.error(i, str(exc))
    if res.rows == 0:
        res.error(1, "no CdtTrfTxInf elements found (expected an ISO 20022 pacs.008 message)")
    return res


def _obn_list(text: str) -> list:
    data = json.loads(text)
    if isinstance(data, dict) and "Result" in data:
        data = data["Result"].get("value")
        data = json.loads(data) if isinstance(data, str) else data
    if isinstance(data, dict):
        data = data.get("data") or data.get("accounts") or data.get("transactions") or [data]
    if not isinstance(data, list):
        raise ValueError("expected a JSON list of OBN objects")
    return data


def parse_obn_accounts(text: str, bank_code: str, offset: int) -> ParseResult:
    res = ParseResult()
    try:
        items = _obn_list(text)
    except ValueError as exc:
        res.error(1, str(exc))
        return res
    for i, a in enumerate(items, start=1):
        res.rows += 1
        try:
            no = str(a.get("accountNumber") or "").strip()
            if not re.fullmatch(r"\d{10}", no):
                raise ValueError(f"accountNumber {no!r} is not a 10-digit NUBAN")
            acc = {"bank_code": bank_code, "account_no": no, "holder_name": a.get("fullName") or a.get("accountName"),
                   "identifiers": []}
            if a.get("accountOpeningDate"):
                acc["opened_at"] = parse_time(a["accountOpeningDate"], offset)
            if a.get("bvn"):
                acc["bvn"] = str(a["bvn"])
            if a.get("phoneNumber"):
                acc["identifiers"].append({"kind": "phone", "value": str(a["phoneNumber"])})
            if a.get("email"):
                acc["identifiers"].append({"kind": "email", "value": str(a["email"])})
            if str(a.get("kycTier") or "").isdigit():
                acc["kyc_tier"] = int(a["kycTier"])
            res.accounts.append(acc)
        except (ValueError, TypeError, AttributeError) as exc:
            res.error(i, str(exc))
    return res


def parse_obn_statement(text: str, bank_code: str, account_no: str | None, offset: int) -> ParseResult:
    res = ParseResult()
    try:
        items = _obn_list(text)
    except ValueError as exc:
        res.error(1, str(exc))
        return res
    for i, e in enumerate(items, start=1):
        res.rows += 1
        try:
            no = str(e.get("accountNumber") or account_no or "").strip()
            if not no:
                raise ValueError("accountNumber missing (pass account_no for the whole file)")
            ref = str(e.get("referenceId") or "").strip()
            if not ref:
                raise ValueError("referenceId missing")
            direction = str(e.get("debitOrCredit") or "").strip().lower()
            if direction.startswith("d"):
                direction = "debit"
            elif direction.startswith("c"):
                direction = "credit"
            else:
                raise ValueError(f"debitOrCredit {e.get('debitOrCredit')!r} is not DEBIT or CREDIT")
            res.statements.append({"bank_code": bank_code, "account_no": no, "reference": ref[:80],
                                   "ts": parse_time(e.get("bookDate") or e.get("valueDate"), offset),
                                   "amount_kobo": parse_amount_kobo(e.get("amount")), "direction": direction,
                                   "channel": channel_of(e.get("channel")), "narration": (e.get("narration") or "")[:200] or None})
        except (ValueError, TypeError, AttributeError) as exc:
            res.error(i, str(exc))
    return res


STREAMABLE = {"nip", "csv"}

RECIPIENT_WORDS = ("benef", "dest", "dst", "recipient", "counterparty", "payee", "to_account", "credit_account")


class MissingColumns(ports.MissingColumns):
    """The message says what was expected, what was found, and, when there is no recipient column
    at all, why that matters."""

    def __init__(self, missing: list[str], found: list[str], fmt: str):
        label = "NIP session records" if fmt == "nip" else "generic transfers"
        what = ", ".join(missing) if len(missing) <= 3 else f"{len(missing)} expected columns"
        msg = f"The columns do not match {label} (missing {what})."
        if not any(w in c.lower() for c in found for w in RECIPIENT_WORDS):
            msg += " There is no recipient account column, so the file cannot show who paid whom."
            if any(c.lower() in ("is_fraud", "fraud", "label", "fraud_label") for c in found):
                msg += " It looks like a labelled transaction dataset."
        super().__init__(msg, missing, found)


def iter_file_batches(path: str, fmt: str, mapping: dict | None, offset: int, default_bank: str | None,
                      batch_size: int = 5000, on_progress=None):
    """Read a large NIP or CSV file from disk in batches, without loading it into memory.

    Yields one ParseResult per batch. The first batch reports missing columns, if any, and the
    iteration stops there. on_progress(bytes_read) is called after each batch."""
    import itertools

    if fmt not in STREAMABLE:
        raise ValueError(f"large-file import supports {sorted(STREAMABLE)}")
    m = {**(NIP_FIELDS if fmt == "nip" else CSV_FIELDS), **(mapping or {})}
    need = ("reference", "timestamp", "src_bank", "src_account", "dst_bank", "dst_account", "amount") if fmt == "nip" else \
        ("reference", "timestamp", "src_account", "dst_account")
    with open(path, "rb") as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
        reader = csv.DictReader(text)
        missing = [m[k] for k in need if m[k] not in (reader.fieldnames or [])]
        if missing:
            raise MissingColumns(missing, list(reader.fieldnames or []), fmt)
        row_no = 2
        while True:
            chunk = list(itertools.islice(reader, batch_size))
            if not chunk:
                break
            res = ParseResult()
            _rows_to_transfers(chunk, m, res, offset, nip_codes=(fmt == "nip"), default_bank=default_bank, start=row_no)
            row_no += len(chunk)
            if on_progress:
                on_progress(raw.tell())
            yield res
