# Epic 4 — Review Gate & Submission Integration

## Expanded Goal
Integrate the automation pipeline with the preview UI to complete the human-in-the-loop review gate. Support Approve/Edit/Abort actions, apply a single edit-correction pass with updated preview, then execute submission on approval with confirmation/error handling and one auto-retry.

## Story 4.1 — Review API & Eventing Contract
As a developer,
I want REST endpoints and lightweight eventing between the automation and the preview UI,
so that the UI can display summaries/screenshots and drive Approve/Edit/Abort.

Acceptance Criteria
1: FastAPI endpoints: `POST /review/session` (create), `GET /review/{id}` (fetch summary, screenshot, status), `POST /review/{id}/approve`, `POST /review/{id}/edit`, `POST /review/{id}/abort`.
2: JSON schema documented for request/response; includes `summary`, `artifacts`, `status`, `errors`.
3: Polling endpoint `GET /review/{id}/updates?since=<ts>` returns recent events; optional SSE `/review/{id}/events` when enabled.
4: 401/404/409 error cases defined; UI shows friendly toasts.
5: Contract tests validate schema stability.

## Story 4.2 — UI Wiring & Controls
As a user,
I want the preview UI wired to the Review API,
so that Approve/Edit/Abort work reliably with clear feedback.

Acceptance Criteria
1: Approve calls `/approve` and disables controls while pending; success transitions to submitting state.
2: Edit opens a shadcn `Dialog` with a text box; posting to `/edit` shows a retry-in-progress state.
3: Abort posts to `/abort` and closes the window (or returns to idle) with a toast.
4: Keyboard shortcuts invoke the same actions and respect disabled/busy states.
5: UI unit tests mock API and assert control states and toasts.

## Story 4.3 — Edit-Correction Loop (One Pass)
As an applicant,
I want to apply one round of textual corrections before submission,
so that small fixes are incorporated without leaving the flow.

Acceptance Criteria
1: Edit text is passed to the agent which attempts targeted fixes (e.g., salary value, checkbox toggles) without changing unrelated fields.
2: On success, `SUMMARY_UPDATED` is emitted and screenshot refreshed; on no-op or failure, an explanatory toast appears.
3: Exactly one correction attempt per run; subsequent edits are disallowed and UI indicates this limit.
4: All logs remain PII-redacted; diffs are summarized in `actions.log`.
5: Integration tests simulate a salary tweak and verify updated summary.

## Story 4.4 — Submission & Confirmation Handling
As an applicant,
I want the system to submit on approval and confirm outcome,
so that I know whether the application succeeded or needs attention.

Acceptance Criteria
1: On Approve (non-dry-run), agent clicks the final submit; waits for confirmation indicators.
2: Success: emits `SUBMITTED` with confirmation text/screenshot; `run.json` updated with `status=submitted`, timestamps, and `confirmation` fields.
3: Failure: emits `SUBMIT_FAILED`, captures error screenshot, and auto-retries once; if still failing, returns to Review with error reasons.
4: Domain and one-tab guardrails enforced during submit; off-domain attempts blocked and logged.
5: Tests mock success and failure pages to validate detection and retry.

## Story 4.5 — Run Finalization States
As an operator,
I want clear terminal states recorded,
so that auditability and next steps are unambiguous.

Acceptance Criteria
1: `run.json` ends with one of: `submitted`, `aborted`, `error`; includes `summary`, `artifacts`, and `events` timeline.
2: Aborted: write reason from user action; store last screenshot.
3: Error: include error taxonomy code and snapshot path; remain in Review state for user decision.
4: History append remains stubbed for Epic 5; local `run.json` completeness verified.
5: Contract tests ensure terminal-state schema.

### Rationale (Epic 4)
- Completes the human-in-the-loop flow that makes the tool trustworthy. A single correction pass keeps scope tight while addressing common last-minute edits. Submission with one retry aligns with reliability goals without masking systemic issues.

---
