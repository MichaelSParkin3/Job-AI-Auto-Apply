# Job-AI-Auto-Apply

Local-first, review-first automation for job applications. This repo currently ships a minimal CLI scaffold and config loader, with a roadmap for a Preview server (FastAPI) and a React UI that lets you approve/decline edits before anything is submitted.

Status: Story 1.3 (Profile schema & commands) implemented.

## Why
- Privacy by default: runs on your machine; artifacts stored locally
- Review-first UX: no blind submissions — you approve before actions
- Deterministic demo flow: safe dry-run path to validate the stack

## Features (current)
- Typer CLI with subcommands: `apply`, `profiles`, `config`, `history`
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
- (For UI later) Node.js 22 LTS + pnpm 9, Chrome stable

### Setup
```bash
# Create virtual env (PowerShell examples)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install (editable)
pip install -U pip
pip install -e .[dev]
# If your Python < 3.11 or editable install fails, install minimal deps:
# pip install typer python-dotenv PyYAML pytest
```

### Initialize and Inspect Config
```bash
python app.py --help
python app.py config init          # creates config/config.yaml and runtime folders
python app.py config show          # prints effective settings as JSON
python app.py apply demo           # provisions a run dir, redacted actions.log, and history entry
```

### Sample Demo Artifacts
Running `python app.py apply demo` creates a run folder similar to:

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

### Tests
```bash
pytest -q
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
