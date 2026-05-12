# 🎯 Job Search Agent

A durable, AI-powered job search automation system built with **Temporal**, **Google Sheets**, **OpenAI**, and **MCP**. It finds jobs, scores them against your profile, generates tailored resumes and cover notes, and waits for your approval before anything goes out.

```
Job Sources → Temporal Workflow → Score → Spreadsheet → Generate Docs → Alert → Await Approval → Track
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    MCP Interface Layer                   │
│         (Claude / any MCP client can drive this)        │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│                  Temporal Engine                         │
│   ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│   │ Scrape   │→ │  Score   │→ │ Resume + Cover Note  │  │
│   │  Jobs    │  │  Jobs    │  │     Generator        │  │
│   └──────────┘  └──────────┘  └──────────┬───────────┘  │
│                                           │              │
│   ┌──────────────────────────────────────▼───────────┐  │
│   │         Human Approval Signal (wait forever)     │  │
│   └──────────────────────────────────────┬───────────┘  │
│                                           │              │
│   ┌───────────────────────────────────────▼──────────┐  │
│   │            Update Spreadsheet + Alert            │  │
│   └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│              Google Sheets (Control Panel)               │
│  Date │ Company │ Score │ Status │ Resume │ Cover Note   │
└─────────────────────────────────────────────────────────┘
```

---

## Features

- **Durable workflows** — survives crashes, retries failed steps automatically
- **Human-in-the-loop** — prepares everything, but waits for your GO signal
- **AI scoring** — ranks jobs against your profile (skills, location, salary, role type)
- **Resume tailoring** — generates a targeted resume variant per job
- **Cover note drafts** — personalized, not templated
- **Multi-source scraping** — LinkedIn, Greenhouse, Lever, HN Who's Hiring, custom boards
- **Google Sheets dashboard** — your control panel for every job
- **Telegram/Gmail alerts** — instant notification when a strong match is found
- **MCP wrapper** — drive the whole system via Claude or any MCP client
- **Referral detection** — checks if you have a connection at the company

---

## Spreadsheet Schema

| Column | Description |
|---|---|
| Date Found | When the job was discovered |
| Company | Company name |
| Job Title | Exact title from posting |
| Location | Remote / City |
| Salary | Parsed salary range |
| Job URL | Direct link to posting |
| Source | Where it was found |
| Match Score | 0–100 AI-generated score |
| Role Type | IC / Manager / Hybrid |
| Why It Fits | AI explanation of match |
| Resume Version | Filename of tailored resume |
| Cover Note Draft | Draft text or link |
| Status | See statuses below |
| Deadline | Application deadline if listed |
| Contact Name | Hiring manager if findable |
| Referral? | Yes / No / Unknown |
| Follow Up Date | When to follow up |
| Notes | Your free-form notes |

### Statuses
`New` → `Review` → `Tailor Resume` → `Ready to Apply` → `Applied` → `Follow Up` → `Interview` → `Rejected` / `Skip`

---

## Project Structure

```
job-search-agent/
├── temporal/
│   ├── workflows/
│   │   ├── job_search_workflow.py      # Main orchestration
│   │   ├── approval_workflow.py        # Human-in-the-loop signal handler
│   │   └── followup_workflow.py        # Scheduled follow-up reminders
│   ├── activities/
│   │   ├── scrape_jobs.py              # Job source scrapers
│   │   ├── score_jobs.py               # AI scoring against profile
│   │   ├── generate_docs.py            # Resume + cover note generation
│   │   ├── update_sheet.py             # Google Sheets read/write
│   │   └── send_alert.py               # Telegram/Gmail notifications
│   └── workers/
│       └── worker.py                   # Temporal worker entrypoint
├── mcp/
│   └── server.py                       # MCP server wrapping Temporal signals
├── scrapers/
│   ├── linkedin.py                     # LinkedIn scraper (Playwright)
│   ├── greenhouse.py                   # Greenhouse API
│   ├── lever.py                        # Lever API
│   ├── hn_hiring.py                    # HN Who's Hiring parser
│   └── base.py                         # Base scraper interface
├── scoring/
│   └── scorer.py                       # Job ↔ profile scoring logic
├── ai/
│   ├── resume_tailor.py                # Resume tailoring via OpenAI
│   └── cover_note.py                   # Cover note generation
├── sheets/
│   └── client.py                       # Google Sheets API client
├── alerts/
│   ├── telegram.py                     # Telegram bot alerts
│   └── gmail.py                        # Gmail alerts
├── config/
│   ├── profile.yaml                    # YOUR profile — skills, prefs, resume base
│   └── sources.yaml                    # Job sources to monitor
├── scripts/
│   ├── setup.sh                        # One-shot setup
│   └── approve.py                      # CLI to approve/skip jobs
├── docs/
│   ├── setup-google-sheets.md
│   ├── setup-temporal.md
│   └── setup-telegram.md
├── .env.example
├── requirements.txt
├── docker-compose.yml
└── README.md
```

---

## Phases

### Phase 1 — Spreadsheet tracker (manual)
Set up Google Sheets with the schema. Populate manually to get your workflow right.

### Phase 2 — Job discovery
Scripts scrape sources and auto-populate rows. Deduplication handled by URL.

### Phase 3 — AI scoring
Every new job is scored 0–100 against `config/profile.yaml`. Low scores are auto-skipped.

### Phase 4 — Resume + cover note generation
Above-threshold jobs get a tailored resume variant and a personalized cover note draft.

### Phase 5 — Temporal workflow with approval
Full durable pipeline. You get alerted, then approve/skip via Telegram command or CLI.

### Phase 6 — MCP wrapper
Drive everything via Claude: "Find me new Python jobs paying over $180k" → runs the full pipeline.

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/yourname/job-search-agent
cd job-search-agent
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Fill in: OPENAI_API_KEY, GOOGLE_SHEETS_ID, TELEGRAM_BOT_TOKEN, etc.
cp config/profile.yaml.example config/profile.yaml
# Edit profile.yaml with your skills, target roles, salary, location prefs

# 3. Start Temporal (local dev)
docker-compose up -d

# 4. Start the worker
python temporal/workers/worker.py

# 5. Trigger a search run
python scripts/run_search.py

# 6. Approve jobs (when alerted)
python scripts/approve.py --job-id <id> --action apply
```

---

## Environment Variables

```env
# AI
OPENAI_API_KEY=

# Google Sheets
GOOGLE_SHEETS_ID=
GOOGLE_SERVICE_ACCOUNT_JSON=

# Temporal
TEMPORAL_HOST=localhost:7233
TEMPORAL_NAMESPACE=job-search

# Alerts
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
GMAIL_USER=
GMAIL_APP_PASSWORD=

# Optional: LinkedIn session cookie for scraping
LINKEDIN_LI_AT=
```

---

## Configuration

### `config/profile.yaml`
```yaml
name: "Your Name"
target_titles:
  - "Senior Software Engineer"
  - "Staff Engineer"
  - "Engineering Manager"
skills:
  - Python
  - Go
  - Distributed Systems
  - Kubernetes
location:
  preferred: ["Remote", "New York", "San Francisco"]
  hard_no: ["Requires Relocation"]
salary:
  minimum: 150000
  target: 200000
role_type: IC  # IC | Manager | Either
experience_years: 8
industries:
  preferred: ["Fintech", "Dev Tools", "AI/ML Infrastructure"]
  avoid: ["Gambling", "AdTech"]
scoring_weights:
  title_match: 0.30
  skills_match: 0.25
  salary_match: 0.20
  location_match: 0.15
  industry_match: 0.10
minimum_score: 65
```

### `config/sources.yaml`
```yaml
sources:
  - type: greenhouse
    companies: [stripe, airbnb, notion, figma]
  - type: lever
    companies: [anthropic, openai, mistral]
  - type: hn_hiring
    enabled: true
  - type: linkedin
    keywords: ["senior python engineer", "staff engineer remote"]
    enabled: false  # requires session cookie
```

---

## MCP Tools (Phase 6)

| Tool | Description |
|---|---|
| `search_jobs` | Trigger a new search run |
| `list_jobs` | List jobs by status or score |
| `approve_job` | Signal approval for a job |
| `skip_job` | Signal skip for a job |
| `get_job_details` | Get full job info + AI docs |
| `update_status` | Update job status in sheet |
| `generate_resume` | Force regenerate resume for a job |
| `get_stats` | Pipeline stats (applied, interviews, etc.) |

---

## Contributing

PRs welcome. Priority needs:
- More scraper sources (Wellfound, Workday, Ashby)
- Better deduplication across sources
- Interview prep workflow (Phase 7 idea)
- Calendar integration for deadlines

---

## License

MIT
