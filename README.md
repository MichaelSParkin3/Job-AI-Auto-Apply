# Job-AI-Auto-Apply

Local-first, review-first automation for job applications. This repo currently ships a minimal CLI scaffold and config loader, with a roadmap for a Preview server (FastAPI) and a React UI that lets you approve/decline edits before anything is submitted.

Status: Story 1.1 (CLI + config) implemented; next is Story 1.2 (Preview Server Skeleton).

## Why
- Privacy by default: runs on your machine; artifacts stored locally
- Review-first UX: no blind submissions — you approve before actions
- Deterministic demo flow: safe dry-run path to validate the stack

## Features (current)
- Typer CLI with subcommands: `apply`, `profiles`, `config`, `history`
- Config loader with precedence: CLI > profile > global `config/config.yaml`
- Idempotent `config init` + required runtime folders creation
- Optional `.env.local` for OpenRouter; missing file is a warning, not an error
- JSON event logging primitives and `ApiError` shape placeholder

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
```

### Environment Variables
Create `.env.local` at repo root (optional):
```env
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=deepseek/deepseek-chat-v3.1:free
```
The app logs a JSON warning if `.env.local` is missing and continues.

### Profiles (skeleton)
```bash
python app.py profiles list        # lists files in data/profiles/*.yaml
```

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
