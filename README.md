# Custom Job Search Execution

An AI-powered job search dashboard that scrapes multiple job boards, filters by your location and experience level, scores every result against your resume, and surfaces the top matches — no manual keyword entry required.

```
Upload Resume → Extract Profile → Scrape All Sources → Filter → Score → Ranked Matches
```

---

## How It Works

1. **Upload your resume** on the Profile page — the AI extracts your skills, titles, experience level, and salary range
2. **Location is auto-detected** via IP geolocation — searches your city first, then Remote
3. **All enabled scrapers fire concurrently**, deduplicating by URL across sources
4. **Location filtering** — non-applicable region jobs are filtered out based on your preferences
5. **Level filtering** — intern/junior roles and VP/C-level roles are removed based on your years of experience
6. **AI scoring** — every candidate is scored 0–100 against your profile; results sorted highest first
7. **Review in the dashboard** — click the Score column to toggle sort order; apply, skip, or save for later

Zero hardcoded job titles or keywords. Every search query is derived from your resume.

**Session cleanup** — when you stop `app.py`, all jobs, tailored resumes, and the loaded profile are automatically wiped for a clean next session.

---

## Quick Start — Standalone (no Temporal required)

The default mode. One terminal, no Docker needed.

```bash
# 1. Clone
git clone https://github.com/TessaAnselm/Custom-Job-Search-Execution.git
cd Custom-Job-Search-Execution

# 2. Install
pip install -r requirements.txt
python3 -m playwright install chromium   # needed for LinkedIn + Indeed

# 3. Configure .env
cp .env.example .env
# Set one AI provider key: ANTHROPIC_API_KEY, GOOGLE_API_KEY, GROQ_API_KEY, or OPENAI_API_KEY
# Set LINKEDIN_LI_AT if you want LinkedIn results (see below)

# 4. Launch
python3 app.py
# Open http://localhost:5050 — you land on the Profile page
```

Upload your resume on the Profile page. The app extracts your profile, runs a search, and shows your ranked matches — usually within 1–2 minutes.

---

## Optional: Run with Temporal (durable workflows + follow-up reminders)

Temporal adds crash recovery, per-step retries, and 7-day follow-up reminders. No Docker required — use the Temporal CLI.

**Install Temporal CLI** (once):
```bash
brew install temporal
```

Then run three terminals:

**Terminal 1 — Temporal server**
```bash
temporal server start-dev
# Temporal server: localhost:7233
# Temporal UI:     localhost:8233
```

**Terminal 2 — Worker**
```bash
python3 -m temporal.workers.worker
```

**Terminal 3 — Dashboard**
```bash
python3 app.py
# Open http://localhost:5050
```

The dashboard auto-detects Temporal. If the server is running, searches run as durable workflows visible in the Temporal UI at `localhost:8233`. If Temporal is not running, it falls back to standalone mode automatically.

**What Temporal adds:**
- Crash recovery — resumes from the last completed step if the worker restarts
- Per-job child workflows that wait indefinitely for your approve/skip decision
- 7-day follow-up reminder after marking a job "Ready to Apply"
- Live pipeline progress visible in the dashboard modal

**Storage in Temporal mode**

| `GOOGLE_SHEETS_ID` configured? | Where jobs are saved |
|---|---|
| Yes (valid path + file) | Google Sheets |
| No | `jobs_local.json` (automatic fallback) |

---

## LinkedIn Setup

LinkedIn requires a session cookie from your browser:

1. Log into LinkedIn in Chrome
2. Open DevTools → Application → Cookies → `https://www.linkedin.com`
3. Copy the value of the `li_at` cookie
4. Add to `.env`: `LINKEDIN_LI_AT=your_value_here`
5. Enable in `config/sources.yaml`: `enabled: true`

The cookie expires when you log out. LinkedIn searches jobs posted in the last 24 hours.

---

## Environment Variables

```env
# AI provider — pick one
AI_PROVIDER=anthropic        # anthropic | gemini | groq | openai | ollama
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
GROQ_API_KEY=...
OPENAI_API_KEY=sk-...

# LinkedIn scraping (optional)
LINKEDIN_LI_AT=

# Persist jobs to Google Sheets instead of local JSON (optional)
GOOGLE_SHEETS_ID=
GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service-account.json

# Alerts — at least one recommended for follow-up reminders (optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
GMAIL_USER=
GMAIL_APP_PASSWORD=
```

---

## Job Sources

| Source | Status | Requires |
|---|---|---|
| LinkedIn | ✅ enabled | `LINKEDIN_LI_AT` cookie + `playwright install chromium` |
| Indeed | ✅ enabled | `playwright install chromium` |
| HN Who's Hiring | ⚙️ opt-in | Nothing |
| Remotive | ⚙️ opt-in | Nothing |
| RemoteOK | ⚙️ opt-in | Nothing |
| Wellfound | ⚙️ opt-in | `playwright install chromium` |
| Greenhouse | ⚙️ opt-in | Company slugs in `config/sources.yaml` |
| Lever | ⚙️ opt-in | Company slugs in `config/sources.yaml` |
| YC Work at a Startup | ❌ disabled | API removed |
| Built In SF | ❌ disabled | API removed |

Toggle sources in `config/sources.yaml`. The search modal always shows exactly which sources are currently enabled.

---

## Location Search

Location is determined in this order:

1. **Profile preferred cities** (non-Remote) — searched first
2. **IP geolocation** — your actual city is auto-detected if no city is in the profile
3. **Remote** — always included if `Remote` is in your profile preferred list

If your profile has `preferred: [San Francisco, CA, Remote]`, scrapers run for San Francisco first, then Remote, combining all results with URL deduplication.

---

## Scoring

Every job is scored 0–100 against your profile:

| Factor | Default weight |
|---|---|
| Title match | 30% |
| Skills overlap | 25% |
| Salary match | 20% |
| Location match | 15% |
| Industry match | 10% |

Jobs without a description (common with LinkedIn/Indeed) get a neutral skills baseline (50) rather than being penalized. Results are sorted highest score first by default. Click the **Score** column header in the dashboard to toggle ascending/descending order.

---

## Status Pipeline

```
Review → Ready to Apply → Applied → Follow Up → Interview → Rejected / Skip
```

Decide at **Review**. The Report page shows your full pipeline history and source breakdown.

---

## Project Structure

```
Custom-Job-Search-Execution/
├── app.py                          # Flask app — routes, scraper runner, scoring pipeline
├── templates/
│   ├── profile.html                # Resume upload + profile editor (entry point)
│   ├── dashboard.html              # Ranked job matches, sortable by score
│   ├── job_detail.html             # Single job — AI explanation, resume tailoring
│   └── report.html                 # Pipeline summary + CSV export
├── static/
│   ├── css/dashboard.css
│   ├── js/dashboard.js
│   └── js/profile.js
├── scrapers/
│   ├── base.py                     # Job dataclass + BaseScraper interface
│   ├── linkedin.py                 # LinkedIn (Playwright + session cookie)
│   ├── indeed.py                   # Indeed (Playwright, replaces dead RSS feed)
│   ├── hn_hiring.py                # HN Who's Hiring
│   ├── remotive.py                 # Remotive free API
│   ├── remoteok.py                 # RemoteOK free API (tag-based)
│   ├── wellfound.py                # Wellfound (Playwright, location-aware)
│   ├── greenhouse.py               # Greenhouse API (opt-in, company slugs)
│   └── lever.py                    # Lever API (opt-in, company slugs)
├── scoring/
│   └── scorer.py                   # Fast deterministic score + async AI explanation
├── ai/
│   ├── client.py                   # Multi-provider AI client
│   ├── resume_tailor.py            # Tailored resume per job
│   └── cover_note.py               # Cover note generation
├── sheets/
│   └── client.py                   # Google Sheets read/write (optional)
├── alerts/
│   ├── telegram.py
│   └── gmail.py
├── temporal/                       # Durable workflow orchestration (optional)
│   ├── workflows/job_search_workflow.py
│   ├── activities/
│   │   ├── scrape_jobs.py
│   │   ├── score_jobs.py
│   │   ├── generate_docs.py
│   │   ├── update_sheet.py
│   │   └── send_alert.py
│   └── workers/worker.py
├── utils/
│   └── search_config.py            # Profile → queries + IP-geolocated locations
├── storage/
│   └── local.py                    # Local JSON fallback storage
├── config/
│   ├── profile.yaml                # Auto-generated from resume (wiped on shutdown)
│   └── sources.yaml                # Enable/disable scrapers
├── .env.example
├── requirements.txt
└── docker-compose.yml              # Alternative Temporal setup via Docker
```

---

## MCP Tools

Drive the pipeline from Claude or any MCP client:

| Tool | Description |
|---|---|
| `search_jobs` | Trigger a new search |
| `list_jobs` | List jobs by status or score |
| `approve_job` | Mark a job ready to apply |
| `skip_job` | Skip a job |
| `update_status` | Set any status |
| `get_stats` | Pipeline stats |

---

## License

MIT
