"""
Temporal activities: read/write job storage.

Falls back to jobs_local.json when Google Sheets is not configured,
so Temporal mode works out of the box without any cloud setup.
"""

import os
from datetime import date
from temporalio import activity
from storage.local import (
    load_local_jobs, save_local_jobs,
    update_local_job_status, get_local_job_status,
)


def _sheets_configured() -> bool:
    sheets_id = os.getenv("GOOGLE_SHEETS_ID", "")
    sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    return bool(
        sheets_id and sa_path
        and sheets_id != "your-spreadsheet-id-here"
        and os.path.exists(sa_path)
    )


def _to_local_row(job: dict, status: str) -> dict:
    """Normalize a raw job dict (lowercase keys) to the dashboard's Title Case schema."""
    row_id = job.get("id") or job.get("_row_id", "")
    return {
        "_row_id":          row_id,
        "Date Found":       job.get("Date Found") or date.today().isoformat(),
        "Company":          job.get("Company") or job.get("company", ""),
        "Job Title":        job.get("Job Title") or job.get("title", ""),
        "Location":         job.get("Location") or job.get("location", ""),
        "Salary":           job.get("Salary") or job.get("salary", ""),
        "Job URL":          job.get("Job URL") or job.get("url", ""),
        "Source":           job.get("Source") or job.get("source", ""),
        "Match Score":      str(job.get("Match Score") or job.get("score", 0)),
        "Why It Fits":      job.get("Why It Fits") or job.get("explanation", ""),
        "Status":           status,
        "Role Type":        job.get("Role Type") or job.get("role_type", ""),
        "Deadline":         job.get("Deadline") or job.get("deadline", ""),
        "Contact Name":     job.get("Contact Name") or job.get("contact_name", ""),
        "Referral?":        job.get("Referral?", ""),
        "Follow Up Date":   job.get("Follow Up Date", ""),
        "Notes":            job.get("Notes", ""),
        "Resume Version":   job.get("Resume Version") or job.get("resume_filename", ""),
        "Cover Note Draft": job.get("Cover Note Draft") or job.get("cover_note", ""),
        "_is_preview":      False,
    }


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

    existing = {j["_row_id"]: j for j in load_local_jobs()}
    for job in jobs:
        row = _to_local_row(job, status)
        existing[row["_row_id"]] = row
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

    status = job_with_docs.get("status", "Review")
    row = _to_local_row(job_with_docs, status)
    existing = {j["_row_id"]: j for j in load_local_jobs()}
    existing[row["_row_id"]] = row
    save_local_jobs(list(existing.values()))
    return row["_row_id"]


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
