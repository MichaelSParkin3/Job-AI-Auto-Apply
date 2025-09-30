# Job-AI-Auto-Apply

Local-first, review-first automation for job applications. This repo now ships the end-to-end dry-run demo experience: a Typer CLI that boots a FastAPI preview service, serves a React UI, and lets you approve/decline edits before anything is submitted.

Status: Story 4.1.6 (Lever plan Browser discovery) implemented.

## What’s New in 4.1.6
- `python app.py apply plan --source lever-google` can launch Browser-Use with `--browser-discovery` to capture SERP HTML,
  persist artifacts under `runs/<id>/plan/`, and enrich plan JSON with deduped Lever results.
- Programmable Search support: use `--programmable-search` together with `GOOGLE_CSE_KEY`/`GOOGLE_CSE_CX` (or CLI overrides)
  to call Google’s Custom Search API when headless discovery is preferred.
- Plan guardrails now record Google allowlist domains alongside Lever defaults so run summaries reflect the expanded surface.

## What’s New in 3.3
- `python app.py apply open` now replays the persisted SimplyHired `FormFillPlan` instead of re-scraping HTML. The new
  `FormFillExecutor` drives Browser-Use via high-level primitives (`fill_text`, `set_select_value`, `set_radio_value`,
  `set_checkbox_state`, `focus`) and emits `FIELD_*` telemetry for every attempt.
- `ProfileAnswerResolver` normalises profile answers (trimmed strings, lower-cased email, E.164-style phone output,
  override fallbacks) and generates masked previews so CLI logs and artifacts never leak raw PII.
- Run persistence adds a `formFill` payload to `run.json` and `history.jsonl`, summarising filled/skipped/issue counts per
  step. The CLI prints a per-step table for quick inspection during dry runs and records validation warnings for empty
  required fields.


## What’s New in 3.1.5
- Upgraded to Browser‑Use 0.7.x with an adapter that waits for BrowserConnectedEvent/agent focus and exposes sync primitives (`open_url`, `wait_for_idle`, `safe_click`, `get_page_html`).
- Added CDP `Page.navigate` fallback to avoid "stuck on Google/new tab" during first navigation.
- Applied locale/timezone via environment (`LANG`/`LC_ALL`/`TZ`), `Accept-Language`, and `--lang` (no deprecated kwargs).
- Updated SimplyHired readiness selectors with a 2025 `data-testid` variant; discovery detects inline vs modal Quick Apply after card click.
- Session backups: live runs default to backups disabled unless explicitly enabled; when enabled, cache/lock files are skipped.
- Windows console output set to UTF‑8 to avoid emoji logging crashes; you can also export `PYTHONIOENCODING=utf-8`.
- Docs: architecture and PRD updated; README includes a “Browser‑Use 0.7.x Notes” section plus upstream links.

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

## Browser‑Use 0.7.x Notes
- Event‑driven lifecycle: we adapt Browser‑Use’s async `BrowserSession` to synchronous CLI primitives. On launch we wait for `BrowserConnectedEvent`/focus; if the browser opens on `chrome://newtab` or Google, we issue a CDP `Page.navigate` fallback to your target URL.
- Locale/timezone: now applied via env (`LANG`/`LC_ALL`/`TZ`), `Accept-Language`, and Chrome `--lang`. Deprecated `locale`/`timezone_id` kwargs are not used.
- Readiness selectors: SimplyHired SERP support includes a 2025 variant using `data-testid` to match current markup.
- Session backups: live runs default to backups disabled (override with `--session-backups`); when enabled, cache/lock files are skipped to avoid permissions noise.
- Windows console UTF‑8: the CLI configures stdout/stderr for UTF‑8 to avoid emoji logging crashes; you can also set `PYTHONIOENCODING=utf-8`.
- Docs: see https://docs.browser-use.com/introduction and https://docs.browser-use.com/changelog for upstream updates.

### Environment Variables
Create `.env.local` at repo root (optional):
```env
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=deepseek/deepseek-chat-v3.1:free
GOOGLE_CSE_KEY=...        # optional: Google Programmable Search API key
GOOGLE_CSE_CX=...         # optional: Programmable Search engine id
```
The app logs a JSON warning if `.env.local` is missing and continues. When Programmable Search credentials are present the CLI
can use `--programmable-search` to call Google’s Custom Search API without launching Browser-Use.

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

`profiles current` returns the resolved session directory, resume presence, and browser overrides so you can confirm bindings before launching Browser-Use. Validation now surfaces actionable JSON errors (`profiles.validation_failed`) when the resume is missing or schema checks fail.

> **Upgrading from earlier commits?** Create folders under `data/resumes/<id>/` and move your existing resumes there before running `profiles validate`.

### Browser-Use Session Bootstrap
Use the new `apply open` command to launch Browser-Use in headful Chrome with profile-bound persistence:

> **Release Notes & Docs:** The automation targets Browser-Use 0.7.9. Bookmark the official [introduction](https://docs.browser-use.com/introduction) and [changelog](https://docs.browser-use.com/changelog) so you can track breaking CDP or event lifecycle changes before updating selector heuristics.

```bash
# Launch a dry-run Browser-Use session for the active profile
python app.py apply open "https://www.simplyhired.com/search?q=python&l=remote"

# Override the profile and Browser-Use model for this invocation
python app.py apply open "https://www.simplyhired.com/search?q=python" \
  --profile frontend-dev \
  --model deepseek/deepseek-r1:free
```

The command resolves the Chrome `user_data_dir` to `.local/browser/profiles/<profile>`, honors overrides from `config/config.yaml` or `data/profiles/<id>.yaml`, and returns a JSON payload with the session identifier plus a `profile` object describing the active binding (resume path, QA overrides, guardrails). If the selected profile fails validation or the resume PDF is missing, the CLI exits with `profiles.validation_failed` before launching Chrome. Dry-run mode continues to fall back to the `demo` profile only when no active profile is configured.

After the search readiness check succeeds the CLI now snapshots the resolved session directory to `.local/browser/backups/<profile>/` and records the result under the `backups` key in the JSON response. Restores run automatically when Chrome launch detects a corrupted profile (e.g., missing `Preferences`), retrying exactly once before surfacing an error. Operators can opt out per run with `--session-backups/--no-session-backups` or by setting `browser_session_backups.enabled` in the global/profile config files. Run metadata (`runs/<id>/run.json`) keeps the same `sessionBackup` structure so history tooling can inspect the latest snapshot and any restore attempts.

### Lever Plan Discovery Modes
- `python app.py apply plan --browser-discovery` launches Browser-Use for each SERP URL in the generated plan, saves the raw HTML
  under `runs/<id>/plan/serp-page-*.html`, and populates the emitted JSON with unique Lever results. Guardrails expand to include
  `www.google.com`, `*.google.com`, and `consent.google.com` alongside the existing Lever allowlist.
- `--programmable-search` prefers Google’s Programmable Search JSON API when `GOOGLE_CSE_KEY`/`GOOGLE_CSE_CX` (or the CLI
  overrides `--google-cse-key/--google-cse-cx`) are provided. This mode avoids launching Chrome and still emits the enriched
  `results` array.
- If both toggles are supplied, Programmable Search takes precedence; omitting both preserves the original headless HTTP fetch
  behaviour from Story 4.0.

#### Stealth Guardrails & Pacing
- **Domain allowlist** – navigation is limited to the configured domains (`browser.allowed_domains`). Profile YAML can append additional domains per-identity.
- **Single-tab enforcement** – attempts to spawn a new tab/window are blocked and logged as `guardrail.browser.NEW_TAB_ATTEMPT` events.
- **Human pacing defaults** – each action injects jittered waits (100–600 ms) and optional think-time ranges (1–2 s) before critical interactions. Tweak via `browser.pacing.wait_jitter_ms` and `browser.pacing.think_time_range_s` in `config/config.yaml`, CLI overrides (`--browser.allowed_domains`, `--browser.pacing.*`), or profile overrides.

#### Form Fill Execution (Story 3.3)
- After discovery produces a `FormFillPlan`, the CLI resolves answers through `ProfileAnswerResolver`, which merges profile YAML
  fields, QA overrides, and derived values (e.g., formatted phone, LinkedIn URL). Missing data results in `FIELD_SKIPPED`
  telemetry with structured reasons instead of placeholder text.
- `FormFillExecutor` issues high-level controller actions (`focus`, `fill_text`, `set_select_value`, `set_radio_value`,
  `set_checkbox_state`) with guardrail pacing and a single retry for transient failures. Every attempt emits redacted
  `FIELD_FILL_STARTED`, `FIELD_FILLED`, `FIELD_SKIPPED`, and `FIELD_RETRY` events.
- Required widgets are validated post-fill via `get_field_state`; empty inputs log `FIELD_VALIDATION_FAILED` warnings and are
  surfaced in the CLI summary table.
- Completed runs persist a `formFill` payload alongside discovery/mapping artifacts in `runs/<id>/run.json` and append a
  matching history entry so review tooling can track filled vs skipped counts over time.
- **Structured telemetry** – navigation, tab suppression, pacing waits, and think-time pauses stream through the `log_event` pipeline so `actions.log` and downstream tooling can observe guardrail posture.

#### Resume Upload (Story 3.4)
- `BrowserUseController.upload_file` triggers the Playwright file chooser deterministically, redacts file metadata (name,
  size, SHA-256), and emits `UPLOAD_STARTED`/`UPLOAD_COMPLETED`/`UPLOAD_FAILED` events. Dry-run mode simulates the chooser
  without touching disk while still exercising telemetry paths.
- `ResumeUploader` validates the configured profile resume, invokes the controller primitive, confirms DOM attachment via
  `get_field_state(..., widget_type="file")`, and retries once with guardrail jitter before capturing an HTML artifact on
  persistent failure.
- Successful runs append a `resumeUpload` block to `runs/<id>/run.json`, record a history entry, and print a one-line CLI
  summary (status, attempt count, simulated flag). Failures write redacted diagnostics plus an HTML snapshot to
  `runs/<id>/resume/` for QA review.

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
