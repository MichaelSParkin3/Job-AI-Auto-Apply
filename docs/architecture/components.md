# Components

## CLI Orchestrator
**Responsibility:** Parse args, load config/profile, coordinate browser actions, manage artifacts/history.

**Key Interfaces:**
- Commands: `apply`, `profiles`, `config`, `history`
- IPC/HTTP calls to Preview server

**Dependencies:** Config loader, Profile manager, Browser‑Use wrapper, Artifact store

**Technology Stack:** Python 3.11, Typer

## Preview Server (BFF)
**Responsibility:** Serve UI, provide preview control endpoints, enforce guardrails.

**Key Interfaces:** `/api/run/*`, `/ui/*`

**Dependencies:** File repository, redaction utilities

**Technology Stack:** FastAPI, Uvicorn (embedded)

## Browser‑Use Controller
**Responsibility:** Headful Chromium automation with stealth posture; deterministic fallbacks for upload/widgets.

**Key Interfaces:** High-level actions (visit, detect Quick Apply, fill forms, upload resume, collect review screenshot)

**Dependencies:** Playwright, model driver (OpenRouter key)

**Implementation Notes:**
- The `BrowserUseController` lives in `apps/browser/controller.py` and wraps the upstream Browser-Use session with strongly typed primitives (`open_url`, `wait_for_idle`, `safe_click`).
- Configuration is resolved via `Settings` + profile overrides; Chrome sessions persist to `.local/browser/profiles/<profile>` and enforce a 1366×768 default viewport (overridable per profile).
- `python app.py apply open` bootstraps the controller, logs guardrail events, and returns a JSON session handle for follow-on automation stories.
- Guardrails: `NavigationGuardrails` blocks off-allowlist URLs, suppresses multi-tab attempts, emits jittered pacing/think-time waits, and records structured telemetry (`guardrail.browser.*`) for downstream run-store ingestion.

**Technology Stack:** Browser‑Use + Playwright (Python)

## Artifact & History Store
**Responsibility:** Persist screenshots, `run.json`, HTML snapshot, redacted `actions.log`, append `history.jsonl`.

**Key Interfaces:** `save_run(run)`, `append_history(entry)`, `housekeep(retentionDays)`

**Dependencies:** Windows filesystem

**Technology Stack:** Python repository module (file‑based)

## Dedupe Service
**Responsibility:** Compute fingerprint, enforce 30‑day window, bypass when expired.

**Key Interfaces:** `should_skip(posting)`, `record_fingerprint(posting)`

**Dependencies:** Hashing, history/history.jsonl

**Technology Stack:** Python utility module

```mermaid
C4Container
    title Job AI Auto Apply — Containers
    Person(user, "User")
    Container(cli, "CLI", "Python/Typer")
    Container(preview, "Preview Server", "FastAPI")
    ContainerDb(store, "Artifacts/History", "Filesystem")
    System_Ext(sh, "SimplyHired", "Web App")

    Rel(user, cli, "Runs commands")
    Rel(cli, preview, "HTTP JSON")
    Rel(preview, store, "Save/Read")
    Rel(cli, store, "Write artifacts/history")
    Rel(cli, sh, "Headful Chrome via Browser‑Use")
```

---

## Browser‑Use 0.7.x Update (2025‑09‑28)
- Controller now adapts the async Browser‑Use `BrowserSession` (event‑driven) into synchronous primitives used by the CLI (`open_url`, `wait_for_idle`, `safe_click`, `get_page_html`).
- Adapter waits for `BrowserConnectedEvent`/focus; if the window is on `chrome://newtab`/Google, it triggers a CDP `Page.navigate` fallback to the target URL to avoid stalls.
- Locale/timezone are applied via environment (`LANG`/`LC_ALL`/`TZ`), `Accept-Language`, and `--lang`; deprecated `locale`/`timezone_id` kwargs are no longer passed to `BrowserSession`.
- Session backups are created under `.local/browser/backups/<profile>` and skip Chrome cache/lock files to reduce permission errors; retention is configurable.
- Readiness selectors include a 2025 variant using `data-testid` attributes to align with current SimplyHired markup.
