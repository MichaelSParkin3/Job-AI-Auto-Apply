# Epic 2 — Stealth Browser Wrapper & Profiles

## Expanded Goal
Deliver a reliable, headful Chrome automation baseline that respects stealth requirements, binds browser sessions to profiles, and can open a SimplyHired search URL while enforcing domain guardrails and one-tab human-like behavior.

## Story 2.1 — Browser-Use Wrapper Initialization
As a developer,
I want a thin wrapper around Browser-Use configured for headful Chrome,
so that automation starts consistently with stealth and reuse of sessions.

Acceptance Criteria
1: `apply --dry-run --open <search_url>` launches headful Chrome with `keep_alive=true`.
2: `user_data_dir` is `.local/browser/profiles/<profile>` and persists cookies across runs.
3: Window opens with stable viewport (e.g., 1366x768) and OS locale/timezone.
4: Default model set from config/profile; override via CLI without crash.
5: Wrapper exposes `open_url`, `wait_for_idle`, and `safe_click` primitives.

## Story 2.2 — Domain Guardrails & One-Tab Policy
As an operator,
I want strict navigation guardrails and a single-tab policy,
so that automation cannot wander or look like a bot.

Acceptance Criteria
1: Allowed domains default to `*.simplyhired.com`; off-domain requests are blocked and logged.
2: Opening a new tab is prevented; attempts are redirected to the existing tab.
3: Pacing: top-down action ordering with jittered waits (100–600ms) and think-time (1–2s) before submits.
4: Status events emitted: `NAVIGATE`, `BLOCKED_DOMAIN`, `NEW_TAB_ATTEMPT`, `THINK_TIME`.
5: Unit tests assert guardrail enforcement and event emission.

## Story 2.3 — Profile Binding & Resume Availability
As a user,
I want the active profile bound to the browser session,
so that identity and documents are correctly scoped.

Acceptance Criteria
1: Active profile selection determines `user_data_dir` and model overrides at runtime.
2: Resume path resolves to `data/resumes/<profile>/resume.pdf`; missing file triggers actionable error.
3: Profile metadata is exposed to the wrapper for later field mapping (no fill yet).
4: `profiles current` shows active profile and session path.
5: Tests cover profile switching and state isolation.

## Story 2.4 — Search Page Readiness Detection
As a developer,
I want heuristics to confirm the SimplyHired search layout is ready,
so that later steps can rely on a stable structure.

Acceptance Criteria
1: Detect left list (≥10 items with job-card roles) and right detail pane.
2: Wait strategy resolves dynamic loads/spinners; emits `SEARCH_READY`.
3: Robust to common A/B variants (selectors configured by JSON map).
4: On failure, backoff+retry once, then emit `SEARCH_UNREADY` with snapshot.
5: Fixture-based tests verify readiness on 2–3 stored HTML variants.

## Story 2.5 — Session Backup and Recovery
As an operator,
I want automatic backup and restoration of profile sessions,
so that corruption or crashes don’t require re-login.

Acceptance Criteria
1: On first successful run, snapshot `user_data_dir` to `.local/browser/backups/<profile>/latest`.
2: On corruption detection, auto-restore and retry once; emit `SESSION_RESTORED`.
3: Backups keep the last 2 snapshots per profile with rotation.
4: Config flag disables backups if desired.
5: Tests simulate partial directory corruption and validate recovery.

### Rationale (Epic 2)
- Establishes a durable, stealthy baseline and profile-scoped sessions, enabling Epic 3’s form filling without reliability surprises. Guardrails, pacing, and readiness heuristics directly mitigate anti-bot friction and layout drift.

---
