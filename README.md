# Custom Job Search Execution

An AI-powered job search pipeline that finds jobs across multiple sources, scores them against your profile, generates tailored resumes and cover notes, and waits for your approval before anything goes out.

```
Scrape → Deduplicate → Score → Generate Docs → Alert → Await Approval → Track
```

---

## Web Dashboard

A local Flask dashboard lets you review job matches, approve or skip them, and trigger new searches — all from your browser.

```
http://localhost:5050
```

**Dashboard views:**
- Stats bar — jobs at each stage (Review, Applied, Interview, etc.)
- Job table — score, company, title, location, salary, source, inline actions
- Job detail page — AI explanation, cover note draft, resume filename, metadata
- Run Search button — triggers the full pipeline

---

## Quick Start — Run Locally

The fastest path: clone the repo, install dependencies, and launch the dashboard. It runs on demo data immediately — no API keys needed to see it working.

```bash
# 1. Clone
git clone https://github.com/TessaAnselm/Custom-Job-Search-Execution.git
cd Custom-Job-Search-Execution

# 2. Install
pip install -r requirements.txt

# 3. Copy and fill in your profile
cp config/profile.yaml.example config/profile.yaml
# Edit profile.yaml — add your name, target titles, skills, salary range, resume text

# 4. Launch the dashboard
python3 app.py
# Open http://localhost:5050
```

The dashboard shows demo data until you connect Google Sheets (see [Full Setup](#full-setup) below). You can browse the UI, click through job details, and test the approve/skip flow right away.

---

## Full Setup

To run live job scraping, AI scoring, and resume generation you need a few API keys.

### 1. Environment variables

```bash
cp .env.example .env
```

Fill in `.env`:

```env
# Required for AI scoring + resume/cover note generation
OPENAI_API_KEY=sk-...

# Required to read/write your job tracker
GOOGLE_SHEETS_ID=your-spreadsheet-id
GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service-account.json

# At least one alert channel (optional but recommended)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
GMAIL_USER=you@gmail.com
GMAIL_APP_PASSWORD=

# Only needed if LinkedIn scraping is enabled
LINKEDIN_LI_AT=
```

### 2. Google Sheets

1. Create a new Google Sheet
2. Create a service account in Google Cloud Console and download the JSON key
3. Share your sheet with the service account email
4. Set `GOOGLE_SHEETS_ID` to the sheet ID from the URL

The sheet schema (columns A–R) is set up automatically on first run.

### 3. Trigger a search

Without Temporal (simplest):
```bash
# Coming soon: python3 scripts/run_standalone.py
```

With Temporal running:
```bash
# Start Temporal locally
docker-compose up -d

# Start the worker
python3 temporal/workers/worker.py

# Trigger a search run
python3 scripts/run_search.py

# Review jobs from the CLI
python3 scripts/approve.py list
python3 scripts/approve.py apply <job_id>
python3 scripts/approve.py skip <job_id>
```

---

## Job Sources

| Source | Type | Location focus | Requires |
|---|---|---|---|
| Greenhouse | API | Configurable companies | Nothing |
| Lever | API | Configurable companies | Nothing |
| HN Who's Hiring | RSS/HTML | Global | Nothing |
| Indeed | RSS | SF + configurable | Nothing |
| Wellfound | Playwright | SF startups | `playwright install chromium` |
| Y Combinator | JSON API | SF/Remote, YC companies | Nothing |
| Built In SF | JSON API | San Francisco only | Nothing |
| LinkedIn | Playwright | Configurable | Session cookie (`LINKEDIN_LI_AT`) |

Configure which sources are active and what to search for in `config/sources.yaml`.

---

## Scoring

Every job is scored 0–100 against your `config/profile.yaml` using weighted factors:

| Factor | Default weight |
|---|---|
| Title match | 30% |
| Skills overlap | 25% |
| Salary match | 20% |
| Location match | 15% |
| Industry match | 10% |

Jobs below `minimum_score` are auto-skipped. Strong matches get a tailored resume and cover note generated via GPT-4o.

---

## Status Pipeline

```
New → Review → Tailor Resume → Ready to Apply → Applied → Follow Up → Interview → Rejected / Skip
```

You only make decisions at the **Review** stage. Everything else moves automatically.

---

## Project Structure

```
Custom-Job-Search-Execution/
├── app.py                          # Flask web dashboard
├── templates/
│   ├── dashboard.html              # Job list + stats view
│   └── job_detail.html             # Single job detail view
├── static/
│   ├── css/dashboard.css
│   └── js/dashboard.js
├── scrapers/
│   ├── base.py                     # Job dataclass + BaseScraper interface
│   ├── greenhouse.py               # Greenhouse API
│   ├── lever.py                    # Lever API
│   ├── hn_hiring.py                # HN Who's Hiring thread parser
│   ├── indeed.py                   # Indeed RSS feed
│   ├── wellfound.py                # Wellfound (Playwright)
│   ├── yc.py                       # Y Combinator / workatastartup.com
│   ├── builtin_sf.py               # Built In SF
│   └── linkedin.py                 # LinkedIn (Playwright + session cookie)
├── scoring/
│   └── scorer.py                   # Weighted job scoring + GPT explanation
├── ai/
│   ├── resume_tailor.py            # GPT-4o resume tailoring per job
│   └── cover_note.py               # GPT-4o cover note generation
├── sheets/
│   └── client.py                   # Google Sheets read/write
├── alerts/
│   ├── telegram.py                 # Telegram bot notifications
│   └── gmail.py                    # Gmail SMTP notifications
├── temporal/
│   ├── workflows/
│   │   └── job_search_workflow.py  # Main + per-job + follow-up workflows
│   ├── activities/
│   │   ├── scrape_jobs.py          # Scrape + deduplicate
│   │   ├── score_jobs.py           # Score against profile
│   │   ├── generate_docs.py        # Resume + cover note
│   │   ├── update_sheet.py         # Sheet read/write
│   │   └── send_alert.py           # Telegram/Gmail dispatch
│   └── workers/
│       └── worker.py               # Temporal worker entrypoint
├── mcp/
│   └── server.py                   # MCP server (drive via Claude)
├── scripts/
│   ├── run_search.py               # Trigger a search via Temporal
│   └── approve.py                  # CLI to approve/skip/list jobs
├── config/
│   ├── profile.yaml.example        # Copy to profile.yaml and fill in
│   └── sources.yaml                # Active sources and search queries
├── .env.example
├── requirements.txt
└── docker-compose.yml              # Temporal local dev (server + UI)
```

---

## MCP Tools

Drive the pipeline via Claude or any MCP client:

| Tool | Description |
|---|---|
| `search_jobs` | Trigger a new search run |
| `list_jobs` | List jobs by status or score |
| `approve_job` | Signal approval for a job |
| `skip_job` | Signal skip |
| `update_status` | Update job status |
| `get_stats` | Pipeline stats (applied, interviews, etc.) |

---

## Contributing

PRs welcome. Open areas:

- Standalone runner (no Temporal required) — `scripts/run_standalone.py`
- Workday and Ashby scrapers
- Interview prep workflow
- Calendar integration for deadlines and follow-ups
- Better cross-source deduplication

---

## License

MIT
