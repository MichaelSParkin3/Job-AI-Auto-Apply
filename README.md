# Job-AI-Auto-Apply

Local-first, review-first automation for job applications. This repo now ships the end-to-end dry-run demo experience: a Typer CLI that boots a FastAPI preview service, serves a React UI, and lets you approve/decline edits before anything is submitted.

Status: Story 1.5 (Dry-run demo flow) implemented.

## Why
- Privacy by default: runs on your machine; artifacts stored locally
- Review-first UX: no blind submissions — you approve before actions
- Deterministic demo flow: safe dry-run path to validate the stack

## Features (current)
- Typer CLI with subcommands: `apply`, `profiles`, `config`, `history`
- FastAPI preview service that launches alongside the CLI demo flow and serves the React UI on http://localhost:4950/ui
- Config loader with precedence: CLI > profile marker > profile YAML > global `config/config.yaml`
- Idempotent `config init` + runtime folders (`config/`, `data/profiles/`, `data/resumes/`, `.local/browser/profiles/`, `.local/state/`, `runs/`, `history/`)
- Profile management commands (`profiles new|validate|list|use|current`) with Pydantic schema enforcement
- Optional `.env.local` for OpenRouter; missing file is a warning, not an error
- Filesystem run store provisioning per-demo folders with seeded `run.json`
- Redacted JSON event logging pipeline writing to stdout and `actions.log`
- Append-only `history/history.jsonl` entries for demo runs
- Retention placeholders in `config.yaml` for artifacts, history, and actions log size caps

## Quickstart
### Prerequisites
- Windows 10/11
- Python 3.11+
- Node.js 22 LTS + pnpm 9
- Google Chrome Stable (for CLI-opened preview window)

### Setup
```bash
# Create virtual env (PowerShell examples)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install Python dependencies (editable)
pip install -U pip
pip install -e .[dev]
# If your Python < 3.11 or editable install fails, install minimal deps:
# pip install typer python-dotenv PyYAML pytest

# Install UI dependencies (from repo root)
pnpm install
```

### Initialize and Inspect Config
```bash
python app.py --help
python app.py config init          # creates config/config.yaml and runtime folders
python app.py config show          # prints effective settings as JSON
python app.py apply demo --dry-run --limit 1
# provisions a run dir, launches the FastAPI preview service, and opens the local React UI
# add --no-browser to keep Chrome from auto-launching
```

### Run the Interactive Demo Preview
```bash
# Launch the full demo flow (opens Chrome app-mode pointing at the preview UI)
python app.py apply demo --dry-run --limit 1

# Skip auto-opening Chrome if you prefer to visit http://localhost:4950/ui manually
python app.py apply demo --dry-run --limit 1 --no-browser

# Restart an existing preview without provisioning a new run directory
python app.py preview demo
```

Approving, aborting, or editing from the UI persists decisions to `runs/<id>/run.json`, appends entries to `actions.log`, and records redacted history events under `history/history.jsonl`. Guardrail log lines (e.g., `guardrail.demo.no_network`) confirm no Browser-Use automation or external SimplyHired calls occur during the demo.

### Sample Demo Artifacts
Running `python app.py apply demo --dry-run --limit 1` creates a run folder similar to:

```json
{
  "run_id": "20240926-120000-abcdef12",
  "actions_log": "runs/20240926-120000-abcdef12/actions.log"
}
```

`actions.log` entries are newline-delimited JSON with automatic PII masking:

```json
{"event":"run.demo_initialized","level":"info","message":"Demo run directory prepared with redacted logging.","runId":"20240926-120000-abcdef12","timestamp":"2024-09-26T12:00:00Z"}
```

`history/history.jsonl` receives a matching redacted record:

```json
{"fingerprint":"20240926-120000-abcdef12","id":"20240926-120000-abcdef12","postingUrl":"demo://placeholder","profileId":"","runPath":"runs/20240926-120000-abcdef12","status":"demo","summary":"Demo run initialized; actions.log will contain redacted events.","timestamp":"2024-09-26T12:00:00Z"}
```

### Environment Variables
Create `.env.local` at repo root (optional):
```env
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=deepseek/deepseek-chat-v3.1:free
```
The app logs a JSON warning if `.env.local` is missing and continues.

### Profiles
```bash
# Generate a new profile template (fills placeholders, does not overwrite unless --force)
python app.py profiles new frontend-dev

# Fill in the YAML and add a resume at data/resumes/frontend-dev/resume.pdf, then validate
python app.py profiles validate frontend-dev

# Persist the active profile for this machine and inspect its status
python app.py profiles use frontend-dev
python app.py profiles current

# View all profiles with validity and resume status
python app.py profiles list
```

> **Upgrading from earlier commits?** Create folders under `data/resumes/<id>/` and move your existing resumes there before running `profiles validate`.

### Browser-Use Session Bootstrap
Use the new `apply open` command to launch Browser-Use in headful Chrome with profile-bound persistence:

```bash
# Launch a dry-run Browser-Use session for the active profile
python app.py apply open "https://www.simplyhired.com/search?q=python&l=remote"

# Override the profile and Browser-Use model for this invocation
python app.py apply open "https://www.simplyhired.com/search?q=python" \
  --profile frontend-dev \
  --model deepseek/deepseek-r1:free
```

The command resolves the Chrome `user_data_dir` to `.local/browser/profiles/<profile>`, honors overrides from `config/config.yaml` or `data/profiles/<id>.yaml`, and returns a JSON payload with the session identifier so follow-up automation can reuse the same browser instance.

### Tests
```bash
pytest -q
pnpm --filter @app/ui test -- --runInBand
```

## Project Structure
See `docs/architecture/unified-project-structure.md`. Current key paths:
```
app.py                         # root entry that delegates to Typer app
apps/cli/                      # CLI implementation
core/tests/                    # pytest tests for CLI/config
config/                        # generated config.yaml (gitignored)
.local/, runs/, history/       # runtime artifacts (gitignored)
```

## Roadmap (from PRD)
- 1.2 Preview Server Skeleton (FastAPI on :4950, Chrome app-mode)
- 1.3 Profiles schema & commands
- 1.4 Run store & redacted logging
- 1.5 Dry-run demo flow end-to-end

## Development Notes
- JSON logs to stdout; avoid string exceptions
- Contracts align with `docs/architecture/api-specification-rest.md`
- Testing guidance in `docs/architecture/testing-strategy.md`

## Repo Hygiene
- `.gitignore` excludes local artifacts, logs, and build outputs
- `.gitattributes` uses `text=auto` and sets LF for Unix scripts and CRLF for Windows scripts; marks assets as binary; excludes local artifacts from archives

## Contributing
This project uses a story-driven workflow. See `docs/prd/epic-1-foundation-review-ui.md` and `docs/stories/`.

## License
TBD
