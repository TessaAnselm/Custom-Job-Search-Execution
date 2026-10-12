# CareerPilot AI — Custom Job Search Execution

CareerPilot AI extends this Flask job-search application with an agent workflow for discovering real roles, evaluating fit against a verified candidate profile, and preparing truthful application drafts for human review. The project prioritizes reuse of the existing search and matching pipeline and self-hosted inference through Akamai-hosted vLLM.

```
Verified Profile → Discover Jobs → Filter and Score → Explain Fit → Prepare Reviewable Drafts
```

## Architecture: local app, remote inference

The Flask app (`app.py`, templates, dashboard) runs entirely on your machine and needs no GPU — it never bundles a model. When it needs AI (profile extraction, match explanations, resume/cover-note drafts, or the CareerPilot agent), it makes an HTTP call to whatever `AI_PROVIDER` is configured. With `AI_PROVIDER=vllm`, that call goes out over the network to Qwen3-4B running on the Akamai workshop's GPU — not to a model on your machine and not to OpenAI/Anthropic/Gemini.

```
Browser → localhost:5050 (Flask app, your machine, no GPU)
              │
              │  AI calls only
              ▼
     localhost:8000/v1 ──kubectl port-forward──▶ svc/vllm (Akamai namespace)
                                                       │
                                                       ▼
                                               vLLM → Qwen3-4B on the assigned GPU
```

Two ways to reach the Akamai-hosted model:
- **From your laptop (local development):** keep the Flask app running locally, and tunnel only the inference calls with `kubectl port-forward svc/vllm 8000:8000`, then set `VLLM_HOST=http://localhost:8000/v1` in `.env`. This is the path validated end-to-end and documented below.
- **Deployed inside the namespace:** using `k8s/careerpilot-agent.yaml`, the app runs as a pod alongside vLLM and reaches it directly via the in-cluster Service name `http://vllm:8000/v1` — no port-forward needed. This is the eventual workshop deployment path, not required for local development.

## Project status

**Implemented in this repository:** multi-source job discovery and deterministic matching; the Flask profile/dashboard experience; configurable OpenAI-compatible vLLM inference; a minimal AWS Strands agent wrapping existing search and document-generation functions; profile verification, grounded recommendations, review-only application drafts; basic agent activity and inference metrics; and a Kubernetes Deployment template for the app.

**Verified:** live connectivity from a laptop to the Akamai workshop's Qwen3-4B service, via `kubectl port-forward svc/vllm 8000:8000` and `scripts/test_inference.py`, with a real model response and measured latency.

**Not yet verified or complete:** a full end-to-end CareerPilot run (search → match → draft package) against the live Qwen3-4B service, including whether the deployed vLLM is configured for the tool-calling Strands' agent loop needs; the actual workshop namespace, GPU allocation; and a built/published application image and deployed Kubernetes workload. The Deployment template is not a ready-to-apply release. The workshop brief lists an RTX 4000 Ada; an earlier RTX PRO 6000 mention needs verification in the assigned environment.

## CareerPilot architecture and demo

CareerPilot reuses the existing scrapers, profile-derived search configuration, deterministic scoring, Flask dashboard, and resume/cover-note generators. AWS Strands orchestrates bounded tools over those functions; the vLLM provider routes model requests to the configured OpenAI-compatible endpoint. The intended demo discovers real postings, explains match evidence and gaps from a candidate-verified profile, suggests factual resume tailoring, and prepares a draft package. A person reviews and approves any application; CareerPilot does not submit applications automatically.

The Akamai workshop is expected to provide a Kubernetes namespace, JupyterLab workstation, NVIDIA GPU, vLLM serving `Qwen/Qwen3-4B`, an OpenAI-compatible API, Prometheus metrics, namespace-scoped Kubernetes access, and an agent runtime. `http://vllm:8000/v1` is the in-cluster endpoint; reach it from a laptop via `kubectl port-forward` as described in [Architecture](#architecture-local-app-remote-inference) above. Confirm the actual service/model configuration from the workshop environment before deployment. The app can show client/agent measurements and vLLM `/metrics` aggregates; server aggregates are not per-task measurements, and per-run TTFT is unavailable in the current non-streaming client path.

For additional Kubernetes deployment notes, see the [CareerPilot workshop runbook](docs/CareerPilot_Runbook.md).

### Frontend screenshots

These screenshots show the guided profile setup and the resume-extraction failure captured during testing. The parser has since been hardened for Qwen reasoning and Markdown-wrapped JSON; a live Akamai resume-extraction run still needs verification.

<p align="center">
  <img src="docs/image/Screenshot%202026-10-12%20at%204.34.08%E2%80%AFPM.png" alt="CareerPilot setup guide at the Akamai connection step" width="90%" />
  <br /><em>1. The guide starts with the Akamai connection check.</em>
</p>
<p align="center">
  <img src="docs/image/Screenshot%202026-10-12%20at%204.36.29%E2%80%AFPM.png" alt="CareerPilot checking the configured vLLM connection" width="90%" />
  <br /><em>2. Checking the configured vLLM endpoint.</em>
</p>
<p align="center">
  <img src="docs/image/Screenshot%202026-10-12%20at%204.36.40%E2%80%AFPM.png" alt="CareerPilot connected to Qwen3-4B" width="90%" />
  <br /><em>3. The Qwen3-4B connection check succeeds.</em>
</p>
<p align="center">
  <img src="docs/image/Screenshot%202026-10-12%20at%204.37.17%E2%80%AFPM.png" alt="CareerPilot reading an uploaded resume" width="90%" />
  <br /><em>4. Resume upload and profile extraction begin.</em>
</p>
<p align="center">
  <img src="docs/image/Screenshot%202026-10-12%20at%204.37.57%E2%80%AFPM.png" alt="Candidate profile fields left blank after extraction failed" width="90%" />
  <br /><em>5. Captured failure state: name and experience were not extracted, so these fields need manual review.</em>
</p>
<p align="center">
  <img src="docs/image/Screenshot%202026-10-12%20at%204.39.02%E2%80%AFPM.png" alt="CareerPilot reporting a vLLM profile extraction failure" width="90%" />
  <br /><em>6. Captured issue: the connection check passes, but resume extraction fails.</em>
</p>

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
# Set AI_PROVIDER and the matching provider configuration in .env
# Set LINKEDIN_LI_AT if you want LinkedIn results (see below)

# 4. Launch
python3 app.py
# Open http://localhost:5050 — you land on the Profile page
```

Upload your resume on the Profile page. The app extracts your profile, runs a search, and shows your ranked matches — usually within 1–2 minutes.

To use the CareerPilot agent, choose `AI_PROVIDER=vllm` and configure the workshop endpoint as described below. CareerPilot requires a verified profile and runs from the dashboard.

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
AI_PROVIDER=anthropic        # anthropic | gemini | groq | openai | ollama | vllm
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
GROQ_API_KEY=...
OPENAI_API_KEY=sk-...

# Akamai workshop's OpenAI-compatible vLLM endpoint (AI_PROVIDER=vllm)
# In Jupyter/a namespace pod: http://vllm:8000/v1 (default below)
# From your laptop: http://localhost:8000/v1, after `kubectl port-forward svc/vllm 8000:8000`
VLLM_HOST=http://vllm:8000/v1
MODEL_NAME=Qwen/Qwen3-4B
VLLM_API_KEY=
VLLM_TIMEOUT_SECONDS=30

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

## Run CareerPilot with Akamai vLLM

The workshop provides a Kubernetes namespace, JupyterLab workstation, NVIDIA GPU, vLLM with `Qwen/Qwen3-4B`, an OpenAI-compatible endpoint, Prometheus metrics, scoped Kubernetes access, and an agent runtime. `http://vllm:8000/v1` is the in-cluster Service address — it only resolves from inside the namespace (Jupyter, or a pod like the one `k8s/careerpilot-agent.yaml` deploys). From your laptop, reach the same model by tunneling through `kubectl` instead — see below. Check the workshop-provided environment for the actual namespace, endpoint, model, and GPU allocation; the earlier RTX PRO 6000 mention is unverified (the brief lists RTX 4000 Ada). Do not change the workshop's vLLM or GPU resources for this project.

0. **From your laptop:** install `kubectl` (`brew install kubectl` on Mac), save the kubeconfig the workshop gives you (e.g. `./.kube/s01.yaml`), then in a dedicated terminal you leave running:
   ```bash
   export KUBECONFIG=./.kube/s01.yaml
   kubectl port-forward svc/vllm 8000:8000
   ```
   This makes the remote model reachable at `http://localhost:8000/v1` for as long as that terminal stays open. Skip this step if you're working directly inside Jupyter or a pod in the namespace — there, `http://vllm:8000/v1` already resolves.

1. Set `AI_PROVIDER=vllm` and `MODEL_NAME=Qwen/Qwen3-4B` in `.env`. Set `VLLM_HOST=http://localhost:8000/v1` (laptop + port-forward) or `http://vllm:8000/v1` (already inside the namespace). Set `VLLM_API_KEY` only if the service requires it; never put credentials in source control or print them in logs.
2. Test the model connection before starting the app:

   ```bash
   python scripts/test_inference.py
   ```

   A successful probe reports the configured model and measured round-trip latency. This confirms basic inference connectivity, not agent tool-calling compatibility; validate the full dashboard workflow against the deployed Qwen/vLLM configuration.

3. Start the app with `python app.py` and open `http://localhost:5050`. Upload a synthetic or consented resume, review the extracted profile, and explicitly confirm its facts on the Profile page. Select **Run CareerPilot** on the dashboard.
4. Review the real job matches, evidence and gaps, resume recommendations, activity, and draft application package. The package remains in Review; CareerPilot never submits an application or message.

The Strands agent treats scraped job descriptions as untrusted data, not instructions. It only uses a profile after user verification, must ground qualifications in that profile, and requires human review of generated drafts. Use the minimum candidate data needed for a demo, keep credentials in environment variables or a Kubernetes Secret, and avoid logging resumes or contact details.

Run local mocked checks with `python -m unittest discover -s tests -v`; these require neither Akamai access nor a GPU. Dashboard request timings are client/agent measurements, while vLLM `/metrics` values are server-wide aggregates. Per-run TTFT is unavailable in the current non-streaming client path.

The Kubernetes file at `k8s/careerpilot-agent.yaml` is a deployment template, not a ready-to-apply manifest: replace its namespace and image placeholders and confirm the in-namespace vLLM service before use. It deploys only the app, not another model server.

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
