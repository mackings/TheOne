"""NIBSS connection: cross-bank trace requests and the BVN watch-list.

TheOne sees money only until it leaves the bank. To follow it further, a bank asks the
receiving banks, through NIBSS, what happened next: that is a trace request. NIBSS also runs
the industry BVN watch-list of people confirmed in fraud.

NIBSS does not publish an open API for either, so this module defines the two calls TheOne
needs and talks to them over HTTP. Until the bank's NIBSS access is in place it points at a
mock NIBSS served by this app (/mock-nibss), which answers with simulated other-bank data.

  trace(account, received)  ->  onward transfers out of that account at its bank
  watchlisted(bvn)          ->  whether a BVN is on the watch-list

Raw BVNs are only used in flight for the watch-list check; TheOne stores a keyed hash.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings
from app.network.application.ports import NibssConnector, NibssError


class NoNibss:
    name = "none"

    def trace(self, bank_code: str, account_no: str, received: list[dict]) -> list[dict]:
        raise NibssError("no NIBSS connection is configured (set NETWORK_NIBSS_CONNECTOR)")

    def watchlisted(self, bvn: str) -> bool:
        return False


class HttpNibss:
    name = "http"

    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0, http: httpx.Client | None = None):
        self.base = base_url.rstrip("/")
        self.key = api_key
        self.http = http or httpx.Client(timeout=timeout)

    def _post(self, path: str, body: dict) -> Any:
        try:
            r = self.http.post(f"{self.base}{path}", json=body, headers={"X-Api-Key": self.key})
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise NibssError(f"NIBSS request failed: {e}") from e

    def trace(self, bank_code: str, account_no: str, received: list[dict]) -> list[dict]:
        return self._post("/trace", {"bank_code": bank_code, "account_no": account_no, "received": received}).get("onward", [])

    def watchlisted(self, bvn: str) -> bool:
        return bool(self._post("/watchlist/check", {"bvn": bvn}).get("listed"))


_connector: NibssConnector | None = None


def get_connector(s: Settings) -> NibssConnector:
    global _connector
    if _connector is None or _connector.name != s.network_nibss_connector:
        _connector = HttpNibss(s.network_nibss_base_url, s.network_nibss_api_key) if s.network_nibss_connector == "http" else NoNibss()
    return _connector


def set_connector(c: NibssConnector | None) -> None:
    """Tests inject a connector here."""
    global _connector
    _connector = c
