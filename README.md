# Job-AI-Auto-Apply

Local-first, review-first automation for job applications. The CLI discovers roles, prepares Lever apply forms, captures a full review bundle, and hands everything to a local preview UI before any submission happens.

Status: Story 4.3 (preview queue drawer & keyboard flow) implemented.

---

## Table of Contents
1. [Overview](#overview)
2. [System Requirements](#system-requirements)
3. [Installation](#installation)
4. [Step-by-Step Usage](#step-by-step-usage)
   - [Step 0 – Prepare the workspace](#step-0--prepare-the-workspace)
   - [Step 1 – Initialize configuration](#step-1--initialize-configuration)
   - [Step 2 – Create and validate profiles](#step-2--create-and-validate-profiles)
   - [Step 3 – Generate a Lever plan](#step-3--generate-a-lever-plan)
   - [Step 4 – Run Lever review automation](#step-4--run-lever-review-automation)
   - [Step 5 – Review candidates in the preview UI](#step-5--review-candidates-in-the-preview-ui)
   - [Step 6 – Explore the dry-run demo](#step-6--explore-the-dry-run-demo)
5. [Command Reference](#command-reference)
6. [Environment Variables & Logging](#environment-variables--logging)
7. [Troubleshooting](#troubleshooting)
8. [Release Highlights](#release-highlights)
9. [Testing](#testing)
10. [Project Structure](#project-structure)
11. [Contributing](#contributing)

---

## Overview
- **Privacy by default** – everything runs locally; PII never leaves your machine.
- **Review-first UX** – every automation step is staged for human approval; no blind submits.
- **Deterministic demo flow** – `apply demo` launches a canned run so you can validate the stack safely.

Core building blocks:
- Typer CLI (`python app.py …`) with subcommands: `apply`, `profiles`, `config`, `history`.
- Browser-Use 0.7.9 wrapper for headful Chrome sessions with guardrails and pacing.
- FastAPI preview server that serves the React UI at http://localhost:4950/ui.
- Filesystem run store (`runs/<runId>/`) with redacted JSONL logging and queue snapshots.

---

## System Requirements
- Windows 10/11 (PowerShell examples below)
- Python 3.11+
- Node.js 22 LTS + pnpm 9
- Google Chrome Stable (headful automation + preview app mode)

Optional:
- OpenRouter API key (LLM) if you plan to use Browser-Use models behind OpenRouter
- Google Programmable Search API key + CX if you want CSE-based Lever discovery

---

## Installation
```powershell
# Create and activate the virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install Python dependencies (editable install)
pip install -U pip
pip install -e .[dev]

# Install UI dependencies (from repo root)
pnpm install
```
If editable installs are not available, install the minimal set instead:
```powershell
pip install typer python-dotenv pyyaml fastapi httpx pytest
```

---

## Step-by-Step Usage

### Step 0 – Prepare the workspace
1. Clone the repo and `cd` into it.
2. Copy `.env.local.example` to `.env.local` (if present) or create one manually (see [Environment Variables](#environment-variables--logging)).
3. Make sure your PowerShell session is running from the project root. All relative paths below assume the repo root.

### Step 1 – Initialize configuration
```powershell
python app.py --help
python app.py config init    # creates config/config.yaml and runtime directories
python app.py config show    # prints the effective settings as JSON
```
`config init` provisions:
- `config/config.yaml`
- `data/profiles/`, `data/resumes/`
- `.local/browser/profiles/`, `.local/browser/backups/`
- `runs/`, `history/`

### Step 2 – Create and validate profiles
Profiles drive automation answers and Browser-Use guardrails. Each profile has a YAML file and a resume PDF.
```powershell
python app.py profiles new frontend-dev
# Edit data/profiles/frontend-dev.yaml and copy a resume to data/resumes/frontend-dev/resume.pdf
python app.py profiles validate frontend-dev
python app.py profiles use frontend-dev
python app.py profiles current
python app.py profiles list
```
Validation surfaces structured JSON errors (`profiles.validation_failed`) until the resume exists and the YAML passes schema checks.

### Step 3 – Generate a Lever plan
Plans describe which Lever postings to open.
```powershell
# Browser-Use discovery (collects SERP HTML and dedupes results)
python app.py apply plan --source lever-google --browser-discovery \
  | Out-File lever-plan.json -Encoding utf8

# Programmable Search (no browser) when GOOGLE_CSE_* is configured
python app.py apply plan --source lever-google --programmable-search \
  | Out-File lever-plan.json -Encoding utf8

# Override search terms/location/pages directly
python app.py apply plan --source lever-google --terms "react front end" --location "remote us" --pages 2 \
  | Out-File lever-plan.json -Encoding utf8
```
Important notes:
- Logs now stream to **stderr**, so the JSON captured by `Out-File` or redirection is clean.
- Plan artifacts (SERP HTML, guardrail domains, deduped results) are stored under `runs/<runId>/plan/` when Browser-Use runs.

### Step 4 – Run Lever review automation
```powershell
python app.py apply run --plan lever-plan.json --limit 5 --profile frontend-dev --mode review --dry-run
```
What happens:
- A run directory `runs/<runId>/` is created.
- Each candidate gets a subfolder with HTML snapshots, form plan, summary, resume telemetry, and screenshot.
- Enriched plan intents live under `runs/<runId>/plans/<candidateId>.json` with hashed prompt bundles in `runs/<runId>/autofill/prompts/` for audit without leaking PII.
- `queue.json` tracks candidate state (`discovered → planned → awaiting_decision`).
- Console output logs queue transitions and summary counts.

### Step 5 - Review candidates in the preview UI
Once `apply run` completes, note the run id printed in the logs (or use the newest folder under `runs\`). Launch the preview UI for that run:
```powershell
python app.py preview run 20250930-045625-0805f893  # replace with your run id
```
Add `--no-browser` if you prefer to open http://localhost:4950/ui manually.

Once the preview UI opens:
- The queue drawer lists all `pending` / `escalated` candidates.
- Keyboard shortcuts: `Shift+A` approve, `Shift+X` escalate, `J/K` navigate, `Shift+?` toggle legend.
- Decisions update `queue.json` (`decided` array) and stamp the candidate payload under `runs/<runId>/lever/<candidateId>/`.

You can always inspect `runs/<runId>/queue.json` manually if you only need the data.

### Step 6 - Explore the dry-run demo
Use this when you just want the preview experience without real automation:
```powershell
python app.py apply demo --dry-run --limit 1       # opens Chrome app mode by default
python app.py apply demo --dry-run --limit 1 --no-browser
python app.py preview demo                        # reopen the last demo run
```
Demo runs seed placeholder artifacts, redacted `actions.log` lines, and append to `history/history.jsonl`.
AI autofill runs additionally persist drafted answer artifacts under `runs/<runId>/answers/` with hashed values for reviewer audits.

---
## Command Reference

### `python app.py apply ...`
| Command | Purpose | Notes |
| --- | --- | --- |
| `apply demo` | Provision a demo run, launch preview UI | `--limit`, `--no-browser` available |
| `apply plan` | Emit Lever discovery plan JSON | `--browser-discovery`, `--programmable-search`, `--terms`, `--location`, `--pages`, CSE overrides |
| `apply run` | Execute Lever automation using a plan | `--plan`, `--profile`, `--limit`, `--mode review`, `--dry-run`, `--plan-model`, `--plan-llm/--no-plan-llm`, `--answer-model`, `--no-answer-llm`, `--min-answer-confidence` |
| `apply queue` | Manually reassign queue candidates between human/AI lanes | `--action escalate|assign-ai`, `--reason` (optional context) |
| `apply open` | Launch Browser-Use session for a SimplyHired search | Accepts `--profile`, `--model`, `--session-backups/--no-session-backups` |

### `python app.py profiles ...`
- `profiles new <id>` – scaffold YAML + folders.
- `profiles validate <id>` – enforce schema & resume presence.
- `profiles use <id>` – mark profile active.
- `profiles current` – print active profile and overrides.
- `profiles list` – list all profiles with validation status.

### `python app.py config ...`
- `config init` – create `config/config.yaml` with documented defaults.
- `config show` – render effective settings in JSON (CLI overrides > profile > global).

### `python app.py history ...`
- `history path` – print the absolute `history/` directory.
- `history summary` – surface recent decision aggregates with `--last`, `--limit`, and `--json` options.

### `python app.py preview ...`
- `preview demo` - start the preview FastAPI server with demo data (`--no-browser`, `--port` available).
- `preview run <runId>` - launch the preview FastAPI server for an existing automation run (`--no-browser`, `--port` available).

---

## Environment Variables & Logging
Add these (optional) to `.env.local`:
```env
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=deepseek/deepseek-chat-v3.1:free
GOOGLE_CSE_KEY=...                       # Programmable Search (optional)
GOOGLE_CSE_CX=...                        # Programmable Search (optional)
BROWSER_USE_SETUP_LOGGING=false          # keep Browser-Use logs off stdout; CLI sets this by default
```
Key logging behaviors:
- CLI structured events are redacted and now written to **stderr** (`apps/cli/utils.log_event`).
- Browser-Use `setup_logging` is disabled by default (`BROWSER_USE_SETUP_LOGGING=false`) so third-party warnings do not contaminate JSON streams.
- `runs/<runId>/actions.log` is newline-delimited JSON with the same redaction applied.

---

## Troubleshooting
| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| Plan command writes “Plan file is not valid JSON” | Mixing stdout/stderr in your redirect with older commits | Update to this commit (logs now use stderr) and re-run `apply plan` with `Out-File` or `>` |
| Preview UI shows empty queue after `apply run` | Preview server is still on a demo run id | Stop the demo server and relaunch preview using the run id from `apply run` (see [Step 5](#step-5--review-candidates-in-the-preview-ui)) |
| Browser-Use fails to launch | Missing profile validation or Chrome path | Run `profiles validate`, check `profiles current`, set `chrome_path` in `config/config.yaml` if needed |
| Resume upload reports `UPLOAD_FAILED` | Missing resume or selector mismatch | Confirm resume path in `data/resumes/<id>/`, inspect `runs/<runId>/lever/<candidateId>/resume-upload.json` |
| `pip install -e .` fails | Editable installs not supported on your Python build | Install minimal deps manually (see [Installation](#installation)) |

---

## Release Highlights
- **4.5** – Queue override API + CLI power command, failsafe watchdog reassignment, preview UI take-back banner, and regression coverage.
- **4.3** – Preview UI queue drawer, keyboard shortcuts (`Shift+A`, `Shift+X`, `J/K`, `Shift+?`), optimistic updates, manual override log, RTL test coverage.
- **4.1.6** – `apply plan --browser-discovery` enriches plans with SERP artifacts; Programmable Search mode; guardrail updates for Google domains.
- **3.3** – `apply open` replays stored SimplyHired form plans; `FormFillExecutor` + `ProfileAnswerResolver` telemetry; `formFill` persistence.
- **3.1.5** – Browser-Use 0.7.x adapter, CDP navigation fallback, locale/timezone alignment, session backup controls, UTF-8 console handling.

---

## Testing
Ensure you installed the `dev` extras (or FastAPI/HTTPX manually), then:
```powershell
pytest -q
pytest apps/preview/tests/test_queue_endpoints.py
pytest sites/lever/tests/test_lever_queue_restart.py
pnpm run test -- --runInBand
```

---

## Project Structure
```
app.py                         # CLI entry point
apps/cli/                      # Typer commands, run store, queue manager
apps/preview/                  # FastAPI preview server + runner helpers
apps/ui/                       # React preview UI (Vite build)
data/profiles/, data/resumes/  # Profile YAML + resumes
runs/, history/, .local/       # Runtime artifacts (gitignored)
docs/                          # Architecture, PRD, story docs
```

---

## Contributing
The project follows a story-driven workflow. See `docs/prd/epic-1-foundation-review-ui.md` and the individual `docs/stories/*.md` files for acceptance criteria and implementation notes.

License: TBD

