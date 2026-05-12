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
from flask import Flask, render_template, jsonify, request, Response, redirect
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

PROFILE_PATH = os.path.join(os.path.dirname(__file__), "config", "profile.yaml")
RESUMES_DIR  = os.path.join(os.path.dirname(__file__), "resumes")

_preview_cache: dict = {"jobs": [], "fetched_at": 0.0}
PREVIEW_TTL = 1800  # 30 minutes


async def _fetch_live_preview() -> list[dict]:
    """Pull a live sample from HN Who's Hiring and Built In SF (no auth needed)."""
    import re
    import ssl
    import aiohttp
    import certifi
    today = date.today().isoformat()
    jobs: list[dict] = []

    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)

    def _blank_row(extra: dict) -> dict:
        return {
            "Match Score": "", "Why It Fits": "", "Role Type": "",
            "Deadline": "", "Contact Name": "", "Referral?": "",
            "Follow Up Date": "", "Notes": "",
            "Resume Version": "", "Cover Note Draft": "",
            "Date Found": today,
            "_is_preview": True,
            **extra,
        }

    # ── HN Who's Hiring (find thread via whoishiring user, fetch 20 concurrently) ──
    try:
        item_url = "https://hacker-news.firebaseio.com/v0/item/{}.json"
        user_url = "https://hacker-news.firebaseio.com/v0/user/whoishiring/submitted.json"
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(user_url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                submitted_ids = await r.json()

            # Find the latest "Who is hiring?" thread (not "Who wants to be hired?")
            thread_id = None
            for sid in submitted_ids[:6]:
                async with session.get(item_url.format(sid), timeout=aiohttp.ClientTimeout(total=5)) as r:
                    story = await r.json()
                if "Who is hiring" in (story.get("title") or ""):
                    thread_id = sid
                    kid_ids = story.get("kids", [])[:20]
                    break

            if thread_id:
                async def _fetch_comment(kid_id: int) -> dict | None:
                    try:
                        async with session.get(item_url.format(kid_id), timeout=aiohttp.ClientTimeout(total=5)) as r:
                            c = await r.json()
                        text = c.get("text", "") or ""
                        if not text or c.get("dead") or c.get("deleted"):
                            return None
                        first = re.sub(r"<[^>]+>", "", text.split("<p>")[0]).strip()
                        parts = [p.strip() for p in first.split("|")]
                        company  = parts[0] if parts else "Unknown"
                        title    = parts[1] if len(parts) > 1 else "Software Engineer"
                        location = parts[2] if len(parts) > 2 else "Remote"
                        salary   = next((p for p in parts if "$" in p or "k" in p.lower()), "")
                        return _blank_row({
                            "_row_id": f"hn-{c['id']}",
                            "Company": company, "Job Title": title,
                            "Location": location, "Salary": salary,
                            "Job URL": f"https://news.ycombinator.com/item?id={c['id']}",
                            "Source": "hn_hiring", "Status": "New",
                        })
                    except Exception:
                        return None

                results = await asyncio.gather(*[_fetch_comment(k) for k in kid_ids])
                jobs += [r for r in results if r]
    except Exception:
        pass

    # ── Built In SF ────────────────────────────────────────────────────────────
    try:
        from scrapers.builtin_sf import BuiltInSFScraper
        sf_jobs = await BuiltInSFScraper(keywords=["software engineer"]).fetch()
        for job in sf_jobs[:12]:
            jobs.append(_blank_row({
                "_row_id": f"bisf-{job.id}",
                "Company": job.company, "Job Title": job.title,
                "Location": job.location, "Salary": job.salary,
                "Job URL": job.url,
                "Source": "builtin_sf", "Status": "New",
            }))
    except Exception:
        pass

    return jobs


def get_live_preview_jobs() -> list[dict]:
    import time
    now = time.time()
    if _preview_cache["jobs"] and now - _preview_cache["fetched_at"] < PREVIEW_TTL:
        return _preview_cache["jobs"]
    try:
        jobs = asyncio.run(_fetch_live_preview())
        _preview_cache["jobs"] = jobs
        _preview_cache["fetched_at"] = now
        return jobs
    except Exception:
        return _preview_cache["jobs"]


# ── Helpers ──────────────────────────────────────────────────────────────────

def using_live_data():
    return bool(os.getenv("GOOGLE_SHEETS_ID") and os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"))


def get_jobs(status_filter=None, min_score=0):
    try:
        from sheets.client import SheetsClient
        return SheetsClient().list_jobs(status_filter=status_filter, min_score=min_score)
    except Exception:
        jobs = get_live_preview_jobs()
        if status_filter:
            jobs = [j for j in jobs if j.get("Status") == status_filter]
        if min_score:
            jobs = [j for j in jobs if int(j.get("Match Score") or 0) >= min_score]
        return jobs


def get_stats():
    try:
        from sheets.client import SheetsClient
        return SheetsClient().get_stats()
    except Exception:
        stats: dict[str, int] = {}
        for job in get_live_preview_jobs():
            s = job.get("Status", "Unknown")
            stats[s] = stats.get(s, 0) + 1
        return stats


def load_profile() -> dict:
    if os.path.exists(PROFILE_PATH):
        with open(PROFILE_PATH) as f:
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
    """Extract a complete profile from resume text using the configured AI provider."""
    import json
    from ai.client import complete_sync
    prompt = (
        "You are a career profile parser. Extract a complete job-search profile from this resume.\n"
        "Return JSON only — no explanation, no markdown, no code fences.\n\n"
        "Fields to extract:\n"
        "- name (string)\n"
        "- experience_years (integer — estimate from work history dates)\n"
        "- role_type (string — IC, Manager, or Either)\n"
        "- skills (list of 12-15 technical skills)\n"
        "- target_titles (list of 4-6 job titles to target)\n"
        "- location_preferred (list — infer from current city; include Remote if applicable)\n"
        "- location_hard_no (list — empty unless resume says can't relocate)\n"
        "- salary_minimum (integer USD annual, 0 if unclear)\n"
        "- salary_target (integer USD annual, 0 if unclear)\n"
        "- industries_preferred (list of 3-5 industries)\n"
        "- industries_avoid (list — empty unless clear signals)\n"
        "- summary (2-3 sentence first-person professional summary)\n\n"
        f"Resume:\n{resume_text[:4000]}\n\n"
        "Return valid JSON with exactly these field names."
    )
    raw = complete_sync(prompt, max_tokens=800)
    # Strip any accidental markdown fences
    raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(raw)


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    # First-time users: redirect to profile setup before showing jobs
    if not os.path.exists(PROFILE_PATH) or not load_profile().get("name"):
        return redirect("/profile")
    status_filter = request.args.get("status")
    min_score = int(request.args.get("min_score", 0))
    jobs = get_jobs(status_filter=status_filter, min_score=min_score)
    stats = get_stats()
    live = using_live_data()
    return render_template(
        "dashboard.html",
        jobs=jobs,
        stats=stats,
        status_filter=status_filter or "",
        min_score=min_score,
        using_live=live,
        using_preview=not live,
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
    live = using_live_data()
    return render_template(
        "report.html",
        jobs=jobs,
        stats=stats,
        source_breakdown=source_breakdown,
        generated_at=datetime.now().strftime("%B %d, %Y at %I:%M %p"),
        today=date.today().isoformat(),
        using_preview=not live,
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

        provider = os.getenv("AI_PROVIDER", "openai")
        has_key = {
            "gemini":    bool(os.getenv("GOOGLE_API_KEY")),
            "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
            "groq":      bool(os.getenv("GROQ_API_KEY")),
            "openai":    bool(os.getenv("OPENAI_API_KEY")),
            "ollama":    True,
        }.get(provider, False)

        if has_key:
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
