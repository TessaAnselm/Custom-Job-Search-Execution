"""Temporal activities: read/write Google Sheets."""

from temporalio import activity
from sheets.client import SheetsClient


@activity.defn(name="write_jobs_to_sheet")
async def write_jobs_to_sheet(jobs: list[dict], status: str) -> list[str]:
    """Bulk-write a list of jobs with the given status. Returns list of row IDs."""
    sheets = SheetsClient()
    sheets.ensure_header()
    row_ids = []
    for job in jobs:
        row_id = sheets.write_job(job, {}, status=status)
        row_ids.append(row_id)
    return row_ids


@activity.defn(name="write_job_to_sheet")
async def write_job_to_sheet(job_with_docs: dict) -> str:
    """Write a single job (with AI docs merged in). Returns row ID."""
    sheets = SheetsClient()
    sheets.ensure_header()
    ai_docs = {
        "resume_filename": job_with_docs.get("resume_filename", ""),
        "cover_note": job_with_docs.get("cover_note", ""),
        "explanation": job_with_docs.get("explanation", ""),
    }
    status = job_with_docs.get("status", "Review")
    return sheets.write_job(job_with_docs, ai_docs, status=status)


@activity.defn(name="update_job_status")
async def update_job_status(row_id: str, status: str, notes: str = "") -> None:
    sheets = SheetsClient()
    sheets.update_status(row_id, status, notes or None)


@activity.defn(name="get_job_status")
async def get_job_status(row_id: str) -> str:
    sheets = SheetsClient()
    return sheets.get_job_status(row_id)
