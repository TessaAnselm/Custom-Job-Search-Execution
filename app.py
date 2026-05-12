"""
Job Search Dashboard — Flask web UI.

Run with:
    pip install flask python-dotenv pypdf2
    python3 app.py

Open http://localhost:5050
"""

import os
import io
import csv
import asyncio
import yaml
from datetime import datetime, date
from flask import Flask, render_template, jsonify, request, Response
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

PROFILE_PATH = os.path.join(os.path.dirname(__file__), "config", "profile.yaml")
RESUMES_DIR  = os.path.join(os.path.dirname(__file__), "resumes")

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


# ── Helpers ──────────────────────────────────────────────────────────────────

def using_live_data():
    return bool(os.getenv("GOOGLE_SHEETS_ID") and os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"))


def get_jobs(status_filter=None, min_score=0):
    try:
        from sheets.client import SheetsClient
        return SheetsClient().list_jobs(status_filter=status_filter, min_score=min_score)
    except Exception:
        jobs = list(DEMO_JOBS)
        if status_filter:
            jobs = [j for j in jobs if j.get("Status") == status_filter]
        if min_score:
            jobs = [j for j in jobs if int(j.get("Match Score", 0) or 0) >= min_score]
        return jobs


def get_stats():
    try:
        from sheets.client import SheetsClient
        return SheetsClient().get_stats()
    except Exception:
        stats = {}
        for job in DEMO_JOBS:
            s = job.get("Status", "Unknown")
            stats[s] = stats.get(s, 0) + 1
        return stats


def load_profile() -> dict:
    if os.path.exists(PROFILE_PATH):
        with open(PROFILE_PATH) as f:
            return yaml.safe_load(f) or {}
    example = PROFILE_PATH + ".example"
    if os.path.exists(example):
        with open(example) as f:
            return yaml.safe_load(f) or {}
    return {}


def save_profile(data: dict):
    os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
    with open(PROFILE_PATH, "w") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def update_status(row_id, status, notes=""):
    try:
        from sheets.client import SheetsClient
        SheetsClient().update_status(row_id, status, notes or None)
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
            pass
    except Exception:
        for job in DEMO_JOBS:
            if job["_row_id"] == str(row_id):
                job["Status"] = status
                if notes:
                    job["Notes"] = notes
                break


def resume_path_for_job(job: dict) -> str | None:
    filename = job.get("Resume Version", "")
    if filename:
        path = os.path.join(RESUMES_DIR, filename)
        if os.path.exists(path):
            return path
    return None


def extract_text_from_upload(file_storage) -> str:
    filename = file_storage.filename.lower()
    raw = file_storage.read()
    if filename.endswith(".pdf"):
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(raw))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            return raw.decode("utf-8", errors="ignore")
    return raw.decode("utf-8", errors="ignore")


def gpt_extract_profile(resume_text: str) -> dict:
    """Use OpenAI to extract a complete profile from resume text."""
    import json
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    prompt = f"""You are a career profile parser. Extract a complete job-search profile from this resume.
Return JSON only — no explanation, no markdown.

Extract these fields:
- name (string — full name from the resume header)
- experience_years (integer — total years of professional experience, estimate from dates)
- role_type (string — "IC" if individual contributor, "Manager" if they managed people, "Either" if both)
- skills (list of strings — top 12-15 technical skills, tools, languages, frameworks)
- target_titles (list of 4-6 strings — job titles this person should target based on their background)
- location_preferred (list of strings — infer from their current city; always include "Remote" if their work history includes remote roles)
- location_hard_no (list of strings — leave empty unless resume explicitly says they can't relocate)
- salary_minimum (integer — conservative estimate in USD annual based on experience level and tech stack; 0 if unclear)
- salary_target (integer — optimistic but realistic USD annual target; 0 if unclear)
- industries_preferred (list of 3-5 strings — industries matching their background and likely interests)
- industries_avoid (list of strings — leave empty unless resume gives clear signals)
- summary (string — 2-3 sentence professional summary written in first person, based on their actual experience)

Resume:
{resume_text[:4000]}

Return valid JSON matching exactly these field names."""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    status_filter = request.args.get("status")
    min_score = int(request.args.get("min_score", 0))
    jobs = get_jobs(status_filter=status_filter, min_score=min_score)
    stats = get_stats()
    return render_template(
        "dashboard.html",
        jobs=jobs,
        stats=stats,
        status_filter=status_filter or "",
        min_score=min_score,
        using_demo=not using_live_data(),
    )


@app.route("/job/<row_id>")
def job_detail(row_id):
    jobs = get_jobs()
    job = next((j for j in jobs if j.get("_row_id") == row_id), None)
    if not job:
        return "Job not found", 404
    resume_content = ""
    path = resume_path_for_job(job)
    if path:
        with open(path) as f:
            resume_content = f.read()
    return render_template("job_detail.html", job=job, resume_content=resume_content)


@app.route("/profile")
def profile_page():
    return render_template("profile.html", profile=load_profile())


@app.route("/report")
def report():
    all_jobs = get_jobs()
    tracked_statuses = {"Applied", "Follow Up", "Interview", "Rejected", "Ready to Apply", "Offer"}
    jobs = [j for j in all_jobs if j.get("Status") in tracked_statuses]
    jobs.sort(key=lambda j: j.get("Date Found", ""), reverse=True)

    applied_statuses = {"Applied", "Follow Up", "Interview", "Rejected", "Offer"}
    applied = [j for j in all_jobs if j.get("Status") in applied_statuses]
    interviews = [j for j in all_jobs if j.get("Status") == "Interview"]
    pending_followup = [j for j in all_jobs if j.get("Status") == "Follow Up"]
    response_rate = f"{int(len(interviews) / len(applied) * 100)}%" if applied else "—"

    scores = [int(j.get("Match Score", 0) or 0) for j in applied if j.get("Match Score")]
    avg_score = str(int(sum(scores) / len(scores))) if scores else "—"

    source_breakdown: dict[str, int] = {}
    for j in applied:
        s = j.get("Source", "unknown")
        source_breakdown[s] = source_breakdown.get(s, 0) + 1
    source_breakdown = dict(sorted(source_breakdown.items(), key=lambda x: x[1], reverse=True))

    stats = {
        "total_tracked": len(all_jobs),
        "applied": len(applied),
        "interviews": len(interviews),
        "response_rate": response_rate,
        "avg_score": avg_score,
        "pending_followup": len(pending_followup),
    }
    return render_template(
        "report.html",
        jobs=jobs,
        stats=stats,
        source_breakdown=source_breakdown,
        generated_at=datetime.now().strftime("%B %d, %Y at %I:%M %p"),
        today=date.today().isoformat(),
    )


@app.route("/report/export")
def report_export():
    all_jobs = get_jobs()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "Date Found", "Company", "Job Title", "Location", "Salary",
        "Match Score", "Source", "Status", "Contact Name",
        "Follow Up Date", "Notes", "Job URL",
    ])
    writer.writeheader()
    for job in all_jobs:
        writer.writerow({k: job.get(k, "") for k in writer.fieldnames})
    filename = f"job-report-{date.today().isoformat()}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── API ───────────────────────────────────────────────────────────────────────

@app.route("/api/approve", methods=["POST"])
def api_approve():
    data = request.get_json()
    row_id = data.get("row_id")
    action = data.get("action")
    notes = data.get("notes", "")
    status_map = {"apply": "Ready to Apply", "skip": "Skip", "later": "Tailor Resume"}
    status = status_map.get(action)
    if not status:
        return jsonify({"error": f"Unknown action: {action}"}), 400
    update_status(row_id, status, notes)
    return jsonify({"ok": True, "row_id": row_id, "status": status})


@app.route("/api/save-profile", methods=["POST"])
def api_save_profile():
    try:
        data = request.get_json()
        save_profile(data)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/upload-resume", methods=["POST"])
def api_upload_resume():
    if "resume" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400
    f = request.files["resume"]
    try:
        text = extract_text_from_upload(f)
        extracted = {"base_resume": text.strip()}

        if os.getenv("OPENAI_API_KEY"):
            structured = gpt_extract_profile(text)
            extracted.update(structured)

        # Build and save a complete profile.yaml immediately
        profile = _build_profile_from_extracted(extracted, text)
        save_profile(profile)

        return jsonify({"ok": True, "extracted": extracted, "profile": profile})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _build_profile_from_extracted(extracted: dict, raw_resume_text: str) -> dict:
    """Map GPT-extracted fields into the profile.yaml schema."""
    return {
        "name": extracted.get("name", ""),
        "experience_years": extracted.get("experience_years", 0),
        "role_type": extracted.get("role_type", "IC"),
        "target_titles": extracted.get("target_titles", []),
        "skills": extracted.get("skills", []),
        "location": {
            "preferred": extracted.get("location_preferred", ["Remote"]),
            "hard_no":   extracted.get("location_hard_no", []),
        },
        "salary": {
            "minimum": extracted.get("salary_minimum", 0),
            "target":  extracted.get("salary_target", 0),
        },
        "industries": {
            "preferred": extracted.get("industries_preferred", []),
            "avoid":     extracted.get("industries_avoid", []),
        },
        "scoring_weights": {
            "title_match":    0.30,
            "skills_match":   0.25,
            "salary_match":   0.20,
            "location_match": 0.15,
            "industry_match": 0.10,
        },
        "minimum_score": 65,
        "base_resume": extracted.get("summary", "") + "\n\n" + raw_resume_text.strip(),
    }


@app.route("/api/save-resume/<row_id>", methods=["POST"])
def api_save_resume(row_id):
    data = request.get_json()
    content = data.get("content", "")
    try:
        jobs = get_jobs()
        job = next((j for j in jobs if j.get("_row_id") == row_id), None)
        if not job:
            return jsonify({"ok": False, "error": "Job not found"}), 404

        os.makedirs(RESUMES_DIR, exist_ok=True)
        existing = job.get("Resume Version", "")
        if existing:
            filename = existing
        else:
            safe_co = "".join(c if c.isalnum() else "_" for c in job.get("Company", "company"))
            safe_ti = "".join(c if c.isalnum() else "_" for c in job.get("Job Title", "role"))
            filename = f"resume_{safe_co}_{safe_ti}_{row_id}.txt"

        path = os.path.join(RESUMES_DIR, filename)
        with open(path, "w") as out:
            out.write(content)
        return jsonify({"ok": True, "filename": filename})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/generate-resume/<row_id>", methods=["POST"])
def api_generate_resume(row_id):
    try:
        jobs = get_jobs()
        job = next((j for j in jobs if j.get("_row_id") == row_id), None)
        if not job:
            return jsonify({"ok": False, "error": "Job not found"}), 404

        profile = load_profile()
        if not profile.get("base_resume"):
            return jsonify({"ok": False, "error": "No base resume in your profile. Go to Profile and add it first."}), 400

        from ai.resume_tailor import ResumeTailor
        tailor = ResumeTailor()

        async def _gen():
            return await tailor.tailor(job, profile)

        content = asyncio.run(_gen())
        return jsonify({"ok": True, "content": content})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


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
                JobSearchWorkflow.run, params,
                id=f"job-search-{run_id}", task_queue="job-search-queue",
            )
            return handle.id

        workflow_id = asyncio.run(_start())
        return jsonify({"ok": True, "workflow_id": workflow_id, "run_id": run_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "hint": "Make sure Temporal worker is running."}), 500


if __name__ == "__main__":
    print("Job Search Dashboard → http://localhost:5050")
    app.run(debug=True, port=5050)
