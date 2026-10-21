"""Getting bank data in: pushed transfers, fraud reports and file imports (small files inline, large
NIP and CSV files as background jobs)."""
from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile

from app.api.deps import get_nibss, get_uow, new_uow
from app.core.config import Settings, get_settings
from app.core.errors import Invalid, NotFound, TooLarge
from app.network.api.schemas import IngestIn, ReportIn
from app.network.application import import_jobs, ingest as ingestion, queries
from app.network.infrastructure import file_formats

router = APIRouter()

IMPORT_FORMATS = {"csv", "nip", "pacs008", "obn_accounts", "obn_statement"}
INLINE_MAX_BYTES = 50 * 1024 * 1024


def _mapping(raw: str | None) -> dict | None:
    try:
        return json.loads(raw) if raw else None
    except ValueError as exc:
        raise Invalid(f"mapping is not valid JSON: {exc}") from exc


async def _chunks(file: UploadFile):
    while chunk := await file.read(1 << 20):
        yield chunk


@router.post("/ingest")
def ingest(body: IngestIn, background: BackgroundTasks, uow=Depends(get_uow), nibss=Depends(get_nibss),
           s: Settings = Depends(get_settings)):
    """Upsert accounts (with hashed identifiers) and append transfers. Idempotent on transfer reference."""
    out = ingestion.ingest(uow, [a.model_dump() for a in body.accounts], [t.model_dump() for t in body.transfers], s, nibss)
    refs = out.pop("_refs")
    background.add_task(queries.refresh, new_uow, refs if not body.accounts else None)
    return out


@router.post("/reports", status_code=201)
def report(body: ReportIn, background: BackgroundTasks, uow=Depends(get_uow)):
    r = ingestion.add_report(uow, body.kind, body.bank_code, body.account_no, body.transfer_reference, body.note, body.reporter)
    background.add_task(queries.refresh, new_uow)
    return {"id": r.id, "kind": r.kind, "account_id": r.account_id}


@router.post("/import/{fmt}/job")
async def import_job(fmt: str, file: UploadFile = File(...), mapping: str | None = Form(default=None),
                     bank_code: str | None = Form(default=None), dry_run: bool = Form(default=False),
                     uow=Depends(get_uow), s: Settings = Depends(get_settings)):
    """Import a large NIP or CSV file in the background. Returns a job to poll for progress."""
    if fmt not in file_formats.STREAMABLE:
        raise Invalid(f"large-file import supports {sorted(file_formats.STREAMABLE)}; other formats use /network/import/{fmt}")
    cols = _mapping(mapping)
    job = await import_jobs.receive(uow, fmt, file.filename or "upload", dry_run, _chunks(file), s)
    import_jobs.start(new_uow, file_formats.iter_file_batches, job.id, cols, bank_code, s)
    return import_jobs.out(job)


@router.get("/import/jobs")
def import_jobs_list(uow=Depends(get_uow)):
    return import_jobs.recent(uow)


@router.get("/import/jobs/{job_id}")
def import_job_status(job_id: str, uow=Depends(get_uow)):
    return import_jobs.status(uow, job_id)


@router.post("/import/{fmt}")
async def import_file(
    fmt: str,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    mapping: str | None = Form(default=None, description='JSON column mapping, e.g. {"reference": "TxnRef"}'),
    bank_code: str | None = Form(default=None, description="bank code for OBN files or CSVs without bank columns"),
    account_no: str | None = Form(default=None, description="account for an OBN statement without accountNumber"),
    dry_run: bool = Form(default=False),
    uow=Depends(get_uow),
    nibss=Depends(get_nibss),
    s: Settings = Depends(get_settings),
):
    """Import bank data. Every bad row is reported with its row number; good rows still load."""
    if fmt not in IMPORT_FORMATS:
        raise NotFound(f"format must be one of {sorted(IMPORT_FORMATS)}")
    raw = await file.read()
    if len(raw) > INLINE_MAX_BYTES:
        raise TooLarge("file larger than 50 MB: NIP and CSV files of any size import in the background "
                       "(POST /network/import/{fmt}/job; the console does this automatically)")
    text = raw.decode("utf-8-sig", errors="replace")
    cols = _mapping(mapping)
    off = s.network_import_utc_offset_hours
    home = bank_code or s.network_home_bank_code
    if fmt == "csv":
        res = file_formats.parse_csv(text, cols, off, default_bank=bank_code)
    elif fmt == "nip":
        res = file_formats.parse_nip(text, cols, off)
    elif fmt == "pacs008":
        res = file_formats.parse_pacs008(text, off)
    elif fmt == "obn_accounts":
        res = file_formats.parse_obn_accounts(text, home, off)
    else:
        res = file_formats.parse_obn_statement(text, home, account_no, off)
    out = {"format": fmt, "rows": res.rows, "valid": len(res.transfers) + len(res.accounts) + len(res.statements),
           "errors": res.errors, "dry_run": dry_run}
    if not dry_run:
        if res.accounts or res.transfers:
            loaded = ingestion.ingest(uow, res.accounts, res.transfers, s, nibss)
            loaded.pop("_refs", None)
            out |= loaded
        if res.statements:
            out |= ingestion.ingest_statements(uow, res.statements)
        background.add_task(queries.refresh, new_uow)
    return out
