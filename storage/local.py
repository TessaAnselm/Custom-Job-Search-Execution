"""
Local job storage — shared by Flask (app.py) and Temporal activities.
Persists scored results to jobs_local.json at the project root.
"""

import json
import os
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_LOCAL_PATH = os.path.join(_ROOT, "jobs_local.json")
LOCAL_JOBS_TTL  = 12 * 3600  # 12 hours


def load_local_jobs() -> list[dict]:
    """Return saved jobs; [] if file is missing or older than 12 hours."""
    if not os.path.exists(JOBS_LOCAL_PATH):
        return []
    if time.time() - os.path.getmtime(JOBS_LOCAL_PATH) > LOCAL_JOBS_TTL:
        os.remove(JOBS_LOCAL_PATH)
        return []
    with open(JOBS_LOCAL_PATH) as f:
        return json.load(f)


def save_local_jobs(jobs: list[dict]) -> None:
    with open(JOBS_LOCAL_PATH, "w") as f:
        json.dump(jobs, f, indent=2, default=str)


def update_local_job_status(row_id: str, status: str, notes: str = "") -> None:
    """Update a single job's status in jobs_local.json."""
    jobs = load_local_jobs()
    for job in jobs:
        if job.get("_row_id") == str(row_id):
            job["Status"] = status
            if notes:
                job["Notes"] = notes
            break
    if jobs:
        save_local_jobs(jobs)


def get_local_job_status(row_id: str) -> str:
    """Return the Status field for a job, or 'Unknown' if not found."""
    for job in load_local_jobs():
        if job.get("_row_id") == str(row_id):
            return job.get("Status", "Unknown")
    return "Unknown"
