# Custom Job Search Execution

An AI-powered job search dashboard that scrapes multiple job boards, filters by your timezone, scores every result against your resume, and surfaces the top 20 matches — no manual keyword entry required.

```
Upload Resume → Extract Profile → Scrape All Sources → Filter → Score → Top 20 Matches
```

---

## How It Works

1. **Upload your resume** on the Profile page — the AI extracts your skills, titles, experience level, and salary range
2. **Search runs automatically** — all enabled scrapers fire concurrently, deduplicating by URL across sources
3. **Location filtering** — server timezone is auto-detected (e.g. Pacific → Bay Area / Remote US priority), non-US jobs are filtered out
4. **Level filtering** — intern/junior roles and VP/C-level roles are removed based on your years of experience
5. **Top 20** — every candidate is fast-scored, sorted, and only the top 20 get a full AI explanation
6. **Review in the dashboard** — apply, skip, or save for later; the Report page tracks your pipeline

Zero hardcoded job titles or keywords. Every search query is derived from your resume.

---

## Quick Start — Standalone (no Temporal required)

The default mode. One terminal, no Docker needed.

```bash
# 1. Clone
git clone https://github.com/TessaAnselm/Custom-Job-Search-Execution.git
cd Custom-Job-Search-Execution

# 2. Install
pip install -r requirements.txt

# 3. Add an AI key to .env (any one provider works)
cp .env.example .env
# Set OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, or GROQ_API_KEY

# 4. Launch
python3 app.py
# Open http://localhost:5050 — you land on the Profile page
```

Upload your resume on the Profile page. The app extracts your profile, runs a search, and redirects you to your top 20 matches — usually within 1–2 minutes.

The terminal will print a source breakdown after each search so you can see exactly what each scraper returned:

```
── Scraper results ──────────────────────────
  hn_hiring      : 18 jobs
  remotive       : 34 jobs
  remoteok       : 22 jobs
  wellfound      : 11 jobs
  total          : 82 (after URL dedup)
─────────────────────────────────────────────
```

---

## Optional: Run with Temporal (durable workflows + follow-up reminders)

Temporal adds durability, retries, and the follow-up reminder workflow. You need three terminals:

**Terminal 1 — Temporal server**
```bash
docker compose up
# Temporal server: localhost:7233
# Temporal UI:     localhost:8080
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

The dashboard auto-detects Temporal. If the server is running, searches run as durable workflows and appear in the Temporal UI at `localhost:8080`. If Docker is stopped, it falls back to standalone mode automatically — the terminal will print which mode is active:

```
[trigger-search] MODE: Temporal | workflow_id=job-search-a1b2c3d4
# or
[trigger-search] Temporal unavailable (ConnectionError: ...) — using standalone mode
[trigger-search] MODE: Standalone (local)
```

**Storage in Temporal mode**

| `GOOGLE_SHEETS_ID` set? | Where jobs are saved |
|---|---|
| Yes | Google Sheets (full read/write) |
| No | `jobs_local.json` (automatic fallback — no setup needed) |

All four Temporal storage activities (`write_job_to_sheet`, `update_job_status`, etc.) check for Sheets credentials at runtime and fall back to local JSON if they aren't present. You can run Temporal mode completely without Google Cloud.

Verify your docker-compose is valid before starting:
```bash
docker compose config   # should print the merged config with no errors
docker compose up
```

---

## Environment Variables

```env
# AI provider — pick one (used for profile extraction + scoring explanations)
AI_PROVIDER=openai          # openai | anthropic | gemini | groq | ollama
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
GROQ_API_KEY=...

# Optional: LinkedIn scraping (needs your li_at session cookie from browser)
LINKEDIN_LI_AT=

# Optional: persist jobs to Google Sheets instead of local JSON
GOOGLE_SHEETS_ID=
GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service-account.json
```

---

## Job Sources

| Source | Status | Requires |
|---|---|---|
| HN Who's Hiring | ✅ enabled | Nothing |
| Remotive | ✅ enabled | Nothing |
| RemoteOK | ✅ enabled | Nothing |
| Wellfound | ✅ enabled | `pip install playwright && playwright install chromium` |
| LinkedIn | ⚙️ opt-in | `LINKEDIN_LI_AT` session cookie in `.env` |
| Greenhouse | ⚙️ opt-in | Company slugs in `config/sources.yaml` |
| Lever | ⚙️ opt-in | Company slugs in `config/sources.yaml` |
| Indeed | ❌ disabled | API dead (404) |
| YC Work at a Startup | ❌ disabled | API removed (406) |
| Built In SF | ❌ disabled | API removed (405) |

Toggle sources and set company slugs in `config/sources.yaml`. No search queries live there — those come entirely from your resume.

---

## Scoring

Every job is scored 0–100 against your profile using weighted factors:

| Factor | Default weight |
|---|---|
| Title match | 30% |
| Skills overlap | 25% |
| Salary match | 20% |
| Location match | 15% |
| Industry match | 10% |

All candidates are fast-scored deterministically first, then the top 20 receive a full AI explanation. Weights are editable on the Profile page.

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
│   ├── dashboard.html              # Top 20 job matches
│   ├── job_detail.html             # Single job — AI explanation, resume tailoring
│   └── report.html                 # Pipeline summary + CSV export
├── static/
│   ├── css/dashboard.css
│   ├── js/dashboard.js
│   └── js/profile.js               # Resume upload → extract → auto-search → redirect
├── scrapers/
│   ├── base.py                     # Job dataclass + BaseScraper interface
│   ├── hn_hiring.py                # HN Who's Hiring (concurrent comment fetching)
│   ├── remotive.py                 # Remotive free API
│   ├── remoteok.py                 # RemoteOK free API (tag-based)
│   ├── wellfound.py                # Wellfound (Playwright, location-aware)
│   ├── linkedin.py                 # LinkedIn (Playwright + session cookie)
│   ├── greenhouse.py               # Greenhouse API (opt-in, company slugs)
│   └── lever.py                    # Lever API (opt-in, company slugs)
├── scoring/
│   └── scorer.py                   # Fast deterministic score + async AI explanation
├── ai/
│   ├── client.py                   # Multi-provider AI client (OpenAI/Anthropic/Gemini/Groq/Ollama)
│   ├── resume_tailor.py            # Tailored resume per job
│   └── cover_note.py               # Cover note generation
├── sheets/
│   └── client.py                   # Google Sheets read/write (optional)
├── alerts/
│   ├── telegram.py
│   └── gmail.py
├── temporal/                       # Optional: Temporal workflow orchestration
│   ├── workflows/
│   ├── activities/
│   └── workers/
├── mcp/
│   └── server.py                   # MCP server — drive the pipeline via Claude
├── scripts/
│   ├── run_search.py
│   └── approve.py
├── config/
│   ├── profile.yaml                # Auto-generated from resume upload
│   └── sources.yaml                # Enable/disable scrapers
├── .env.example
├── requirements.txt
└── docker-compose.yml              # Temporal local dev (optional)
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
