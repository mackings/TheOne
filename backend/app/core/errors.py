"""Errors raised by the domain and application layers. They know nothing about HTTP: the API maps
each status to a response of the form {"detail": message}."""
from __future__ import annotations


class AppError(Exception):
    status = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class Invalid(AppError):
    status = 422


class NotFound(AppError, LookupError):
    status = 404


class Conflict(AppError):
    status = 409


class Gone(AppError):
    status = 410


class Unauthorized(AppError):
    status = 401


class Forbidden(AppError):
    status = 403


class TooLarge(AppError):
    status = 413


class Unsupported(AppError):
    status = 415


class Upstream(AppError):
    """A system TheOne depends on (the bank, NIBSS, the assistant model) failed or refused."""
    status = 502


class Unavailable(AppError):
    status = 503
