"""
Temporal activities: read/write job storage.

Falls back to jobs_local.json when Google Sheets is not configured,
so Temporal mode works out of the box without any cloud setup.
"""

import os
from temporalio import activity
from storage.local import (
    load_local_jobs, save_local_jobs,
    update_local_job_status, get_local_job_status,
)


def _sheets_configured() -> bool:
    return bool(os.getenv("GOOGLE_SHEETS_ID") and os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"))


@activity.defn(name="write_jobs_to_sheet")
async def write_jobs_to_sheet(jobs: list[dict], status: str) -> list[str]:
    """Bulk-write jobs with the given status. Falls back to local JSON if Sheets not configured."""
    if _sheets_configured():
        try:
            from sheets.client import SheetsClient
            sheets = SheetsClient()
            sheets.ensure_header()
            row_ids = []
            for job in jobs:
                row_id = sheets.write_job(job, {}, status=status)
                row_ids.append(row_id)
            return row_ids
        except Exception as e:
            activity.logger.warning(f"Sheets write failed ({e}), falling back to local storage")

    # Local fallback — set status on each job and append to jobs_local.json
    existing = {j["_row_id"]: j for j in load_local_jobs()}
    for job in jobs:
        row_id = job.get("id") or job.get("_row_id", "")
        existing[row_id] = {**job, "_row_id": row_id, "Status": status}
    save_local_jobs(list(existing.values()))
    return [job.get("id") or job.get("_row_id", "") for job in jobs]


@activity.defn(name="write_job_to_sheet")
async def write_job_to_sheet(job_with_docs: dict) -> str:
    """Write a single job (with AI docs). Falls back to local JSON if Sheets not configured."""
    if _sheets_configured():
        try:
            from sheets.client import SheetsClient
            sheets = SheetsClient()
            sheets.ensure_header()
            ai_docs = {
                "resume_filename": job_with_docs.get("resume_filename", ""),
                "cover_note":      job_with_docs.get("cover_note", ""),
                "explanation":     job_with_docs.get("explanation", ""),
            }
            return sheets.write_job(job_with_docs, ai_docs, status=job_with_docs.get("status", "Review"))
        except Exception as e:
            activity.logger.warning(f"Sheets write failed ({e}), falling back to local storage")

    # Local fallback
    row_id = job_with_docs.get("id") or job_with_docs.get("_row_id", "")
    existing = {j["_row_id"]: j for j in load_local_jobs()}
    existing[row_id] = {**job_with_docs, "_row_id": row_id}
    save_local_jobs(list(existing.values()))
    return row_id


@activity.defn(name="update_job_status")
async def update_job_status(row_id: str, status: str, notes: str = "") -> None:
    """Update a job's status. Falls back to local JSON if Sheets not configured."""
    if _sheets_configured():
        try:
            from sheets.client import SheetsClient
            SheetsClient().update_status(row_id, status, notes or None)
            return
        except Exception as e:
            activity.logger.warning(f"Sheets status update failed ({e}), falling back to local storage")

    update_local_job_status(row_id, status, notes)


@activity.defn(name="get_job_status")
async def get_job_status(row_id: str) -> str:
    """Get a job's current status. Falls back to local JSON if Sheets not configured."""
    if _sheets_configured():
        try:
            from sheets.client import SheetsClient
            return SheetsClient().get_job_status(row_id)
        except Exception as e:
            activity.logger.warning(f"Sheets status read failed ({e}), falling back to local storage")

    return get_local_job_status(row_id)
