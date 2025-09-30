# Development Workflow

## Local Development Setup
```bash
# Prerequisites
# - Windows 10/11
# - Python 3.11+
# - Node.js 22 LTS + pnpm 9
# - Chrome stable
# - Playwright browsers: npx playwright install chromium
```

```bash
# Initial Setup
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -e .[dev]
pnpm install
pnpm run build
```

```bash
# Development Commands
# Start preview server with demo data (port 4950)
python app.py preview demo
# Reopen an existing automation run in the preview UI
python app.py preview run <run-id>
# Plan and execute a Lever dry-run iteration
python app.py apply plan --source lever-google --terms "react front end" --location "remote us" --pages 1 | Out-File lever-plan.json -Encoding utf8
python app.py apply run --plan lever-plan.json --profile default --mode review --dry-run
# Run tests
pytest -q
pnpm run test
```

## Environment Configuration
```bash
# .env.local (read locally; never commit)
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=deepseek/deepseek-chat-v3.1:free
# Optional
LOG_LEVEL=INFO
ARTIFACTS_KEEP_DAYS=30
# AI mode guardrails
AI_DECISION_MODEL=deepseek/deepseek-chat-v3.1:free
AI_AUTO_SUBMIT_CONFIDENCE=0.85
# Browser-Use logging (CLI defaults to false to keep stdout clean)
BROWSER_USE_SETUP_LOGGING=false
```

The CLI sets `BROWSER_USE_SETUP_LOGGING=false` before importing Browser-Use so discovery telemetry stays on stderr. Override to `true` when you need the upstream formatting and are not piping structured CLI output.

---

