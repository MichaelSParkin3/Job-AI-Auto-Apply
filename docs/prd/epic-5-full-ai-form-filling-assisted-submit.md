# Epic 5 — Full AI Form Filling & Assisted Submit

## Expanded Goal
Deliver an end-to-end proof that the agent can operate autonomously: use Browser-Use in headful mode plus LLM guidance to map, fill, and submit Lever applications without human intervention. When the submit path is blocked (CAPTCHA, MFA, missing documents), capture a deterministic handoff package so the UI can relaunch Chrome, rehydrate the form, and leave the user at the final submit step. Successful or assisted submissions must land in history with clear provenance so we can demonstrate the MVP vision in action.

## Story 5.1 — LLM-Guided Form Plan Refinement
As a developer,
I want an LLM-assisted planner that augments existing form plans with intent- and context-aware fill instructions,
so that AI form filling can adapt to novel Lever layouts without shipping brittle hand-tuned selectors.

Acceptance Criteria
1. Extend the form planning stage to call a small LLM chain (`plan` model configurable per profile) that reviews DOM extracts, profile data, and prior run telemetry to produce normalized field intents (type, confidence, fallback strategy).
2. Persist enriched plans to `runs/<id>/plans/<candidateId>.json`, including a hashed version for auditing; dry-run mode generates deterministic fixture outputs.
3. Planner records token usage + latency in telemetry (`AUTOFILL_PLAN_READY`) with redacted prompts/responses stored under `runs/<id>/autofill/prompts/`.
4. Profiles can pin critical answers (e.g., security questions) that bypass LLM suggestions; precedence documented and enforced by unit tests.
5. Regression fixtures cover at least two Lever form variants (modal vs. full-page) and assert the planner emits structured intents for required, optional, and custom questions.

## Story 5.2 — Headful Browser-Use Auto Fill Execution
As an operator,
I want the CLI to drive Browser-Use in non-headless mode using the refined plan,
so that the agent visibly fills the application end-to-end without manual clicks.

Acceptance Criteria
1. Introduce an `AutoFillExecutor` that replays plan intents via Browser-Use primitives (`focus`, `fill`, `select`, `upload`), capturing DOM before/after for audit.
2. Executor emits granular telemetry (`AUTOFILL_FIELD_FILLED`, `AUTOFILL_FIELD_SKIPPED`, `AUTOFILL_UPLOAD_SUCCESS/FAILURE`) with redacted value lengths; screenshots written to `runs/<id>/autofill/screenshots/`.
3. CLI flag `--mode ai_autofill` (alias of `auto_review` with auto-fill enabled) launches Chrome headful, surfaces progress in the console, and records the session path used for later rehydration.
4. Guardrails enforce Lever + allowed widget domains while letting the LLM request auxiliary actions (scroll, tab switch) from a curated safe list.
5. Integration tests stub Browser-Use to verify sequencing, telemetry, and artifact paths without launching Chrome.

## Story 5.3 — Submit Attempt & Blocker Detection
As a compliance stakeholder,
I want the agent to attempt submit when all required fields are filled and gracefully detect blockers,
so that successful runs complete automatically while risky cases fall back to human control.

Acceptance Criteria
1. Executor clicks the primary submit CTA when pre-flight validation passes; confirmation pages or success toasts set `run.json.submission.status=\"submitted\"` with timestamps and confirmation snapshot.
2. Detect CAPTCHA, MFA, or unexpected dialogs using DOM heuristics plus optional vision classification; set `submission.blocked` with `reason` enum (`captcha`, `mfa`, `unknown_form_change`) and capture focused screenshot.
3. On blocker detection, automation stops before interacting with CAPTCHA, emits `AUTOFILL_HANDOFF_READY`, and serializes current form values + DOM paths into `runs/<id>/handoff/<candidateId>.json`.
4. Run summary includes boolean `autoSubmitAttempted` and `blockedReason?`; history entries log whether completion was automatic or assisted.
5. Tests simulate success, blocker, and retryable error paths, asserting telemetry, artifact capture, and safety stop behaviour.

## Story 5.4 — Assisted Submit Relaunch & UI Workflow
As a reviewer,
I want to relaunch a saved run, have the agent repopulate the form, and finish submission manually,
so that I can solve CAPTCHAs or approvals quickly without re-entering data.

Acceptance Criteria
1. Preview UI surfaces a “Needs your help to submit” banner with CTA “Resume in Browser”; clicking calls new endpoint `POST /api/run/{id}/handoff/{candidateId}/launch`.
2. CLI receives the launch request, restores the recorded Chrome profile/session, replays the saved handoff snapshot via Browser-Use, and leaves focus on the submit button without clicking.
3. UI tracks relaunch progress, marks the candidate state `handoff_ready`, and prompts the user to confirm submission outcome (Success/Still Blocked) which posts back to `POST /api/queue/{id}/handoff-confirmation`.
4. Resume flow records outcome: success updates `submission.submittedAt`, failure keeps blocker reason but increments `manualAttempts`.
5. End-to-end smoke test exercises the resume API path with mocked Browser-Use, verifying queue updates, UI state transitions, and artifact reuse.

## Story 5.5 — History, Analytics & Proof Artifacts
As an executive stakeholder,
I want indisputable evidence of autonomous form filling and assisted completion,
so that we can demonstrate the MVP vision to partners and investors.

Acceptance Criteria
1. History entries capture `automationMode=ai_autofill`, `autoSubmitOutcome=success|blocked|assisted_success`, and pointers to relevant screenshots/video.
2. CLI command `history show --ai-autofill` summarizes recent runs with counts of auto-submitted vs assisted completions and top blocker reasons.
3. Docs/QA include a repeatable demo script referencing stored artifacts, ensuring we can replay the MVP proof.
4. Telemetry adds `AUTOFILL_DEMO_COMPLETED` once a run includes at least one auto submit success; metric exported via `scripts/report_autofill_success.py`.
5. Contract tests validate JSON schema updates for `run.json` and `history.jsonl` to include the new fields.

### Rationale (Epic 5)
This epic demonstrates the core promise: AI-powered form filling that either submits autonomously or hands the baton to a human with all tedious work completed. It de-risks CAPTCHA and layout variance, captures audit-ready artifacts, and feeds the analytics needed to prove traction before scaling further automation.
