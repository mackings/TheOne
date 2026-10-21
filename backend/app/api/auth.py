"""Role-based API keys.

Roles:
  system      the bank's backend: sends data in, asks for transfer decisions
  app         the customer's mobile or web app: enrolment, verification, step-up, own transfers
  analyst     fraud analysts: read everything in the network, watchlist, dismiss, acknowledge alerts
  supervisor  analyst plus confirming rings, releasing or blocking held transfers, learning,
              backtests, retries and demo data
  admin       everything (the legacy single API_KEY maps here)

Keys come from API_KEYS="key:role,..." (and API_KEY for admin). With no keys configured the API
is open, which is for local development only.
"""
from __future__ import annotations

import hmac
import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

PUBLIC = "public"
ALL = {"system", "app", "analyst", "supervisor", "admin"}
STAFF = {"analyst", "supervisor", "admin"}

RULES: list[tuple[set[str] | str, re.Pattern, set[str] | str]] = [(m, re.compile(p), r) for m, p, r in [
    ("*", r"^/(health|docs|redoc|openapi\.json)(/|$)", PUBLIC),
    ("*", r"^/mock-obn(/|$)", PUBLIC),
    ("*", r"^/mock-nibss(/|$)", PUBLIC),
    ("*", r"^/(enrolment|verify|iris|stepup)(/|$)", {"app", "system", "supervisor", "admin"}),
    ({"GET"}, r"^/customers(/|$)", ALL),
    ({"POST"}, r"^/customers$", {"app", "system", "supervisor", "admin"}),
    ({"DELETE"}, r"^/customers/[^/]+/(template|iris-template|iris-duress-template)$", {"app", "supervisor", "admin"}),
    ({"POST"}, r"^/network/decide$", {"system", "app", "admin"}),
    ({"POST"}, r"^/network/decisions/[^/]+/(resolve|execute)$", {"system", "app", "admin"}),
    ("*", r"^/network/accounts/[^/]+/safe-limit$", {"app", "system", "analyst", "supervisor", "admin"}),
    ({"GET"}, r"^/network/customers/[^/]+/accounts$", ALL),
    ({"POST"}, r"^/network/(ingest|import/[^/]+(/job)?|reports|labels|statement/import)$", {"system", "supervisor", "admin"}),
    ({"POST"}, r"^/network/accounts/[^/]+/(link|sync)$", {"system", "supervisor", "admin"}),
    ({"POST"}, r"^/network/(simulate|reset|learning/refresh|backtest|model/train)$", {"supervisor", "admin"}),
    ({"POST"}, r"^/network/decisions/[^/]+/review$", {"supervisor", "admin"}),
    ({"POST"}, r"^/network/bank-actions/[^/]+/retry$", {"supervisor", "admin"}),
    ({"POST"}, r"^/network/(analyse|rings/[^/]+/actions|rings/[^/]+/trace|alerts/[^/]+/ack|statement/check|statement/check-file)$", STAFF),
    ({"GET"}, r"^/network(/|$)", STAFF | {"system"}),
    ("*", r"^/assistant/", STAFF),
]]


def allowed_roles(method: str, path: str) -> set[str] | str:
    for methods, pattern, roles in RULES:
        if (methods == "*" or method in methods) and pattern.search(path):
            return roles
    # Anything not listed is admin-only.
    return {"admin"}


def role_for_key(key: str | None, keys: dict[str, str]) -> str | None:
    if not key:
        return None
    for k, role in keys.items():
        if hmac.compare_digest(k, key):
            return role
    return None


def install(app: FastAPI, settings) -> None:
    """Check every request's X-API-Key against the role rules. No keys configured means open (development only)."""

    @app.middleware("http")
    async def require_role(request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        roles = allowed_roles(request.method, request.url.path)
        keys = settings.role_keys
        if not keys:
            request.state.role = "admin"
            return await call_next(request)
        role = role_for_key(request.headers.get("x-api-key"), keys)
        if roles == PUBLIC:
            request.state.role = role or "public"
            return await call_next(request)
        if role is None:
            return JSONResponse({"detail": "missing or invalid X-API-Key"}, status_code=401)
        if role != "admin" and role not in roles:
            return JSONResponse({"detail": f"role '{role}' may not {request.method} {request.url.path}"}, status_code=403)
        request.state.role = role
        return await call_next(request)
