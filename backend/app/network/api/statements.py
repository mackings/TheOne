"""Checking one customer's statement, and adding it to the money map."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import get_nibss, get_uow
from app.core.config import Settings, get_settings
from app.core.errors import Forbidden, Invalid, TooLarge, Unauthorized
from app.network.api.schemas import StatementImportIn, StatementIn
from app.network.application import statements
from app.network.domain.statements import pdf_text

router = APIRouter()

MAX_BYTES = 15_000_000


@router.post("/statement/check")
def check_statement(body: StatementIn):
    """Mule checks and a payment-check replay for one pasted statement. Nothing is stored."""
    return statements.check_text(body.text)


@router.post("/statement/check-file")
async def check_statement_file(file: UploadFile = File(...), password: str | None = Form(None)):
    """The same check for an uploaded PDF, CSV or text statement. The text is returned so the console
    can add it to the money map later; nothing is stored."""
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise TooLarge("statements up to 15 MB")
    try:
        text = pdf_text(data, password) if data[:5] == b"%PDF-" else data.decode("utf-8-sig", errors="replace")
    except PermissionError as e:
        raise (Forbidden(str(e)) if password else Unauthorized(str(e))) from e
    except ValueError as e:
        raise Invalid(str(e)) from e
    return {**statements.check_text(text), "text": text}


@router.post("/statement/import")
def import_statement(body: StatementImportIn, uow=Depends(get_uow), nibss=Depends(get_nibss), s: Settings = Depends(get_settings)):
    """Add a statement's transfers to the money map and re-analyse, so rings can form from statements."""
    return statements.import_statement(uow, body.text, body.bank_code, s, nibss)
