"""Connector to the bank's core systems, shaped on the Open Banking Nigeria (OBN) API standard.

Action mapping:
  24-hour watchlist  -> placeHold for the available balance, ending in 24 hours (OBN holds carry
                        a start and end date, so the hold lapses at the bank on its own)
  release            -> removeHold
  confirmed mule     -> block account with blockType PND (post no debit)

The OBN reference documents these paths. It does not document the token endpoint or remove-PND,
so the token path is configurable and lifting a PND stays a manual step at the bank.
Responses in the reference are shown inside a documentation wrapper ({"Result": {"value": ...}});
the real body is the inner JSON (usually a one-item list), which `_unwrap` handles either way.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

import httpx

from app.core.config import Settings
from app.network.application.ports import AccountProfile, BankConnector, BankResult
from app.network.infrastructure.file_formats import parse_amount_kobo, parse_time


def _unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and "Result" in payload and isinstance(payload["Result"], dict):
        payload = payload["Result"].get("value")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return payload
    return payload


def _first(payload: Any) -> Any:
    p = _unwrap(payload)
    return p[0] if isinstance(p, list) and p else p


def _successful(body: Any) -> bool:
    b = _first(body)
    if isinstance(b, str):
        return b.upper() == "SUCCESSFUL"
    if isinstance(b, dict):
        code = str(b.get("responseCode", "")).upper()
        return code in {"SUCCESSFUL", "00", "SUCCESS"}
    return False


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _body(result: BankResult) -> dict:
    body = _first(result.body) if result.ok else None
    return body if isinstance(body, dict) else {}


class _Responses:
    utc_offset_hours = 1

    def account_profile(self, account_no: str) -> AccountProfile:
        res = self.get_account(account_no)
        if not res.ok:
            return AccountProfile(False, res.error)
        b = _body(res)
        tier = str(b.get("kycTier") or "")
        return AccountProfile(True, opened_at=parse_time(b["accountOpeningDate"], self.utc_offset_hours) if b.get("accountOpeningDate") else None,
                              full_name=b.get("fullName") or None, kyc_tier=int(tier) if tier.isdigit() else None,
                              status=b.get("status"))

    def daily_limit_kobo(self, account_no: str) -> tuple[bool, int | None]:
        res = self.get_customer_limits(account_no)
        rows = _unwrap(res.body) if res.ok else []
        caps = [parse_amount_kobo(r["maxCumulativeAmount"]) for r in (rows if isinstance(rows, list) else [rows])
                if isinstance(r, dict) and r.get("maxCumulativeAmount") and str(r.get("periodType", "DAY")).upper() == "DAY"]
        return res.ok, (min(caps) if caps else None)

    def available_balance(self, account_no: str) -> str | None:
        b = _body(self.get_account(account_no))
        value = b.get("accountBalance") or b.get("availableBalance")
        return str(value).replace(",", "") if value is not None else None


class RecordOnlyConnector(_Responses):
    """No bank connected: actions are recorded for an operator to apply manually."""

    name = "none"

    def _no(self, *_a, **_k) -> BankResult:
        return BankResult(False, error="no bank connector configured")

    get_account = get_customer_limits = get_statement = _no

    def place_hold(self, *_a, **_k) -> BankResult:
        return BankResult(True, {"responseCode": "RECORDED"}, meta={"recorded_only": True})

    remove_hold = block_pnd = place_hold


class OBNConnector(_Responses):
    name = "obn"

    def __init__(self, base_url: str, client_id: str, client_secret: str, token_path: str = "/access/token",
                 timeout: float = 8.0, http: httpx.Client | None = None, utc_offset_hours: int = 1):
        self.base = base_url.rstrip("/")
        self.utc_offset_hours = utc_offset_hours
        self.client_id, self.client_secret, self.token_path = client_id, client_secret, token_path
        self.http = http or httpx.Client(timeout=timeout)
        self._token: str | None = None
        self._token_until = 0.0

    def _auth(self) -> dict[str, str]:
        if not self._token or time.time() > self._token_until - 30:
            r = self.http.post(f"{self.base}{self.token_path}",
                               json={"client_id": self.client_id, "client_secret": self.client_secret,
                                     "grant_type": "client_credentials"})
            r.raise_for_status()
            body = _first(r.json())
            self._token = body["access_token"]
            self._token_until = time.time() + float(body.get("expires_in", 3600))
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def _call(self, method: str, path: str, body: dict | None = None) -> BankResult:
        try:
            r = self.http.request(method, f"{self.base}{path}", json=body, headers=self._auth())
            if r.status_code == 401:
                self._token = None
                r = self.http.request(method, f"{self.base}{path}", json=body, headers=self._auth())
            payload = r.json() if r.content else None
            if r.status_code >= 400:
                return BankResult(False, payload, f"HTTP {r.status_code}")
            return BankResult(True, _unwrap(payload))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            return BankResult(False, error=f"{type(exc).__name__}: {exc}"[:400])

    def get_account(self, account_no: str) -> BankResult:
        return self._call("GET", f"/account/{account_no}")

    def get_customer_limits(self, account_no: str) -> BankResult:
        return self._call("GET", f"/limit/getCustomerTransactionLimit/{account_no}")

    def get_statement(self, account_no: str, start: datetime, end: datetime) -> BankResult:
        return self._call("GET", "/transaction/getStatement",
                          {"accountNumber": account_no, "startDate": _fmt(start), "endDate": _fmt(end)})

    def place_hold(self, account_no: str, amount_naira: str, reference: str, reason: str, start: datetime, end: datetime) -> BankResult:
        res = self._call("POST", "/transaction/placeHold", {
            "accountNumber": account_no, "amount": amount_naira, "holdReferenceId": reference, "reason": reason,
            "startdate": _fmt(start), "enddate": _fmt(end)})
        return res if not res.ok or _successful(res.body) else BankResult(False, res.body, "bank did not confirm the hold")

    def remove_hold(self, account_no: str, reference: str) -> BankResult:
        res = self._call("POST", "/transaction/removeHold", {"accountNumber": account_no, "holdReferenceId": reference})
        return res if not res.ok or _successful(res.body) else BankResult(False, res.body, "bank did not confirm the removal")

    def block_pnd(self, account_no: str, message: str) -> BankResult:
        res = self._call("POST", "/account/block", {"accountNumber": account_no, "blockMessage": message, "blockType": "PND"})
        return res if not res.ok or _successful(res.body) else BankResult(False, res.body, "bank did not confirm the PND")


_connector: BankConnector | None = None


def get_connector(s: Settings) -> BankConnector:
    global _connector
    if _connector is None or _connector.name != s.network_bank_connector:
        if s.network_bank_connector == "obn":
            _connector = OBNConnector(s.network_obn_base_url, s.network_obn_client_id, s.network_obn_client_secret,
                                      s.network_obn_token_path, s.network_obn_timeout_s,
                                      utc_offset_hours=s.network_import_utc_offset_hours)
        else:
            _connector = RecordOnlyConnector()
    return _connector


def set_connector(c: BankConnector | None) -> None:
    """Tests and the mock server inject a connector here."""
    global _connector
    _connector = c
