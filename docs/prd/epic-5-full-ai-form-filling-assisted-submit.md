# Epic 5 â€” Full AI Form Filling & Assisted Submit

## Expanded Goal
Deliver an end-to-end proof that the agent can operate autonomously: use Browser-Use in headful mode plus LLM guidance to map, fill, and submit Lever applications without human intervention. When the submit path is blocked (CAPTCHA, MFA, missing documents), capture a deterministic handoff package so the UI can relaunch Chrome, rehydrate the form, and leave the user at the final submit step. Successful or assisted submissions must land in history with clear provenance so we can demonstrate the MVP vision in action.

## Story 5.2.1  Resume-First + Analysis Wait
As an operator, I want the agent to upload the resume first, wait for Levers resume analysis (e.g., Analyzing ? Success!) to complete, then validate and fill remaining fields before proceeding (submit if allowed).
## Story 5.3 — AI Answer Orchestrator & Drafting Pipeline
As the automation architect,
I want the agent to resolve missing field answers using a governed LLM fallback,
so that Lever applications can be completed end-to-end even when the profile lacks pre-saved responses.

Acceptance Criteria
1. Introduce an `AnswerOrchestrator` service that enforces precedence: deterministic profile answers -> resume-derived facts -> cached run/session answers -> LLM draft. The orchestrator must expose a synchronous API consumed by the Autofill Executor and planner, returning `{value, source, confidence, rationaleDigest}` and recording provenance in `run.json.answers[]`.
2. Define an LLM prompt/response contract (`AnswerDraftRequest`, `AnswerDraftResponse`) including field metadata, resume/profile snippets, value format hints, and expected validation rules. Responses must include machine-readable confidence (0-1) and rationale text limited to 512 characters; invalid responses trigger deterministic fallbacks with `reason=validation_failed`.
3. Persist every drafted answer under `runs/<id>/answers/<fieldId>.json` (redacted length hashes only) plus a reviewer-friendly markdown summary. Emit telemetry `AI_FIELD_DRAFTED` (success) or `AI_FIELD_DRAFT_FAILED` (fallback path) with model, latency, and confidence percentiles aggregated per run.
4. Extend configuration so profiles can set `automation.answerPolicies` (min confidence for auto-submit, allowSaveToProfile flag) and add site-level defaults in `sites/lever/config.yaml`. CLI flags `--no-answer-llm` and `--min-answer-confidence` override profile defaults for QA.
5. Update regression suites (unit + integration) to cover answer precedence, LLM schema validation, telemetry emission, and deterministic fallbacks when the LLM is disabled or times out. Tests must stub the OpenRouter client and assert that saved profile answers bypass the draft call.

## Story 5.4 — Reviewer UX & Answer Approval Loop
As a reviewer,
I want to inspect drafted answers with confidence/rationale context and choose whether to apply or save them,
so that AI assistance accelerates submissions without sacrificing control.

Acceptance Criteria
1. Preview UI queue drawer displays each drafted answer with metadata: source (Profile/Resume/LLM), confidence %, rationale snippet, and last-updated timestamp. Rows include actions `Apply`, `Apply & Save`, `Edit`, `Edit & Save`, and `Reject`, each dispatching to new API endpoints.
2. Backend exposes REST endpoints (`POST /api/run/{id}/answers/{fieldId}/apply`, `/save`, `/reject`, `/edit`) that update run artifacts and, when applicable, persist approved answers to the user profile. Responses return updated field state plus telemetry acknowledgement tokens.
3. CLI/Autofill executor consumes reviewer decisions: approved answers update the form plan/executor queue, rejected answers mark the field for manual fill, and edits propagate to Browser-Use before submission resumes.
4. Telemetry `AI_FIELD_REVIEWED` captures reviewer decisions (approve/save/edit/reject) with confidence buckets but no raw text. History entries record when drafted answers were promoted to profiles for auditing.
5. Integration tests (UI + API) simulate approve/save/edit flows with mocked Browser-Use, verifying optimistic UI updates, profile persistence, and rollback on API failure. Accessibility checks ensure drafted-answer controls meet WCAG 2.1 AA colour/ARIA requirements.

## Story 5.5 — Profile Answer Evolution & Analytics
As a product analyst,
I want the system to learn from reviewer-approved answers and surface analytics on draft accuracy,
so that we can improve confidence policies and demonstrate quality improvements over time.

Acceptance Criteria
1. Extend profile schema to track answer provenance (`source`, `lastReviewedBy`, `confidenceHistory[]`, `firstDraftedAt`). Saving a reviewer-approved answer updates these fields and invalidates superseded resume facts.
2. Introduce nightly (or on-demand) report generation `scripts/report_ai_answer_quality.py` summarizing draft counts, approval rates per confidence bucket, and top rejected question categories. Reports stored under `history/analytics/ai-answers/`.
3. Update monitoring dashboards/telemetry to expose gauges `ai_answers.drafted`, `ai_answers.approved`, `ai_answers.saved_to_profile`, and `ai_answers.rejected`. Alerts trigger when rejection rate exceeds configurable thresholds.
4. Documentation updates (user guide + troubleshooting) outline how AI-drafted answers work, how to opt-out per profile, and privacy guarantees (prompt redaction, local storage). QA checklist expanded to verify reporting outputs and profile persistence integrity.
5. Regression tests cover profile schema migrations, report generation edge cases (no drafts, 100% rejects), and telemetry export compatibility with existing monitoring pipeline.

## Story 5.6 — Submit Attempt & Blocker Detection
1. Executor clicks the primary submit CTA when pre-flight validation passes; confirmation pages or success toasts set `run.json.submission.status="submitted"` with timestamps and confirmation snapshot.

## Story 5.7 — Assisted Submit Relaunch & UI Workflow
1. Preview UI surfaces a "Needs your help to submit" banner with CTA "Resume in Browser"; clicking calls new endpoint `POST /api/run/{id}/handoff/{candidateId}/launch`.
## Story 5.8 — History, Analytics & Proof Artifacts

3. Planner records token usage + latency in telemetry (`AUTOFILL_PLAN_READY`) with redacted prompts/responses stored under `runs/<id>/autofill/prompts/`.
4. Profiles can pin critical answers (e.g., security questions) that bypass LLM suggestions; precedence documented and enforced by unit tests.
5. Regression fixtures cover at least two Lever form variants (modal vs. full-page) and assert the planner emits structured intents for required, optional, and custom questions.

## Story 5.2 â€” Headful Browser-Use Auto Fill Execution
As an operator,
I want the CLI to drive Browser-Use in non-headless mode using the refined plan,
so that the agent visibly fills the application end-to-end without manual clicks.

Acceptance Criteria
1. Introduce an `AutoFillExecutor` that replays plan intents via Browser-Use primitives (`focus`, `fill`, `select`, `upload`), capturing DOM before/after for audit.
2. Executor emits granular telemetry (`AUTOFILL_FIELD_FILLED`, `AUTOFILL_FIELD_SKIPPED`, `AUTOFILL_UPLOAD_SUCCESS/FAILURE`) with redacted value lengths; screenshots written to `runs/<id>/autofill/screenshots/`.
3. CLI flag `--mode ai_autofill` (alias of `auto_review` with auto-fill enabled) launches Chrome headful, surfaces progress in the console, and records the session path used for later rehydration.
4. Guardrails enforce Lever + allowed widget domains while letting the LLM request auxiliary actions (scroll, tab switch) from a curated safe list.
5. Integration tests stub Browser-Use to verify sequencing, telemetry, and artifact paths without launching Chrome.


## Story 5.2.1 — Resume-First + Analysis Wait
As an operator, I want the agent to upload the resume first, wait for Lever’s resume analysis (e.g., ‘Analyzing…’ ? ‘Success!’) to complete, then validate and fill remaining fields before proceeding (submit if allowed).

Acceptance Criteria (summary)
1. Upload resume before any autofill actions; emit RESUME_ANALYSIS_STARTED.
2. Wait for success indicator or timeout; emit RESUME_ANALYSIS_DONE/RESUME_ANALYSIS_TIMEOUT.
3. Validate auto-populated name/email/phone/links, overwrite with profile answers if invalid, then fill remaining fields; emit RESUME_FIELDS_VALIDATED.
4. Preview after fills; submit only in allowed modes; keep existing artifacts/telemetry.
5. Configurable selectors/timeouts in sites/lever config; unit tests cover success/timeout paths.

(See docs/stories/5.2.1.resume-first-wait-for-analysis.md for full details.)
## Story 5.3 â€” Submit Attempt & Blocker Detection
As a compliance stakeholder,
I want the agent to attempt submit when all required fields are filled and gracefully detect blockers,
so that successful runs complete automatically while risky cases fall back to human control.

Acceptance Criteria
1. Executor clicks the primary submit CTA when pre-flight validation passes; confirmation pages or success toasts set `run.json.submission.status=\"submitted\"` with timestamps and confirmation snapshot.
2. Detect CAPTCHA, MFA, or unexpected dialogs using DOM heuristics plus optional vision classification; set `submission.blocked` with `reason` enum (`captcha`, `mfa`, `unknown_form_change`) and capture focused screenshot.
3. On blocker detection, automation stops before interacting with CAPTCHA, emits `AUTOFILL_HANDOFF_READY`, and serializes current form values + DOM paths into `runs/<id>/handoff/<candidateId>.json`.
4. Run summary includes boolean `autoSubmitAttempted` and `blockedReason?`; history entries log whether completion was automatic or assisted.
5. Tests simulate success, blocker, and retryable error paths, asserting telemetry, artifact capture, and safety stop behaviour.

## Story 5.4 â€” Assisted Submit Relaunch & UI Workflow
As a reviewer,
I want to relaunch a saved run, have the agent repopulate the form, and finish submission manually,
so that I can solve CAPTCHAs or approvals quickly without re-entering data.

Acceptance Criteria
1. Preview UI surfaces a â€œNeeds your help to submitâ€ banner with CTA â€œResume in Browserâ€; clicking calls new endpoint `POST /api/run/{id}/handoff/{candidateId}/launch`.
2. CLI receives the launch request, restores the recorded Chrome profile/session, replays the saved handoff snapshot via Browser-Use, and leaves focus on the submit button without clicking.
3. UI tracks relaunch progress, marks the candidate state `handoff_ready`, and prompts the user to confirm submission outcome (Success/Still Blocked) which posts back to `POST /api/queue/{id}/handoff-confirmation`.
4. Resume flow records outcome: success updates `submission.submittedAt`, failure keeps blocker reason but increments `manualAttempts`.
5. End-to-end smoke test exercises the resume API path with mocked Browser-Use, verifying queue updates, UI state transitions, and artifact reuse.

## Story 5.5 â€” History, Analytics & Proof Artifacts
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

