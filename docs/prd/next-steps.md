# Next Steps
- UX Expert Prompt: Will be generated after checklist (short, focused prompt to drive UX Expert).

## Architect Prompt
You are the Architect. Using `docs/prd.md` (v0.1, 2025-09-25) and core-config constraints (Windows 10/11, Python 3.11+, Chrome stable, Playwright Chromium; local-first; review-by-default), produce Architecture v4 for a Python monolith and save to `docs/architecture.md` (with shards under `docs/architecture/` if needed).

Deliverables (concise, implementation-ready):
- System Overview: context + component diagrams showing `Typer` CLI orchestrator, `FastAPI` preview server (port 4950), headful Chrome via Browser-Use (stealth), Playwright fallback, and static UI (React + Vite + Tailwind + shadcn/ui) served at `/ui` in Chrome app-mode.
- Module Boundaries & Source Tree: propose modules and filenames aligning to PRD: `app.py` (CLI), `browseruse_wrapper.py`, `sites/simplyhired.py`, `preview_server.py`, `review_api.py`, `config_loader.py`, `run_store.py`, `history_index.py`, `selector_lib/`, `mapping/`, `redaction.py`, `pacing.py`, `events.py`, `dedupe.py`, `artifacts.py`.
- Process Model (key flows):
  - Discovery loop scanning left results list with pagination, in-run visited set, honoring `--limit`.
  - Quick Apply open (modal/in-page) → mapping plan → deterministic fill → deterministic resume upload → summary + pre-submit screenshot → Review gate → one-pass Edit/Retry → Submit with one auto-retry → Finalization.
- Eventing Contract (Review): REST-first with optional SSE. Specify endpoints and schemas for: `POST /review/session`, `GET /review/{id}`, `POST /review/{id}/approve`, `POST /review/{id}/edit`, `POST /review/{id}/abort`, plus `GET /review/{id}/updates?since=ts` (polling). Enumerate event names used across the pipeline (e.g., `QA_CANDIDATE`, `SEARCH_READY`, `FORM_MAPPED`, `FIELD_FILLED`, `UPLOAD_FAILED`, `SUMMARY_READY`, `SUBMITTED`, etc.).
- Data Contracts (JSON Schema): versioned schemas for `runs/<id>/run.json` and `history/history.jsonl` entries (include sample objects). Identify required/optional fields, enums for statuses, and forward-compatibility strategy.
- Config & Profiles: structure for `config/config.yaml` and `data/profiles/*.yaml` (precedence CLI → profile → global). Document keys for: default model, artifacts, retention days, storage thresholds, domain guardrails, viewport, pacing, `user_data_dir` roots.
- Stealth & Pacing: allowed domains (`*.simplyhired.com`), one-tab policy, stable viewport/timezone/locale, human-like waits (jitter + think-time), and where these are enforced in code.
- Session Management: per-profile `user_data_dir` under `.local/browser/profiles/<profile>`, backup/restore strategy (keep last 2), corruption detection, size caps, and restore flow (`SESSION_RESTORED`).
- Windows-Safe Persistence: algorithm for atomic JSONL append (temp file + lock + rename), path conventions, and error handling (`HISTORY_APPEND_FAILED`).
- Security & Privacy: PII redaction strategy (what/where to redact), log redaction markers, `.env.local` handling, domain guardrails, no CAPTCHA bypass.
- Testing Architecture: map PRD’s “Unit + Integration + UI + a11y” to test harnesses (pytest, fixtures for HTML snapshots; Vitest/RTL; axe-core; optional Playwright visual baseline). Define seams for mocking Browser-Use and file uploads.
- Risks & Mitigations: anti-bot friction, layout drift, upload quirks, session corruption. Provide concrete mitigations and telemetry/events to observe them.
- Implementation Checkpoints: align to Epics 1–5 with increments that compile and run locally at each stage.

Decisions to Make (and recommend):
- Review transport default: polling vs SSE (recommend polling by default, SSE behind a flag).
- JD HTML snapshot toggle: config key `save_html: true|false` (recommend true by default with a CLI/profile override; document ToS considerations).
- Concurrency model: single-process with FastAPI in a background thread (simplest on Windows) vs separate process with IPC (recommend thread for MVP).
- Visual artifacts: screenshots default on; video optional.

Output Format:
- `docs/architecture.md` plus optional shards in `docs/architecture/` (v4 style). Include diagrams (ASCII or Mermaid), sequence diagrams for the apply loop and review flow, and schemas as embedded code blocks.
