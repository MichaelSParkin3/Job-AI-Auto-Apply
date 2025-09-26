# Technical Assumptions

## Repository Structure: Monorepo
- Single repository containing: Python CLI (`Typer`), preview server (`FastAPI`), site playbooks (`sites/`), Browser-Use wrapper, and optional UI in `ui/` (React + Vite + Tailwind + shadcn/ui) built into static assets served by FastAPI.
- Rationale: Small team/codebase; simplifies versioning, local-first storage contracts, and CI. Keeps UI assets version-locked with backend logic.

## Service Architecture
- Monolith (Python): Typer orchestrates the apply flow and launches/communicates with a FastAPI preview server on port 4950 (same process via thread for simplicity on Windows).
- Browser: Headful Chrome via Browser-Use with stealth enabled; persistent `user_data_dir` per profile under `.local/browser/profiles/{profile}`; `keep_alive` for reuse across runs.
- Guardrails: Restrict to `*.simplyhired.com`; one tab/flow at a time; human-like pacing and stable viewport/locale/timezone.
- Fallbacks: Deterministic Playwright steps for uploads and nonstandard widgets when LLM actions mis-detect.
- UI Delivery: FastAPI serves static UI assets from `ui/dist` at `/ui`; Chrome app-mode opens this endpoint.

## Testing Requirements: Unit + Integration + UI + A11y
- Unit (Python): config loader/precedence; dedupe hash; PII redaction; run store/history append; artifact pathing; domain guardrails; CLI args.
- Contract/Schema: pydantic/JSON Schema for `run.json`, `history.jsonl` entries, and profile YAML; versioned contracts.
- Integration (Python, fixture-based): dry-run apply against recorded HTML snapshots/fixtures; verify artifacts, preview loop, and dedupe decisions without live submissions.
- UI Unit/Interaction (Vitest + React Testing Library): shadcn/ui controls; keyboard shortcuts (`A`/`E`/`Esc`); dialog open/close; loading states; basic roles/labels.
- Accessibility (axe-core): automated a11y scan on the preview route; ensure focus order and accessible names.
- Guardrail Tests: assert only `*.simplyhired.com` requests; deny off-domain calls in dry-run and live modes.
- Privacy Tests: seeded PII never appears in `actions.log`; allowed only in `run.json`; verify retention/rotation behaviors.
- Reliability/Windows: atomic JSONL append with file locks; session backup/restore; long paths.
- Visual Baseline (optional, local Playwright): single golden of the preview to catch layout breakage; disabled in CI by default.

### CI vs. Local Execution
- CI: Unit + Contract + Integration (fixtures) + UI unit + a11y.
- Local Extended: add visual baseline and simulated E2E; "live" E2E only behind `--e2e` with safeguards to avoid real submissions.

## Additional Technical Assumptions and Requests
- Platform: Windows 10/11; Python 3.11+; Chrome stable; Playwright Chromium installed.
- Secrets: `.env.local` for OpenRouter keys.
- Defaults: `--limit 2`; artifact retention 30 days; storage warning thresholds configurable.
- History: JSONL `history/history.jsonl` + per-run `runs/.../run.json`; crash-safe appends on Windows with file locks.
- Dedupe: `posting_url + sha256(job_description_full)`; allow re-apply after 30 days.
- Sessions: Auto-backup last-good session per profile; restore on corruption.
- Logging: `actions.log` structured JSON with PII redaction; verbose debug toggle.
- UX: Keyboard shortcuts (`A`, `E`, `Esc`) in preview; WCAG AA targets; shadcn/ui components for speed and consistency.
- Config: `config/config.yaml` + `data/profiles/*.yaml` with precedence CLI → profile → global.

### Rationale (Technical Assumptions)
- Choices align to the brief’s local-first, Windows-focused constraints and minimize moving parts. Monolith + Monorepo reduces operational overhead. Unit + Integration testing balances reliability with simplicity; live E2E is risky for ATS flows, so snapshots/fixtures are favored.

---
