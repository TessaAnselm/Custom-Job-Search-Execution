"""
Job Search Dashboard — Flask web UI.

Run with:
    pip install flask python-dotenv pypdf2
    python3 app.py

Open http://localhost:5050
"""

import os
import io
import re
import csv
import asyncio
import yaml
from datetime import datetime, date
from flask import Flask, render_template, jsonify, request, Response, redirect
from dotenv import load_dotenv
from utils.search_config import get_local_region, build_search_config
from storage.local import (
    load_local_jobs, save_local_jobs,
    update_local_job_status, get_local_job_status,
    JOBS_LOCAL_PATH,
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

PROFILE_PATH = os.path.join(os.path.dirname(__file__), "config", "profile.yaml")
RESUMES_DIR  = os.path.join(os.path.dirname(__file__), "resumes")



# ── Helpers ──────────────────────────────────────────────────────────────────

def using_live_data():
    return bool(os.getenv("GOOGLE_SHEETS_ID") and os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"))


def get_jobs(status_filter=None):
    try:
        from sheets.client import SheetsClient
        return SheetsClient().list_jobs(status_filter=status_filter)
    except Exception:
        jobs = load_local_jobs()
        if status_filter:
            jobs = [j for j in jobs if j.get("Status") == status_filter]
        return jobs


def get_stats():
    try:
        from sheets.client import SheetsClient
        return SheetsClient().get_stats()
    except Exception:
        stats: dict[str, int] = {}
        for job in load_local_jobs():
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



def _location_score(location: str, region: dict) -> int:
    """1 if job location matches local region, 0 otherwise."""
    loc = location.lower()
    abbr = region["abbr"]
    # Detect explicit region restrictions
    is_eu_only   = bool(re.search(r'\beu only\b|\(eu\b|europe only|remote.*eu only|\bemea\b', loc))
    is_us_only   = bool(re.search(r'\bus only\b|north america only', loc))
    is_asia_only = bool(re.search(r'\basia only\b|\bapac\b|asia pacific only', loc))
    is_us_region = abbr in ("PT", "CT/MT", "ET")
    is_eu_region = abbr in ("GMT", "CET")
    if is_eu_only and is_us_region:
        return 0
    if is_us_only and is_eu_region:
        return 0
    if is_asia_only and (is_us_region or is_eu_region):
        return 0
    # Use word-boundary matching for short ambiguous keywords (us, sf, uk, eu)
    # to avoid matching "us" inside "austin", "various", "futo", etc.
    for kw in region["keywords"]:
        if len(kw) <= 3:
            if re.search(rf'\b{re.escape(kw)}\b', loc):
                return 1
        else:
            if kw in loc:
                return 1
    return 0


# Broad list of non-US countries, regions, and geographic qualifiers.
# Intentionally includes Canada because most Canadian roles cannot be filled by US workers.
_NON_US_GEO = re.compile(
    r'\b('
    # Europe
    r'uk|united kingdom|england|scotland|wales|ireland|'
    r'france|germany|spain|portugal|italy|netherlands|belgium|'
    r'switzerland|austria|sweden|norway|denmark|finland|'
    r'poland|czech republic|czechia|hungary|romania|ukraine|russia|'
    r'europe|eu\b|emea|northern europe|western europe|eastern europe|southern europe|'
    r'berlin|amsterdam|paris|london|dublin|madrid|barcelona|warsaw|'
    r'prague|stockholm|helsinki|oslo|copenhagen|vienna|zurich|zürich|'
    r'brussels|lisbon|athens|budapest|bucharest|'
    # Asia-Pacific
    r'india|japan|china|korea|taiwan|hong kong|singapore|'
    r'indonesia|malaysia|philippines|vietnam|thailand|myanmar|'
    r'pakistan|bangladesh|sri lanka|nepal|'
    r'australia|new zealand|sydney|melbourne|'
    r'apac|asia|southeast asia|south asia|east asia|asia pacific|'
    r'tokyo|beijing|shanghai|seoul|taipei|jakarta|manila|bangkok|hanoi|'
    r'mumbai|bangalore|delhi|hyderabad|chennai|pune|'
    # Canada (remote Canada ≠ remote US for employment purposes)
    r'canada|british columbia|ontario|alberta|quebec|toronto|vancouver|'
    # Middle East / Africa / LatAm
    r'israel|tel aviv|dubai|uae|saudi arabia|'
    r'south africa|cape town|nigeria|kenya|'
    r'brazil|mexico|argentina|colombia|latin america|south america'
    r')\b',
    re.IGNORECASE,
)

# Explicit US-only work authorization signals
_US_GEO = re.compile(
    r'\b(united states|u\.s\.a?\.?|san francisco|california|new york|nyc|'
    r'seattle|bay area|silicon valley|boston|austin|denver|chicago|'
    r'los angeles|portland|atlanta|texas|washington state|'
    r'north america(?!\s+only)|anywhere in (the\s+)?(us|usa|united states)|'
    r'us\s*only|usa\s*only|remote\s*[-–—(]?\s*(us|usa|united states)\b'
    r')\b',
    re.IGNORECASE,
)

_EU_ONLY = re.compile(
    r'\beu only\b|\(eu\)|\beurope only\b|\bemea\b|\buk only\b',
    re.IGNORECASE,
)
_ASIA_ONLY = re.compile(r'\bapac\b|\basia only\b|\basia pacific only\b', re.IGNORECASE)

_JUNIOR_TITLES = re.compile(
    r'\bintern\b|\binternship\b|\bentry.?level\b|\bjunior\b|\bjr\b', re.IGNORECASE
)
_SENIOR_ONLY_TITLES = re.compile(
    r'\bvp\b|\bvice president\b|\bc[est]o\b|\bchief\b|\bpresident\b', re.IGNORECASE
)
_DIRECTOR_TITLES = re.compile(r'\bdirector\b|\bhead of\b', re.IGNORECASE)


def _is_location_applicable(location: str, region: dict) -> bool:
    """Return False for jobs that are clearly in a different region than the user."""
    loc = location.lower()
    abbr = region["abbr"]
    is_us_region = abbr in ("PT", "CT/MT", "ET")
    is_eu_region = abbr in ("GMT", "CET")

    if is_us_region:
        if _EU_ONLY.search(loc) or _ASIA_ONLY.search(loc):
            return False
        # Has a non-US geographic name — only keep if a US signal is also present
        # (e.g., "Remote (US or UK)" is fine; "Remote - Poland" is not)
        if _NON_US_GEO.search(loc) and not _US_GEO.search(loc):
            return False
    elif is_eu_region:
        if _ASIA_ONLY.search(loc):
            return False
        if re.search(r'\bus only\b|north america only', loc, re.IGNORECASE):
            return False

    return True


def _is_level_applicable(title: str, experience_years: int) -> bool:
    """Return False for job titles that are clearly too junior or too senior."""
    if experience_years >= 3 and _JUNIOR_TITLES.search(title):
        return False
    if experience_years < 8 and _SENIOR_ONLY_TITLES.search(title):
        return False
    if experience_years < 6 and _DIRECTOR_TITLES.search(title):
        return False
    return True


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
        # Update local results file when Sheets is not configured
        local = load_local_jobs()
        for job in local:
            if job["_row_id"] == str(row_id):
                job["Status"] = status
                if notes:
                    job["Notes"] = notes
                break
        if local:
            save_local_jobs(local)


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




async def _run_standalone_search() -> list[dict]:
    """Scrape all enabled sources + score — no Temporal or Google Sheets required."""
    import ssl, certifi, aiohttp
    from scoring.scorer import JobScorer

    profile = load_profile()
    if not profile.get("name"):
        raise ValueError("Set up your profile first before running a search.")

    min_score = profile.get("minimum_score", 65)

    # Build all search terms from the profile — no hardcoded keywords anywhere
    sc = build_search_config(profile)
    queries        = sc["queries"]
    tags           = sc["tags"]
    title_keywords = sc["title_keywords"]
    location       = sc["location"]

    print(f"\n[search] queries={queries}")
    print(f"[search] tags={tags} | location={location}")

    # Force fresh data
    if os.path.exists(JOBS_LOCAL_PATH):
        os.remove(JOBS_LOCAL_PATH)

    # ── Load sources.yaml ─────────────────────────────────────────────────────
    sources_path = os.path.join(os.path.dirname(__file__), "config", "sources.yaml")
    with open(sources_path) as f:
        sources_cfg = yaml.safe_load(f).get("sources", [])

    ssl_ctx  = ssl.create_default_context(cafile=certifi.where())
    scrapers = []
    for src in sources_cfg:
        if not src.get("enabled", True):
            continue
        t = src.get("type")
        try:
            if t == "greenhouse":
                from scrapers.greenhouse import GreenhouseScraper
                scrapers.append(GreenhouseScraper(src.get("companies", [])))
            elif t == "lever":
                from scrapers.lever import LeverScraper
                scrapers.append(LeverScraper(src.get("companies", [])))
            elif t == "hn_hiring":
                from scrapers.hn_hiring import HNHiringScraper
                scrapers.append(HNHiringScraper())
            elif t == "indeed":
                from scrapers.indeed import IndeedScraper
                scrapers.append(IndeedScraper(queries, location))
            elif t == "yc":
                from scrapers.yc import YCScraper
                scrapers.append(YCScraper(queries, remote=src.get("remote", True)))
            elif t == "builtin_sf":
                from scrapers.builtin_sf import BuiltInSFScraper
                scrapers.append(BuiltInSFScraper(queries, remote=src.get("remote", False)))
            elif t == "remotive":
                from scrapers.remotive import RemotiveScraper
                scrapers.append(RemotiveScraper(queries))
            elif t == "remoteok":
                from scrapers.remoteok import RemoteOKScraper
                scrapers.append(RemoteOKScraper(tags=tags, title_keywords=title_keywords))
            elif t == "wellfound":
                try:
                    from scrapers.wellfound import WellfoundScraper
                    scrapers.append(WellfoundScraper(queries, location))
                except Exception as e_wf:
                    print(f"[scraper] wellfound init failed: {e_wf}")
            # linkedin — needs LINKEDIN_LI_AT session cookie in .env
            elif t == "linkedin":
                li_at = os.getenv("LINKEDIN_LI_AT", "")
                if li_at:
                    from scrapers.linkedin import LinkedInScraper
                    scrapers.append(LinkedInScraper(queries, location, li_at))
        except Exception as e:
            print(f"[scraper] {t} failed to initialize: {type(e).__name__}: {e}")

    print(f"[search] running {len(scrapers)} scraper(s): {[s.source_name() for s in scrapers]}")

    # ── Scrape all sources concurrently ───────────────────────────────────────
    raw_results = await asyncio.gather(*[s.fetch() for s in scrapers], return_exceptions=True)

    # Collect jobs with per-source breakdown
    seen_urls: set[str] = set()
    all_jobs = []
    print("\n── Scraper results ──────────────────────────")
    for scraper_obj, result in zip(scrapers, raw_results):
        name = scraper_obj.source_name()
        if isinstance(result, Exception):
            print(f"  {name:15}: FAILED — {type(result).__name__}: {result}")
        else:
            print(f"  {name:15}: {len(result)} jobs")
            for job in result:
                if job.url not in seen_urls:
                    seen_urls.add(job.url)
                    all_jobs.append(job)
    print(f"  {'total':15}: {len(all_jobs)} (after URL dedup)")
    print("─────────────────────────────────────────────\n")

    # ── Step 1: apply hard filters + fast-score every candidate ───────────────
    scorer  = JobScorer(profile)
    region  = get_local_region()
    exp_yrs = profile.get("experience_years", 0)
    today   = date.today().isoformat()

    candidates: list[tuple[int, object, dict, str]] = []
    for job in all_jobs:
        if not _is_location_applicable(job.location, region):
            continue
        if not _is_level_applicable(job.title, exp_yrs):
            continue
        jd   = job.to_dict()
        fast = scorer.score_fast(jd)
        candidates.append((fast["score"], job, jd, fast["explanation"]))

    # ── Step 2: sort by fast score, keep top 20 for AI explanation ────────────
    candidates.sort(key=lambda x: x[0], reverse=True)
    top20 = candidates[:20]

    # ── Step 3: AI explanation only on the top 20 — no wasted calls ───────────
    results = []
    for fast_score, job, jd, fast_explanation in top20:
        try:
            full        = await scorer.score(jd)
            score       = full["score"]
            explanation = full.get("explanation", fast_explanation)
        except Exception:
            score       = fast_score
            explanation = fast_explanation

        results.append({
            "_row_id":          job.id,
            "Date Found":       today,
            "Company":          job.company,
            "Job Title":        job.title,
            "Location":         job.location,
            "Salary":           job.salary,
            "Job URL":          job.url,
            "Source":           job.source,
            "Match Score":      str(score),
            "Why It Fits":      explanation,
            "Status":           "Review",
            "Role Type":        job.role_type,
            "Deadline":         job.deadline,
            "Contact Name":     job.contact_name,
            "Referral?":        "",
            "Follow Up Date":   "",
            "Notes":            "",
            "Resume Version":   "",
            "Cover Note Draft": "",
            "_is_preview":      False,
        })

    results.sort(key=lambda j: int(j.get("Match Score") or 0), reverse=True)
    save_local_jobs(results)
    return results


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    # Always land on Profile until the user has uploaded a resume
    if not os.path.exists(PROFILE_PATH) or not load_profile().get("name"):
        return redirect("/profile")

    profile = load_profile()
    has_resume = bool(profile.get("base_resume", "").strip())
    if not has_resume:
        return redirect("/profile")

    region        = get_local_region()
    live          = using_live_data()
    has_local     = bool(load_local_jobs()) if not live else False
    status_filter = request.args.get("status")
    jobs          = get_jobs(status_filter=status_filter)
    stats         = get_stats()

    return render_template(
        "dashboard.html",
        jobs=jobs,
        stats=stats,
        status_filter=status_filter or "",
        total=len(load_local_jobs()) if has_local else len(jobs),
        using_live=live,
        using_local=has_local,
        waiting_resume=False,
        region=region,
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
    if not os.path.exists(PROFILE_PATH) or not load_profile().get("name"):
        return redirect("/profile")

    profile = load_profile()
    has_resume = bool(profile.get("base_resume", "").strip())
    if not has_resume:
        return redirect("/profile")

    generated_at = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    today = date.today().isoformat()

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
        generated_at=generated_at,
        today=today,
        waiting_resume=False,
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
    # ── Try Temporal first (production mode) ──────────────────────────────────
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
        print(f"[trigger-search] MODE: Temporal | workflow_id={workflow_id}")
        return jsonify({"ok": True, "mode": "temporal", "workflow_id": workflow_id, "run_id": run_id})

    except (ImportError, ModuleNotFoundError):
        print("[trigger-search] Temporal not installed — using standalone mode")
    except Exception as e:
        print(f"[trigger-search] Temporal unavailable ({type(e).__name__}: {e}) — using standalone mode")

    # ── Standalone mode (local, no Temporal needed) ───────────────────────────
    print("[trigger-search] MODE: Standalone (local)")
    try:
        results = asyncio.run(_run_standalone_search())
        print(f"[trigger-search] Done — {len(results)} jobs saved")
        return jsonify({
            "ok": True,
            "mode": "standalone",
            "count": len(results),
            "run_id": "local",
        })
    except Exception as e:
        print(f"[trigger-search] Standalone search failed: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/workflow-status/<workflow_id>")
def api_workflow_status(workflow_id):
    """Poll Temporal for live pipeline progress. Returns stage, message, and job counts."""
    try:
        from temporalio.client import Client

        async def _get():
            client = await Client.connect(
                os.getenv("TEMPORAL_HOST", "localhost:7233"),
                namespace=os.getenv("TEMPORAL_NAMESPACE", "default"),
            )
            handle = client.get_workflow_handle(workflow_id)
            desc   = await handle.describe()
            result = {
                "ok":          True,
                "workflow_id": workflow_id,
                "status":      desc.status.name,
                "run_id":      desc.run_id,
            }
            # Attach detailed progress from the workflow query handler
            try:
                from temporal.workflows.job_search_workflow import JobSearchWorkflow
                result["progress"] = await handle.query(JobSearchWorkflow.get_status)
            except Exception:
                pass
            return result

        return jsonify(asyncio.run(_get()))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    print("Job Search Dashboard → http://localhost:5050")
    app.run(debug=True, port=5050)
