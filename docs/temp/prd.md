# Job AI Auto Apply — Product Requirements Document (PRD)

> Source basis: docs/brief.md (read on 2025-09-25)

## Goals and Background Context

### Goals
- Automate SimplyHired “Quick Apply” submissions with a review gate by default
- Support multiple role-specific profiles, each with its own resume, links, and Q&A
- Operate with a stealth-first, human-like automation posture using headful Chrome
- Keep all user data and artifacts strictly local; never store PII in the cloud
- Provide a minimal preview UI (port 4950) to Approve/Edit/Abort before submit
- Persist a complete audit trail per run with screenshots and a redacted step log
- Capture and store full job description text and HTML snapshots for every run
- Avoid duplicate applications within a 30-day window via content fingerprinting
- Achieve ≥ 95% successful submits in Review mode; median submit time ≤ 120s
- Enable quick profile switching (≤ 2s) and ≤ 1 manual correction per application
- Offer a safe Dry-Run mode that never submits but exercises the full flow

### Background Context
Many job seekers repeatedly re-enter the same information across postings while juggling multiple role personas (e.g., Frontend Developer and Music Producer) that require distinct resumes and narratives. UI drift and anti-bot measures on SimplyHired can break brittle scripts, while privacy concerns make cloud-based tools unattractive. This project delivers a local-first Windows app using Browser-Use (Playwright-based, LLM-driven) to automate SimplyHired “Quick Apply” with a stealth posture and a review-first workflow. It emphasizes privacy (local storage only), reliability (artifacted audit trail and dedupe), and user control (approve/edit/abort) to increase throughput without sacrificing accuracy or trust.

### Change Log
| Date       | Version | Description                     | Author |
|------------|---------|---------------------------------|--------|
| 2025-09-25 | v0.1    | Initial PRD draft from brief    | PM John |

---

## Requirements

### Functional (FR)
- FR1: Provide a Typer-based CLI with subcommands: `apply`, `profiles`, `config`, `history`.
- FR2: Load global defaults from `config/config.yaml`; resolve precedence CLI → profile → global.
- FR3: Manage per-profile YAML (identity, Q&A, overrides) with `documents.resume_path` under `data/resumes/{profile}/resume.pdf` and persistent Chrome `user_data_dir` per profile.
- FR4: Given a SimplyHired search URL, iterate up to `--limit` items (default `2`); detect “Quick Apply”; open application flow.
- FR5: Fill forms using the active profile with heuristic selectors tolerant to A/B variants; follow top-down, human-like pacing.
- FR6: Upload the profile’s PDF resume during the application flow.
- FR7: Present a preview window (FastAPI, port `4950`) that shows at minimum the final review page screenshot with controls: Approve, Edit, Abort; apply simple textual edits and retry once; Dry-Run never submits.
- FR8: On approval, submit the application; detect confirmation or error and auto-retry once on failure; otherwise return to preview.
- FR9: Persist per-run artifacts: screenshots (default) and optional video; `actions.log` with PII redacted; `run.json` containing full submitted details.
- FR10: Append an entry to `history/history.jsonl` for every run and persist `runs/.../run.json`; capture and store full job description text and an HTML snapshot; compute a dedupe fingerprint and skip duplicates within 30 days.
- FR11: Use headful Chrome with Browser-Use stealth enabled, one-tab flows, persistent sessions, and domain guardrails to `*.simplyhired.com`.
- FR12: Provide deterministic Playwright fallbacks for uploads/quirky widgets when LLM actions are insufficient.
- FR13: Expose artifact and retention settings via config/CLI (screenshots, video, keep days) and warn at configurable storage thresholds.
- FR14: Support quick profile switching and isolation: list/select active profile; ensure user data dir and documents are profile-scoped.
- FR15: Emit clear CLI status and exit codes; redact PII in logs while preserving a complete audit trail in artifacts.
- FR16: Load OpenRouter API keys from `.env.local`; default model `deepseek/deepseek-chat-v3.1:free`; allow overrides per profile/CLI.
- FR17: Implement deduplication (fingerprint = `posting_url + sha256(job_description_full)`); allow re-apply after 30 days.
- FR18: Enforce guardrails (domain restriction, default `--limit 2`, manual login persistence) to reduce risk and brittleness.

### Non-Functional (NFR)
- NFR1: Privacy — All PII and artifacts remain local; no cloud storage of user data.
- NFR2: Performance — Median Review-mode submit ≤ 120s; preview decision ≤ 10s.
- NFR3: Reliability — ≥ 95% submit success in Review mode; auto-retry once on failure.
- NFR4: Stealth — Headful Chrome, human-like pacing, stable viewport/timezone/locale, one-tab flow, persistent sessions.
- NFR5: Security — Redact PII in step logs; store full PII only in `run.json`; secrets in `.env.local`; respect site ToS; restrict domains.
- NFR6: Usability — Profile switch ≤ 2s; ≤ 1 manual correction per application; minimal yet clear preview UI.
- NFR7: Compatibility — Windows 10/11, Chrome stable, Python 3.11+, Playwright Chromium installed.
- NFR8: Observability — Artifacts for 100% of runs; `history.jsonl` append latency ≤ 1s; error taxonomy captured.
- NFR9: Maintainability — File-first storage contracts; modular site playbooks; dry-run supports local testing.
- NFR10: Scalability — Support configurable `--limit`; retention policies and threshold warnings for storage growth.
- NFR11: Resilience — Session backup/restore; recreate on corruption; model override and backoff when default unavailable.
- NFR12: Compliance — No CAPTCHA bypass; stays within SimplyHired “Quick Apply”; do not follow off-site flows.

#### Rationale (Requirements)
- Source of truth is docs/brief.md; FRs directly map to CLI, automation flow, preview, artifacting, and history requirements described there. Trade-offs favor local-first privacy and reliability over breadth (single-site MVP). Stealth constraints (headful, pacing, domain guardrails) limit speed but reduce bot detection risk. Assumptions include availability of OpenRouter free model and Chrome on Windows. Key items needing validation: acceptable pacing defaults, edit loop UX, and JD snapshot legality for local storage.

---

## User Interface Design Goals

### Overall UX Vision
A minimal, distraction-free review experience that keeps the user firmly in control: show the final review page screenshot, summarize key extracted fields (job, company, location, answers, salary if any), and provide three clear actions (Approve, Edit, Abort). Default to Review mode for trust; allow Dry-Run to exercise the flow safely. Favor single-window focus, fast muscle-memory shortcuts, and predictable behavior.

### Key Interaction Paradigms
- Single window (Chrome app-mode) anchored to port 4950
- Approve/Edit/Abort primary actions with keyboard shortcuts: `A`, `E`, `Esc`
- Edit: lightweight text box for small corrections (e.g., “set salary to 125k”); one retry then back to review
- Deterministic states: Loading → Review → Submitting → Confirmation/Error → Back to Review (if needed)
- Human-like pacing hints and status to explain pauses (builds trust)
- Clear redaction markers in any text preview to avoid exposing PII in logs

### Primary User Journey (MVP)
1. Start: user runs CLI with a SimplyHired search URL and selects an active profile; app launches headful Chrome and prepares preview server (port 4950).
2. Discover: agent scans the left results list, opens a candidate with Quick Apply, and fills the form deterministically (no submit yet).
3. Fill: agent maps fields from profile, uploads the resume PDF, and compiles a submission summary with a pre‑submit screenshot.
4. Review: preview window shows the screenshot and summary; user chooses Approve, Edit, or Abort.
5. Edit (optional): user enters a short correction; agent attempts a single targeted retry and refreshes the summary/screenshot.
6. Approve and Submit: on approval, agent submits once; on failure, auto‑retries once, otherwise returns to Review with reasons.
7. Finalize and History: artifacts and `run.json` are written; a JSONL history entry is appended; dedupe fingerprint prevents re‑apply within 30 days.

### Component Library: shadcn/ui
- Use `shadcn/ui` (Tailwind CSS component library) for accessible, consistent, and fast-to-assemble UI components.
- Core MVP components: `Button`, `Dialog` (Edit overlay), `Card`, `Toast/Toaster` (status), `Skeleton` (loading), `Separator`, and `Spinner`.
- Implementation: Minimal React + Vite UI served as static assets by FastAPI under `/ui` and opened in Chrome app-mode; keep footprint small.
- Rationale: High-quality, accessible components reduce bespoke CSS/JS, speed up delivery, and align with desktop-only Windows target.

### Core Screens and Views
- Preview Window (MVP)
- Edit Overlay (MVP)
- Submission Confirmation / Error State (MVP)
- History View (Post-MVP) — open run folder or show a simple list with links

### Accessibility: WCAG AA
- Color contrast ≥ 4.5:1 and scalable type
- Full keyboard navigation and visible focus rings
- Descriptive labels/ARIA for buttons and status
- Alt text for screenshots plus text summary of detected fields

### Branding
- Minimal, neutral styling with a single accent color
- System fonts; prioritize clarity and speed over heavy branding

### Target Device and Platforms: Desktop Only (Windows)
- Local FastAPI server with static `/ui` (React + Vite + Tailwind + shadcn/ui)
- Fixed window size consistent with stable viewport for stealth

#### Assumptions and Rationale (UI Goals)
- Prioritizes speed, clarity, and trust over rich UI; screenshot-first aligns with “review-by-default.” Keyboard shortcuts reduce friction. shadcn/ui provides accessible, consistent components with minimal setup using Tailwind. Desktop-only (Windows) matches platform constraints in the brief and stabilizes viewport for stealth.

---

## Technical Assumptions

### Repository Structure: Monorepo
- Single repository containing: Python CLI (`Typer`), preview server (`FastAPI`), site playbooks (`sites/`), Browser-Use wrapper, and optional UI in `ui/` (React + Vite + Tailwind + shadcn/ui) built into static assets served by FastAPI.
- Rationale: Small team/codebase; simplifies versioning, local-first storage contracts, and CI. Keeps UI assets version-locked with backend logic.

### Service Architecture
- Monolith (Python): Typer orchestrates the apply flow and launches/communicates with a FastAPI preview server on port 4950 (same process via thread for simplicity on Windows).
- Browser: Headful Chrome via Browser-Use with stealth enabled; persistent `user_data_dir` per profile under `.local/browser/profiles/{profile}`; `keep_alive` for reuse across runs.
- Guardrails: Restrict to `*.simplyhired.com`; one tab/flow at a time; human-like pacing and stable viewport/locale/timezone.
- Fallbacks: Deterministic Playwright steps for uploads and nonstandard widgets when LLM actions mis-detect.
- UI Delivery: FastAPI serves static UI assets from `ui/dist` at `/ui`; Chrome app-mode opens this endpoint.

### Testing Requirements: Unit + Integration + UI + A11y
- Unit (Python): config loader/precedence; dedupe hash; PII redaction; run store/history append; artifact pathing; domain guardrails; CLI args.
- Contract/Schema: pydantic/JSON Schema for `run.json`, `history.jsonl` entries, and profile YAML; versioned contracts.
- Integration (Python, fixture-based): dry-run apply against recorded HTML snapshots/fixtures; verify artifacts, preview loop, and dedupe decisions without live submissions.
- UI Unit/Interaction (Vitest + React Testing Library): shadcn/ui controls; keyboard shortcuts (`A`/`E`/`Esc`); dialog open/close; loading states; basic roles/labels.
- Accessibility (axe-core): automated a11y scan on the preview route; ensure focus order and accessible names.
- Guardrail Tests: assert only `*.simplyhired.com` requests; deny off-domain calls in dry-run and live modes.
- Privacy Tests: seeded PII never appears in `actions.log`; allowed only in `run.json`; verify retention/rotation behaviors.
- Reliability/Windows: atomic JSONL append with file locks; session backup/restore; long paths.
- Visual Baseline (optional, local Playwright): single golden of the preview to catch layout breakage; disabled in CI by default.

#### CI vs. Local Execution
- CI: Unit + Contract + Integration (fixtures) + UI unit + a11y.
- Local Extended: add visual baseline and simulated E2E; "live" E2E only behind `--e2e` with safeguards to avoid real submissions.

### Additional Technical Assumptions and Requests
- Platform: Windows 10/11; Python 3.11+; Chrome stable; Playwright Chromium installed.
- Secrets: `.env.local` for OpenRouter keys.
- Defaults: `--limit 2`; artifact retention 30 days; storage warning thresholds configurable.
- History: JSONL `history/history.jsonl` + per-run `runs/.../run.json`; crash-safe appends on Windows with file locks.
- Dedupe: `posting_url + sha256(job_description_full)`; allow re-apply after 30 days.
- Sessions: Auto-backup last-good session per profile; restore on corruption.
- Logging: `actions.log` structured JSON with PII redaction; verbose debug toggle.
- UX: Keyboard shortcuts (`A`, `E`, `Esc`) in preview; WCAG AA targets; shadcn/ui components for speed and consistency.
- Config: `config/config.yaml` + `data/profiles/*.yaml` with precedence CLI → profile → global.

#### Rationale (Technical Assumptions)
- Choices align to the brief’s local-first, Windows-focused constraints and minimize moving parts. Monolith + Monorepo reduces operational overhead. Unit + Integration testing balances reliability with simplicity; live E2E is risky for ATS flows, so snapshots/fixtures are favored.

---

## Epic List

- Epic 1: Foundation & Review UI — Scaffold CLI, config, and preview server using shadcn/ui; deliver a working review window showing a placeholder screenshot with Approve/Edit/Abort and Dry-Run skeleton.
- Epic 2: Stealth Browser Wrapper & Profiles — Implement Browser-Use headful Chrome with stealth, per-profile sessions (`user_data_dir`), and domain guardrails; reliably open a SimplyHired search URL.
- Epic 3: SimplyHired Quick Apply Automation — Detect and drive the “Quick Apply” flow, fill fields from the active profile, upload resume, and compile a submission summary.
- Epic 4: Review Gate & Submission Integration — Feed the final review screenshot into the UI, support one-shot Edit/Retry, and submit on approval with clear confirmation/error handling.
- Epic 5: Artifacts, History & Dedupe Hardening — Persist screenshots/run.json/HTML snapshot, append history JSONL, enforce 30‑day dedupe, retention policies, storage warnings, and add Playwright fallbacks, auto-retry, and session backup/restore.

#### Rationale (Epics)
- Sequenced to deliver deployable value early: users get a working review UI in Epic 1, then stealth navigation, then real apply flow, then integrated submission, and finally durability/observability. Cross-cutting concerns (logging, redaction) appear within relevant epics, not as standalone epics.

---

## Next Steps (Preview)
- Once the Epic List is approved, we will expand each epic with stories and acceptance criteria, ensuring sequential, AI-sized vertical slices.

---

## Epic 1 — Foundation & Review UI

### Expanded Goal
Establish a working foundation that proves the review-first experience. Ship a CLI skeleton, configuration loader, and a FastAPI preview server that serves a minimal React + shadcn/ui interface. The UI must open in Chrome app-mode and render a placeholder screenshot with functional Approve/Edit/Abort and keyboard shortcuts, as a safe Dry-Run simulation.

### Story 1.1 — Project Scaffold & Config Loader
As a developer,
I want a structured repo with a Typer CLI and config loader,
so that I can run commands and manage defaults consistently.

Acceptance Criteria
1: Running `python app.py --help` lists `apply`, `profiles`, `config`, `history`.
2: `config init` creates `config/config.yaml` with documented defaults.
3: `.env.local` is read for OpenRouter keys without crashing if missing.
4: Required folders exist on first run: `config/`, `data/`, `.local/`, `runs/`, `history/`.
5: Precedence documented: CLI → profile → global.

### Story 1.2 — Preview Server Skeleton
As a user,
I want a preview window served on port 4950,
so that I can review a submission before it’s sent.

Acceptance Criteria
1: `python app.py preview --demo` starts FastAPI on 4950 and opens Chrome app-mode.
2: UI uses shadcn/ui with `Button`, `Dialog`, `Card`, and `Toast` primitives.
3: Keyboard shortcuts: `A`=Approve, `E`=Edit, `Esc`=Abort.
4: Placeholder screenshot rendered with alt text and text summary region.
5: Dry-Run mode visibly indicated; Approve/Abort only simulate actions.

### Story 1.3 — Profiles Schema & Commands
As a user,
I want to create and validate role profiles,
so that each application uses the correct identity and resume.

Acceptance Criteria
1: `profiles new <id>` writes `data/profiles/<id>.yaml` using a template.
2: Schema includes identity, Q&A, model overrides, `documents.resume_path`.
3: `profiles validate <id>` checks YAML and resume presence at `data/resumes/<id>/resume.pdf`.
4: `profiles list` shows available profiles and their status.
5: Profile switching persists for the current session.

### Story 1.4 — Run Store & Redacted Logging (Skeleton)
As an operator,
I want consistent run folders and redacted logs,
so that I can audit behavior without exposing PII.

Acceptance Criteria
1: `runs/<run_id>/` is created for each demo run with timestamps.
2: `actions.log` contains structured JSON lines with redacted PII tokens.
3: `history/history.jsonl` appends a minimal entry for demo runs.
4: Crash-safe append behavior verified on Windows.
5: Configurable retention placeholders present (no deletion yet).

### Story 1.5 — Dry-Run Demo Flow
As a cautious user,
I want a complete demo path with no external browsing,
so that I can test the UI/UX safely.

Acceptance Criteria
1: `apply --dry-run --limit 1 --demo` renders the preview UI with a canned placeholder.
2: Approve/Abort paths update a demo `run.json` and toasts status.
3: Edit opens a Dialog text box and simulates one retry.
4: A demo `run.json` is written to the run folder with summary fields.
5: No network calls to SimplyHired occur in demo mode.

#### Rationale (Epic 1)
- Focuses on trust and local-first preview before any live automation. Stories are sequenced from scaffolding → UI → profiles → logging → demo end-to-end, each completable by a single agent session and testable locally.

---

## Epic 2 — Stealth Browser Wrapper & Profiles

### Expanded Goal
Deliver a reliable, headful Chrome automation baseline that respects stealth requirements, binds browser sessions to profiles, and can open a SimplyHired search URL while enforcing domain guardrails and one-tab human-like behavior.

### Story 2.1 — Browser-Use Wrapper Initialization
As a developer,
I want a thin wrapper around Browser-Use configured for headful Chrome,
so that automation starts consistently with stealth and reuse of sessions.

Acceptance Criteria
1: `apply --dry-run --open <search_url>` launches headful Chrome with `keep_alive=true`.
2: `user_data_dir` is `.local/browser/profiles/<profile>` and persists cookies across runs.
3: Window opens with stable viewport (e.g., 1366x768) and OS locale/timezone.
4: Default model set from config/profile; override via CLI without crash.
5: Wrapper exposes `open_url`, `wait_for_idle`, and `safe_click` primitives.

### Story 2.2 — Domain Guardrails & One-Tab Policy
As an operator,
I want strict navigation guardrails and a single-tab policy,
so that automation cannot wander or look like a bot.

Acceptance Criteria
1: Allowed domains default to `*.simplyhired.com`; off-domain requests are blocked and logged.
2: Opening a new tab is prevented; attempts are redirected to the existing tab.
3: Pacing: top-down action ordering with jittered waits (100–600ms) and think-time (1–2s) before submits.
4: Status events emitted: `NAVIGATE`, `BLOCKED_DOMAIN`, `NEW_TAB_ATTEMPT`, `THINK_TIME`.
5: Unit tests assert guardrail enforcement and event emission.

### Story 2.3 — Profile Binding & Resume Availability
As a user,
I want the active profile bound to the browser session,
so that identity and documents are correctly scoped.

Acceptance Criteria
1: Active profile selection determines `user_data_dir` and model overrides at runtime.
2: Resume path resolves to `data/resumes/<profile>/resume.pdf`; missing file triggers actionable error.
3: Profile metadata is exposed to the wrapper for later field mapping (no fill yet).
4: `profiles current` shows active profile and session path.
5: Tests cover profile switching and state isolation.

### Story 2.4 — Search Page Readiness Detection
As a developer,
I want heuristics to confirm the SimplyHired search layout is ready,
so that later steps can rely on a stable structure.

Acceptance Criteria
1: Detect left list (≥10 items with job-card roles) and right detail pane.
2: Wait strategy resolves dynamic loads/spinners; emits `SEARCH_READY`.
3: Robust to common A/B variants (selectors configured by JSON map).
4: On failure, backoff+retry once, then emit `SEARCH_UNREADY` with snapshot.
5: Fixture-based tests verify readiness on 2–3 stored HTML variants.

### Story 2.5 — Session Backup and Recovery
As an operator,
I want automatic backup and restoration of profile sessions,
so that corruption or crashes don’t require re-login.

Acceptance Criteria
1: On first successful run, snapshot `user_data_dir` to `.local/browser/backups/<profile>/latest`.
2: On corruption detection, auto-restore and retry once; emit `SESSION_RESTORED`.
3: Backups keep the last 2 snapshots per profile with rotation.
4: Config flag disables backups if desired.
5: Tests simulate partial directory corruption and validate recovery.

#### Rationale (Epic 2)
- Establishes a durable, stealthy baseline and profile-scoped sessions, enabling Epic 3’s form filling without reliability surprises. Guardrails, pacing, and readiness heuristics directly mitigate anti-bot friction and layout drift.

---

## Epic 3 — SimplyHired Quick Apply Automation

### Expanded Goal
Detect and open the Quick Apply flow on a job detail, robustly map form fields (tolerant to common A/B variants), fill values from the active profile using a top-down, human-like strategy, deterministically upload the resume PDF, and compile a clear submission summary and pre-submit screenshot for the review UI. No actual submission in this epic.

### Story 3.1 — Quick Apply Discovery & Safe Open
As an applicant,
I want the agent to scan the left results list, find Quick Apply postings, safely open each Quick Apply, then return to the results to continue,
so that it can process many applications in one run without duplicates and with pagination when needed.

Acceptance Criteria
1: From a SimplyHired search page (left list + right detail), scans the left list top‑to‑bottom to identify cards with a Quick Apply marker; ignores off‑site "Apply" links.
2: For each candidate, opens the job detail (right pane) and safely opens the Quick Apply module (modal or in‑page) without submitting; emits events: `QA_CANDIDATE`, `QUICK_APPLY_OPENED` (or `QUICK_APPLY_MISSING`).
3: After safe open, closes the module (or navigates back) and returns focus to the search page, resuming scan at the next unvisited card. Maintains an in‑run visited set keyed by `posting_url`/card id to avoid re‑opening the same job. (Cross‑run dedupe is out‑of‑scope; see Epic 5.)
4: Honors `--limit N` (default 2): stops after processing N Quick Apply candidates or end‑of‑results, whichever comes first.
5: Pagination: when the current list is exhausted and the limit is not reached, detects and uses pagination controls (Next/numbered) to load the next results page and continues scanning; emits `PAGINATED_NEXT` and `END_OF_RESULTS` when appropriate.
6: Guardrails enforced throughout: single‑tab policy and allowed domains only; logs `BLOCKED_DOMAIN` on violations.
7: Fixture tests cover: (a) multiple Quick Apply markers on one page; (b) two‑page results with Next; (c) duplicate item across pages skipped by the visited set; (d) modal and in‑page variants.

### Story 3.2 — Form Structure Mapping & Selector Library
As a developer,
I want a small selector library and heuristics to map visible form labels/inputs to profile fields,
so that filling is resilient to minor label or layout changes.

Acceptance Criteria
1: JSON/YAML selector map defines label synonyms (e.g., "Full Name", "Your name").
2: Heuristics resolve label→input pairs, including radios, selects, checkboxes, and textareas.
3: Emits `FORM_MAPPED` with a structured plan of fields to fill; unknowns marked `UNMAPPED`.
4: Unit tests validate mapping for common fields and A/B label variants.
5: Unknowns fall back to a conservative skip with log entries; no crash.

### Story 3.3 — Profile-Driven Filling & Validation
As an applicant,
I want fields filled from my active profile with sensible defaults and safety checks,
so that answers are accurate and consistent.

Acceptance Criteria
1: Fills common identity, eligibility, and contact fields from profile YAML.
2: Applies constraints and transformations (e.g., strip PII from logs, normalize phone formats).
3: Radios/selects are chosen by synonym matching; textareas use concise, non-PII summaries if needed.
4: Emits `FIELD_FILLED`/`FIELD_SKIPPED` events with reasons; logs are redacted.
5: Dry-run never clicks submit; live mode stops before submit in this epic.

### Story 3.4 — Deterministic Resume Upload
As an applicant,
I want the resume PDF uploaded reliably,
so that the application includes my document every time.

Acceptance Criteria
1: Uses a deterministic Playwright file chooser to upload `data/resumes/<profile>/resume.pdf`.
2: Verifies upload success via filename/attachment indicator.
3: Retries once with backoff; on failure emits `UPLOAD_FAILED` with snapshot.
4: Respects Dry-Run by simulating upload without network/file mutation.
5: Tests mock the upload control and success indicator states.

### Story 3.5 — Submission Summary & Pre-Submit Screenshot
As a user,
I want a concise submission summary and a pre-submit screenshot,
so that I can review everything before approving.

Acceptance Criteria
1: Extracts key fields (job title, company, location, answers summary non‑PII) into a `summary` object.
2: Captures a pre-submit screenshot of the review/confirmation step if present; otherwise, composes a synthetic summary view.
3: Writes a draft `run.json` into the run folder with the `summary` but no `status=submitted`.
4: Emits `SUMMARY_READY` and stores the screenshot path in artifacts.
5: Integration tests verify `summary` contents and artifact creation in dry-run fixtures.

#### Rationale (Epic 3)
- Builds the core automation that feeds the review gate without risking premature submission. Selector library + heuristics absorb UI drift; deterministic upload covers the most brittle step; the summary provides the UI everything it needs for clear user approval in the next epic.

---

## Epic 4 — Review Gate & Submission Integration

### Expanded Goal
Integrate the automation pipeline with the preview UI to complete the human-in-the-loop review gate. Support Approve/Edit/Abort actions, apply a single edit-correction pass with updated preview, then execute submission on approval with confirmation/error handling and one auto-retry.

### Story 4.1 — Review API & Eventing Contract
As a developer,
I want REST endpoints and lightweight eventing between the automation and the preview UI,
so that the UI can display summaries/screenshots and drive Approve/Edit/Abort.

Acceptance Criteria
1: FastAPI endpoints: `POST /review/session` (create), `GET /review/{id}` (fetch summary, screenshot, status), `POST /review/{id}/approve`, `POST /review/{id}/edit`, `POST /review/{id}/abort`.
2: JSON schema documented for request/response; includes `summary`, `artifacts`, `status`, `errors`.
3: Polling endpoint `GET /review/{id}/updates?since=<ts>` returns recent events; optional SSE `/review/{id}/events` when enabled.
4: 401/404/409 error cases defined; UI shows friendly toasts.
5: Contract tests validate schema stability.

### Story 4.2 — UI Wiring & Controls
As a user,
I want the preview UI wired to the Review API,
so that Approve/Edit/Abort work reliably with clear feedback.

Acceptance Criteria
1: Approve calls `/approve` and disables controls while pending; success transitions to submitting state.
2: Edit opens a shadcn `Dialog` with a text box; posting to `/edit` shows a retry-in-progress state.
3: Abort posts to `/abort` and closes the window (or returns to idle) with a toast.
4: Keyboard shortcuts invoke the same actions and respect disabled/busy states.
5: UI unit tests mock API and assert control states and toasts.

### Story 4.3 — Edit-Correction Loop (One Pass)
As an applicant,
I want to apply one round of textual corrections before submission,
so that small fixes are incorporated without leaving the flow.

Acceptance Criteria
1: Edit text is passed to the agent which attempts targeted fixes (e.g., salary value, checkbox toggles) without changing unrelated fields.
2: On success, `SUMMARY_UPDATED` is emitted and screenshot refreshed; on no-op or failure, an explanatory toast appears.
3: Exactly one correction attempt per run; subsequent edits are disallowed and UI indicates this limit.
4: All logs remain PII-redacted; diffs are summarized in `actions.log`.
5: Integration tests simulate a salary tweak and verify updated summary.

### Story 4.4 — Submission & Confirmation Handling
As an applicant,
I want the system to submit on approval and confirm outcome,
so that I know whether the application succeeded or needs attention.

Acceptance Criteria
1: On Approve (non-dry-run), agent clicks the final submit; waits for confirmation indicators.
2: Success: emits `SUBMITTED` with confirmation text/screenshot; `run.json` updated with `status=submitted`, timestamps, and `confirmation` fields.
3: Failure: emits `SUBMIT_FAILED`, captures error screenshot, and auto-retries once; if still failing, returns to Review with error reasons.
4: Domain and one-tab guardrails enforced during submit; off-domain attempts blocked and logged.
5: Tests mock success and failure pages to validate detection and retry.

### Story 4.5 — Run Finalization States
As an operator,
I want clear terminal states recorded,
so that auditability and next steps are unambiguous.

Acceptance Criteria
1: `run.json` ends with one of: `submitted`, `aborted`, `error`; includes `summary`, `artifacts`, and `events` timeline.
2: Aborted: write reason from user action; store last screenshot.
3: Error: include error taxonomy code and snapshot path; remain in Review state for user decision.
4: History append remains stubbed for Epic 5; local `run.json` completeness verified.
5: Contract tests ensure terminal-state schema.

#### Rationale (Epic 4)
- Completes the human-in-the-loop flow that makes the tool trustworthy. A single correction pass keeps scope tight while addressing common last-minute edits. Submission with one retry aligns with reliability goals without masking systemic issues.

---

## Epic 5 — Artifacts, History & Dedupe Hardening

### Expanded Goal
Make the system durable and auditable at scale by capturing comprehensive artifacts, writing a robust append-only history with atomicity on Windows, enforcing a 30-day dedupe policy, managing storage with retention and thresholds, and finalizing reliability measures (Playwright fallbacks, retries, session backups).

### Story 5.1 — Artifact Capture & Retention Controls
As an operator,
I want controllable artifact capture and retention,
so that I can balance auditability with disk usage.

Acceptance Criteria
1: Config/CLI `--artifacts` supports `screenshots|video|both` with `screenshots` default.
2: Every significant step produces a screenshot; file paths logged in `run.json`.
3: Retention policy: default keep 30 days; `config cleanup` removes expired run folders and empty parents.
4: Storage threshold warnings at configurable GB/% thresholds; logs `STORAGE_THRESHOLD` event.
5: Tests simulate retention and threshold warnings without deleting non-expired runs.

### Story 5.2 — History JSONL Append & Atomicity
As a developer,
I want a crash-safe, atomic append to `history/history.jsonl`,
so that history is consistent even on Windows.

Acceptance Criteria
1: Append uses temp-file + rename with file locks to avoid partial writes.
2: History entry schema includes all fields from the brief (ids, timestamps, URLs, fingerprint, status, artifacts, answers summary, JD text path, HTML snapshot path).
3: Failures roll back without corrupting the file; emits `HISTORY_APPEND_FAILED` with details.
4: Unit tests inject I/O failures to verify atomicity and rollback.
5: A small `history index` utility lists last N entries with filters.

### Story 5.3 — JD Capture & HTML Snapshot
As a user,
I want the full job description text and HTML snapshot saved per run,
so that I have a complete local audit trail.

Acceptance Criteria
1: Extracts JD text from the detail pane; writes to `runs/<id>/jd.txt`.
2: Saves a sanitized HTML snapshot to `runs/<id>/page.html`.
3: Paths recorded in `run.json` and history entry.
4: Privacy: PII redaction rules applied to logs; raw JD stored as-is.
5: Fixture-based tests verify extraction and file creation.

### Story 5.4 — Dedupe Policy Enforcement (30 Days)
As an applicant,
I want the system to avoid re-applying within 30 days for the same posting + JD content,
so that I don’t spam employers.

Acceptance Criteria
1: Fingerprint = `posting_url + sha256(job_description_full)`; matches within 30 days are marked `duplicate` and skipped.
2: `--reapply` flag bypasses dedupe only after 30 days or when explicitly allowed.
3: Skipped duplicates write an entry with `status=duplicate` and reason.
4: History lookup is O(1) or batched with an index to keep performance acceptable.
5: Tests cover duplicate detection, window expiry, and reapply behavior.

### Story 5.5 — Reliability Hardening & Fallbacks
As an operator,
I want improved reliability for brittle steps,
so that transient issues don’t derail runs.

Acceptance Criteria
1: Playwright fallback paths integrated for uploads and stubborn widgets; triggered by explicit failure codes.
2: Auto-retry once on upload/submit failures with exponential backoff; emits `RETRYING` events.
3: Session backup/restore from Epic 2 finalized with rotation and metrics.
4: Error taxonomy finalized and documented; mapped to user-facing toasts and log codes.
5: Integration tests simulate failure→retry→success and failure→retry→fail paths.

#### Rationale (Epic 5)
- Locks in auditability and trust (artifacts/history), enforces respectful behavior (dedupe), and improves resilience (fallbacks/retries). Windows-focused atomic writes prevent corruption; storage controls keep local-first sustainable.

---

## Checklist Results Report

Executive Summary
- Overall PRD completeness: 92%
- MVP scope: Just Right (focused, single-site, review-first)
- Readiness for architecture: READY
- Key concerns to watch: JD HTML snapshot ToS compliance; formal JSON Schemas for `run.json` and history entries; add a brief user-journey outline for clarity.

Category Analysis
| Category                         | Status  | Critical Issues |
| -------------------------------- | ------- | --------------- |
| 1. Problem Definition & Context  | PASS    | — |
| 2. MVP Scope Definition          | PASS    | Consider copying “Out of scope (MVP)” from brief into PRD explicitly. |
| 3. User Experience Requirements  | PARTIAL | Add a one-paragraph primary user journey (entry → review → approve/edit/abort → finalize). |
| 4. Functional Requirements       | PASS    | — |
| 5. Non-Functional Requirements   | PASS    | — |
| 6. Epic & Story Structure        | PASS    | — |
| 7. Technical Guidance            | PASS    | — |
| 8. Cross-Functional Requirements | PARTIAL | Formalize JSON Schemas for `run.json` and history; monitoring/metrics minimal (acceptable for MVP). |
| 9. Clarity & Communication       | PASS    | — |

Top Issues by Priority
- BLOCKERS: None
- HIGH: (1) Confirm ToS/legal posture for saving JD HTML snapshots; add opt-out flag if needed. (2) Define JSON Schemas for `run.json` and `history.jsonl` entries and gate CI on them.
- MEDIUM: (1) Add “Out of scope (MVP)” snippet to PRD mirroring the brief. (2) Document a short primary user journey in PRD.
- LOW: Expand error taxonomy table (codes → user-facing toasts) in a follow-up doc.

MVP Scope Assessment
- Possible cuts (if needed): Visual baseline tests (keep local-only), second retry on submit (stick to one retry), early History index CLI.
- Essentials present: Review-first UI, stealth wrapper, mapping/fill + upload, artifacts + dedupe, retention settings.
- Timeline realism: Reasonable for staged delivery across five epics.

Technical Readiness
- Constraints clear (Windows, Chrome, headful, domain guardrails). Risks: anti-bot friction, layout drift; mitigated via pacing, selector library, and Playwright fallbacks. Areas for architect deep-dive: eventing contract, session backup strategy, atomic write patterns on Windows.

Recommendations
- Add JSON Schemas and contract tests (already listed in Testing Requirements). 
- Add “Out of scope (MVP)” and a short user-journey paragraph to PRD (non-blocking).
- Add a config toggle to disable JD HTML snapshot if user prefers text-only.

Final Decision: READY FOR ARCHITECT

## Next Steps
- UX Expert Prompt: Will be generated after checklist (short, focused prompt to drive UX Expert).

### Architect Prompt
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
