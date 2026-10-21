"""Large file imports, run in the background.

The upload is copied to disk as it arrives, then read in batches of a few thousand rows. Each
batch is written with the bulk path and committed, so memory stays flat and a failure part-way
keeps every batch already saved (re-running the same file skips references already present).
Progress lives in net_import_jobs, so any worker can report it. The money map is analysed
once, at the end.
"""
from __future__ import annotations

import logging
import os
import tempfile
import threading
from collections.abc import Callable, Iterator

from app.core.config import Settings
from app.core.errors import NotFound, TooLarge
from app.core.timeutil import now
from app.network.application import ingest as service
from app.network.application.analysis import cache
from app.network.application.ports import MissingColumns, NetworkUnitOfWork, UnitOfWorkFactory
from app.network.domain.entities import ImportJob

log = logging.getLogger(__name__)
SPOOL = os.path.join(tempfile.gettempdir(), "theone-imports")
BATCH = 5000


def spool_path(job_id: str) -> str:
    os.makedirs(SPOOL, mode=0o700, exist_ok=True)
    return os.path.join(SPOOL, f"{job_id}.upload")


BatchReader = Callable[..., Iterator]


def out(j: ImportJob) -> dict:
    return {"id": j.id, "created_at": j.created_at.isoformat(), "finished_at": j.finished_at.isoformat() if j.finished_at else None,
            "format": j.fmt, "filename": j.filename, "size_bytes": j.size_bytes, "bytes_read": j.bytes_read, "dry_run": j.dry_run,
            "status": j.status, "rows": j.rows, "valid": j.valid, "transfers_added": j.added, "transfers_skipped": j.skipped,
            "accounts_added": j.accounts_added, "error_count": j.error_count, "errors": j.errors or [], "message": j.message,
            "progress": round(min(1.0, j.bytes_read / j.size_bytes), 3) if j.size_bytes else None}


async def receive(uow: NetworkUnitOfWork, fmt: str, filename: str, dry_run: bool, chunks, s: Settings) -> ImportJob:
    """Copy an upload to disk as it arrives, refusing files above the configured size."""
    job = uow.import_jobs.add(ImportJob(fmt=fmt, filename=filename[:200], dry_run=dry_run))
    uow.commit()
    size, limit = 0, s.network_import_max_mb * 1024 * 1024
    path = spool_path(job.id)
    with open(path, "wb") as f:
        async for chunk in chunks:
            size += len(chunk)
            if size > limit:
                f.close()
                os.remove(path)
                job.status, job.message = "failed", f"file larger than {s.network_import_max_mb} MB"
                uow.commit()
                raise TooLarge(job.message)
            f.write(chunk)
    job.size_bytes = size
    uow.commit()
    return job


def start(new_uow: UnitOfWorkFactory, read_batches: BatchReader, job_id: str, mapping: dict | None,
          default_bank: str | None, s: Settings) -> None:
    threading.Thread(target=run, args=(new_uow, read_batches, job_id, mapping, default_bank, s),
                     name=f"import-{job_id[:8]}", daemon=True).start()


def run(new_uow: UnitOfWorkFactory, read_batches: BatchReader, job_id: str, mapping: dict | None,
        default_bank: str | None, s: Settings) -> None:
    uow = new_uow()
    path = spool_path(job_id)
    try:
        job = uow.import_jobs.get(job_id)
        job.status = "reading"
        uow.commit()
        errors: list[dict] = []
        for res in read_batches(path, job.fmt, mapping, s.network_import_utc_offset_hours, default_bank,
                                BATCH, on_progress=lambda b: setattr(job, "bytes_read", b)):
            job.rows += res.rows
            job.valid += len(res.transfers)
            job.error_count += max(len(res.errors), res.rows - len(res.transfers))
            errors.extend(res.errors[: max(0, 200 - len(errors))])
            if res.transfers and not job.dry_run:
                r = service.ingest_bulk(uow, res.transfers)
                job.added += r["transfers_added"]
                job.skipped += r["transfers_skipped"]
                job.accounts_added += r["accounts_added"]
                for ref in r["same_account"][: max(0, 200 - len(errors))]:
                    errors.append({"row": None, "error": f"transfer {ref} has the same source and destination"})
                job.error_count += len(r["same_account"])
            job.errors = list(errors)
            uow.commit()
        if not job.dry_run and job.added:
            job.status = "analysing"
            uow.commit()
            cache.run(uow)
        if job.rows and not job.valid:
            raise ValueError("no row in the file could be read; see the errors for the first rows")
        job.status, job.finished_at = "done", now()
        job.bytes_read = job.size_bytes
        uow.commit()
    except MissingColumns as e:
        uow.rollback()
        job = uow.import_jobs.get(job_id)
        job.status, job.finished_at = "failed", now()
        job.message = str(e)[:300]
        job.errors = [{"row": 1, "error": f"Expected columns not found: {', '.join(e.missing)}"},
                      {"row": 1, "error": f"Columns in the file: {', '.join(e.found)[:1500]}"}]
        job.error_count = 1
        uow.commit()
    # Keep every batch already saved and report the failure on the job.
    except Exception as e:
        _failed(uow, job_id, e)
    finally:
        uow.close()
        try:
            os.remove(path)
        except OSError:
            pass


def _failed(uow: NetworkUnitOfWork, job_id: str, e: Exception) -> None:
    log.exception("import job %s failed", job_id)
    uow.rollback()
    job = uow.import_jobs.get(job_id)
    if job:
        job.status, job.message, job.finished_at = "failed", f"{type(e).__name__}: {e}"[:300], now()
        uow.commit()


def recent(uow: NetworkUnitOfWork, limit: int = 10) -> list[dict]:
    return [out(j) for j in uow.import_jobs.newest(limit)]


def status(uow: NetworkUnitOfWork, job_id: str) -> dict:
    job = uow.import_jobs.get(job_id)
    if not job:
        raise NotFound("import job not found")
    return out(job)
