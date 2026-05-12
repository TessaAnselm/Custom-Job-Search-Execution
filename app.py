"""
Job Search Dashboard — Flask web UI.

Run with:
    pip install flask python-dotenv
    python3 app.py

Open http://localhost:5050
"""

import os
import asyncio
from flask import Flask, render_template, jsonify, request, redirect, url_for
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

DEMO_JOBS = [
    {
        "_row_id": "2", "Date Found": "2026-05-10", "Company": "Cloudflare",
        "Job Title": "Security Engineer, Zero Trust", "Location": "Remote",
        "Salary": "$140,000–$175,000", "Job URL": "https://cloudflare.com/careers",
        "Source": "greenhouse", "Match Score": "88", "Role Type": "IC",
        "Why It Fits": "Strong match on network security and Python skills. Remote role meets location preference. Salary above target.",
        "Resume Version": "resume_Cloudflare_Security_Engineer_abc123.txt",
        "Cover Note Draft": "Your work on protecting ~20% of the web is exactly the scale I want to operate at...",
        "Status": "Review", "Deadline": "", "Contact Name": "", "Referral?": "Unknown",
        "Follow Up Date": "", "Notes": "",
    },
    {
        "_row_id": "3", "Date Found": "2026-05-10", "Company": "Snyk",
        "Job Title": "AppSec Engineer", "Location": "Remote",
        "Salary": "$130,000–$160,000", "Job URL": "https://snyk.io/careers",
        "Source": "lever", "Match Score": "82", "Role Type": "IC",
        "Why It Fits": "Direct title match on AppSec. Snyk is in the preferred DevTools/Security industry. OWASP skills align perfectly.",
        "Resume Version": "resume_Snyk_AppSec_Engineer_def456.txt",
        "Cover Note Draft": "I've been using Snyk for vulnerability scanning in my own projects...",
        "Status": "Review", "Deadline": "", "Contact Name": "", "Referral?": "Unknown",
        "Follow Up Date": "", "Notes": "",
    },
    {
        "_row_id": "4", "Date Found": "2026-05-09", "Company": "Anthropic",
        "Job Title": "Trust & Safety Engineer", "Location": "San Francisco, CA",
        "Salary": "$160,000–$200,000", "Job URL": "https://anthropic.com/careers",
        "Source": "lever", "Match Score": "76", "Role Type": "IC",
        "Why It Fits": "AI/ML security focus is a strong industry match. Salary exceeds target. Title is adjacent to target roles.",
        "Resume Version": "resume_Anthropic_Trust_Safety_ghi789.txt",
        "Cover Note Draft": "Building safe AI systems is one of the most important security challenges of this decade...",
        "Status": "Ready to Apply", "Deadline": "", "Contact Name": "", "Referral?": "Unknown",
        "Follow Up Date": "", "Notes": "",
    },
    {
        "_row_id": "5", "Date Found": "2026-05-09", "Company": "Datadog",
        "Job Title": "Software Engineer, Security Platform", "Location": "Remote",
        "Salary": "$120,000–$150,000", "Job URL": "https://datadog.com/careers",
        "Source": "greenhouse", "Match Score": "71", "Role Type": "IC",
        "Why It Fits": "Security platform role with Python focus. Remote. Salary meets minimum but below target.",
        "Resume Version": "", "Cover Note Draft": "",
        "Status": "Applied", "Deadline": "", "Contact Name": "Jane Smith",
        "Referral?": "No", "Follow Up Date": "2026-05-16", "Notes": "Applied via website",
    },
    {
        "_row_id": "6", "Date Found": "2026-05-08", "Company": "Generic Corp",
        "Job Title": "Junior IT Support", "Location": "Requires Relocation",
        "Salary": "$45,000", "Job URL": "https://example.com/job",
        "Source": "hn_hiring", "Match Score": "22", "Role Type": "",
        "Why It Fits": "Low score: title mismatch, salary below minimum, requires relocation.",
        "Resume Version": "", "Cover Note Draft": "",
        "Status": "Skip", "Deadline": "", "Contact Name": "", "Referral?": "Unknown",
        "Follow Up Date": "", "Notes": "",
    },
]


def get_jobs(status_filter=None, min_score=0):
    try:
        from sheets.client import SheetsClient
        sheets = SheetsClient()
        return sheets.list_jobs(status_filter=status_filter, min_score=min_score)
    except Exception:
        jobs = DEMO_JOBS
        if status_filter:
            jobs = [j for j in jobs if j.get("Status") == status_filter]
        if min_score:
            jobs = [j for j in jobs if int(j.get("Match Score", 0) or 0) >= min_score]
        return jobs


def get_stats():
    try:
        from sheets.client import SheetsClient
        sheets = SheetsClient()
        return sheets.get_stats()
    except Exception:
        stats = {}
        for job in DEMO_JOBS:
            s = job.get("Status", "Unknown")
            stats[s] = stats.get(s, 0) + 1
        return stats


def update_status(row_id, status, notes=""):
    try:
        from sheets.client import SheetsClient
        sheets = SheetsClient()
        sheets.update_status(row_id, status, notes or None)

        # Also signal Temporal if it's running
        try:
            from temporal.workflows.job_search_workflow import JobProcessingWorkflow, ApprovalDecision
            from temporalio.client import Client

            decision_map = {
                "Ready to Apply": ApprovalDecision.APPLY,
                "Skip": ApprovalDecision.SKIP,
                "Tailor Resume": ApprovalDecision.LATER,
            }
            if status in decision_map:
                async def _signal():
                    client = await Client.connect(
                        os.getenv("TEMPORAL_HOST", "localhost:7233"),
                        namespace=os.getenv("TEMPORAL_NAMESPACE", "default"),
                    )
                    handle = client.get_workflow_handle(f"job-{row_id}")
                    await handle.signal(JobProcessingWorkflow.decide, decision_map[status], notes or None)
                asyncio.run(_signal())
        except Exception:
            pass  # Temporal not running — sheet update is enough
    except Exception:
        # Demo mode — just update in-memory list
        for job in DEMO_JOBS:
            if job["_row_id"] == str(row_id):
                job["Status"] = status
                if notes:
                    job["Notes"] = notes
                break


@app.route("/")
def index():
    status_filter = request.args.get("status")
    min_score = int(request.args.get("min_score", 0))
    jobs = get_jobs(status_filter=status_filter, min_score=min_score)
    stats = get_stats()

    using_demo = not (os.getenv("GOOGLE_SHEETS_ID") and os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"))

    return render_template(
        "dashboard.html",
        jobs=jobs,
        stats=stats,
        status_filter=status_filter or "",
        min_score=min_score,
        using_demo=using_demo,
    )


@app.route("/job/<row_id>")
def job_detail(row_id):
    jobs = get_jobs()
    job = next((j for j in jobs if j.get("_row_id") == row_id), None)
    if not job:
        return "Job not found", 404
    return render_template("job_detail.html", job=job)


@app.route("/api/approve", methods=["POST"])
def api_approve():
    data = request.get_json()
    row_id = data.get("row_id")
    action = data.get("action")   # apply | skip | later
    notes = data.get("notes", "")

    status_map = {
        "apply": "Ready to Apply",
        "skip": "Skip",
        "later": "Tailor Resume",
    }
    status = status_map.get(action)
    if not status:
        return jsonify({"error": f"Unknown action: {action}"}), 400

    update_status(row_id, status, notes)
    return jsonify({"ok": True, "row_id": row_id, "status": status})


@app.route("/api/trigger-search", methods=["POST"])
def api_trigger_search():
    try:
        from temporalio.client import Client
        from temporal.workflows.job_search_workflow import JobSearchWorkflow, JobSearchParams
        import uuid

        run_id = str(uuid.uuid4())[:8]
        params = JobSearchParams(run_id=run_id)

        async def _start():
            client = await Client.connect(
                os.getenv("TEMPORAL_HOST", "localhost:7233"),
                namespace=os.getenv("TEMPORAL_NAMESPACE", "default"),
            )
            handle = await client.start_workflow(
                JobSearchWorkflow.run,
                params,
                id=f"job-search-{run_id}",
                task_queue="job-search-queue",
            )
            return handle.id

        workflow_id = asyncio.run(_start())
        return jsonify({"ok": True, "workflow_id": workflow_id, "run_id": run_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "hint": "Make sure Temporal worker is running."}), 500


if __name__ == "__main__":
    print("Job Search Dashboard → http://localhost:5050")
    app.run(debug=True, port=5050)
