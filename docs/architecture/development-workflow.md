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
python -m venv .venv && .\.venv\Scripts\pip install -U pip
pip install -e .[dev]
cd apps/ui && pnpm install && pnpm build && cd ../..
# Copy UI build into preview static dir if needed (or serve directly)
```

```bash
# Development Commands
# Start preview server (port 4950)
python -m apps.preview --demo
# Start CLI dry-run example
python -m apps.cli apply --search "<simplyhired-search-url>" --limit 2 --profile default --dry-run
# Run tests
pytest -q
cd apps/ui && pnpm test
```

## Environment Configuration
```bash
# .env.local (read locally; never commit)
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=deepseek/deepseek-chat-v3.1:free
# Optional
LOG_LEVEL=INFO
ARTIFACTS_KEEP_DAYS=30
```

---
