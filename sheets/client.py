"""Google Sheets client — read/write jobs and update statuses."""

import os
import json
from datetime import datetime
from typing import Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Column order must match the README schema
COLUMNS = [
    "Date Found", "Company", "Job Title", "Location", "Salary",
    "Job URL", "Source", "Match Score", "Role Type", "Why It Fits",
    "Resume Version", "Cover Note Draft", "Status", "Deadline",
    "Contact Name", "Referral?", "Follow Up Date", "Notes",
]

HEADER_ROW = 1
DATA_START_ROW = 2


class SheetsClient:
    def __init__(self):
        self.spreadsheet_id = os.environ["GOOGLE_SHEETS_ID"]
        creds = self._load_credentials()
        service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        self.sheet = service.spreadsheets()

    def _load_credentials(self) -> Credentials:
        json_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if json_path and os.path.exists(json_path):
            return Credentials.from_service_account_file(json_path, scopes=SCOPES)
        # Fallback: inline JSON in env var
        raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_INLINE", "")
        if raw:
            info = json.loads(raw)
            return Credentials.from_service_account_info(info, scopes=SCOPES)
        raise RuntimeError("No Google service account credentials found.")

    def ensure_header(self):
        """Write the header row if the sheet is empty."""
        result = self.sheet.values().get(
            spreadsheetId=self.spreadsheet_id,
            range="Sheet1!A1:R1",
        ).execute()
        if not result.get("values"):
            self.sheet.values().update(
                spreadsheetId=self.spreadsheet_id,
                range="Sheet1!A1",
                valueInputOption="RAW",
                body={"values": [COLUMNS]},
            ).execute()

    def get_existing_urls(self) -> set[str]:
        """Return all job URLs already in the sheet for deduplication."""
        result = self.sheet.values().get(
            spreadsheetId=self.spreadsheet_id,
            range="Sheet1!F:F",  # Job URL column
        ).execute()
        rows = result.get("values", [])
        return {row[0] for row in rows if row}

    def write_job(self, job: dict, ai_docs: dict, status: str = "New") -> str:
        """Append a job row. Returns a row_id (1-based row number as string)."""
        row = [
            datetime.now().strftime("%Y-%m-%d"),
            job.get("company", ""),
            job.get("title", ""),
            job.get("location", ""),
            job.get("salary", ""),
            job.get("url", ""),
            job.get("source", ""),
            str(job.get("score", "")),
            job.get("role_type", ""),
            ai_docs.get("explanation", job.get("explanation", "")),
            ai_docs.get("resume_filename", ""),
            ai_docs.get("cover_note", ""),
            status,
            job.get("deadline", ""),
            job.get("contact_name", ""),
            job.get("referral", "Unknown"),
            "",
            "",
        ]
        result = self.sheet.values().append(
            spreadsheetId=self.spreadsheet_id,
            range="Sheet1!A:R",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()

        updated_range = result["updates"]["updatedRange"]
        # Extract row number from range like "Sheet1!A5:R5"
        row_num = updated_range.split("!")[1].split(":")[0].lstrip("A")
        return row_num

    def update_status(self, row_id: str, status: str, notes: Optional[str] = None):
        """Update the Status (col M) and optionally Notes (col R) for a row."""
        row = int(row_id)
        self.sheet.values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f"Sheet1!M{row}",
            valueInputOption="RAW",
            body={"values": [[status]]},
        ).execute()
        if notes:
            self.sheet.values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"Sheet1!R{row}",
                valueInputOption="RAW",
                body={"values": [[notes]]},
            ).execute()

    def get_job_status(self, row_id: str) -> str:
        row = int(row_id)
        result = self.sheet.values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"Sheet1!M{row}",
        ).execute()
        values = result.get("values", [[""]])
        return values[0][0] if values else ""

    def list_jobs(self, status_filter: Optional[str] = None, min_score: int = 0) -> list[dict]:
        result = self.sheet.values().get(
            spreadsheetId=self.spreadsheet_id,
            range="Sheet1!A:R",
        ).execute()
        rows = result.get("values", [])
        if not rows or len(rows) < 2:
            return []

        headers = rows[0]
        jobs = []
        for i, row in enumerate(rows[1:], start=DATA_START_ROW):
            padded = row + [""] * (len(headers) - len(row))
            record = dict(zip(headers, padded))
            record["_row_id"] = str(i)

            if status_filter and record.get("Status") != status_filter:
                continue
            try:
                score = int(record.get("Match Score", 0) or 0)
            except ValueError:
                score = 0
            if score < min_score:
                continue
            jobs.append(record)
        return jobs

    def get_stats(self) -> dict[str, int]:
        jobs = self.list_jobs()
        stats: dict[str, int] = {}
        for job in jobs:
            s = job.get("Status", "Unknown")
            stats[s] = stats.get(s, 0) + 1
        return stats
