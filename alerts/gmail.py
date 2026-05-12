"""Gmail alert — sends job match notifications via SMTP."""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


class GmailAlert:
    def __init__(self):
        self.user = os.environ["GMAIL_USER"]
        self.app_password = os.environ["GMAIL_APP_PASSWORD"]
        self.to = os.getenv("GMAIL_NOTIFY_TO", self.user)

    def send_job_alert(self, job: dict, ai_docs: dict, row_id: str):
        score = job.get("score", "?")
        title = job.get("title", "")
        company = job.get("company", "")
        location = job.get("location", "Remote")
        salary = job.get("salary", "not listed")
        url = job.get("url", "")
        explanation = ai_docs.get("explanation", "")
        cover_note = ai_docs.get("cover_note", "")

        subject = f"[Job Match {score}/100] {title} at {company}"
        body = f"""\
New job match found — {score}/100

{title} at {company}
Location: {location}
Salary: {salary}

Why it fits:
{explanation}

Cover note draft:
{cover_note}

View posting: {url}

Row ID: {row_id}
"""
        self._send(subject, body)

    def send_followup_reminder(self, job: dict, row_id: str):
        title = job.get("title", "")
        company = job.get("company", "")
        subject = f"[Follow-up] {title} at {company}"
        body = f"""\
You applied to {title} at {company} 7 days ago and haven't recorded a response.

Consider following up with your contact or checking the company's application portal.

Row ID: {row_id}
"""
        self._send(subject, body)

    def _send(self, subject: str, body: str):
        msg = MIMEMultipart()
        msg["From"] = self.user
        msg["To"] = self.to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(self.user, self.app_password)
            server.sendmail(self.user, self.to, msg.as_string())
