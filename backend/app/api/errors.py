from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.errors import AppError


def install(app: FastAPI) -> None:
    """Answer every application error the way FastAPI answers its own: {"detail": message}."""

    @app.exception_handler(AppError)
    async def app_error(_request: Request, exc: AppError):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)
