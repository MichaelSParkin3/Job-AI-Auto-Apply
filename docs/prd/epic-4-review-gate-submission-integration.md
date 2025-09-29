# Epic 4 â€” Human Review Queue & Decision Engine Foundation

## Expanded Goal
Lay the groundwork for AI-assisted, human-approved applying by formalizing run modes, persisting a review queue, and wiring the preview UI + CLI to a shared decision engine contract. Humans should be able to batch review multiple candidates, see draft AI hints, and override decisions without restarting a run. This epic delivers the infrastructure and UX needed for the Stage 1 MVP (AI assist with human approval); the actual LLM scoring arrives in Epic 5.

### Story 4.0 — Source Pivot: Google + Lever Apply
As an operator,
I want the agent to discover recent Lever application pages via Google and drive their on-platform forms,
so that we can continue the review-first flow with a more uniform, reliable source than SimplyHired.

Acceptance Criteria
1. Discovery uses Google with query `site:jobs.lever.co/apply <terms>` and time window (`qdr:d|w|m|y`) to collect candidates; paginates via `start`.
2. Results are filtered to `jobs.lever.co` hosts; each result opens either the `/apply` URL directly or the job page then clicks the in-page "Apply for this job" to reach the form.
3. New Lever provider (`sites/lever/*`) detects common fields by label+control mapping, fills from profile, and uploads resume deterministically.
4. Pre-submit summary and screenshot are captured exactly as in Story 3.5, feeding the review queue unchanged.
5. Domain guardrails updated for Lever (`jobs.lever.co`, optional `api.lever.co`, widget host `newassets.hcaptcha.com` load-only); single-tab policy preserved.
6. CLI flag `--source lever-google` selects this provider; default can be toggled via profile.

Notes
- This story deprecates SimplyHired for live runs but leaves code behind for later A/B comparison.

---

## Story 4.1 â€” Run Mode & Decision Engine Contract
As a developer,
I want explicit run modes and a pluggable decision engine interface,
so that the automation can reason about human vs AI responsibilities without forking the pipeline.

Acceptance Criteria
1. CLI resolves `mode` (`review|auto_review|auto_submit`) via CLI flag â†’ profile override â†’ global config and records it in `run.json` and telemetry.
2. Introduce a `DecisionEngine` protocol with `submit_candidate()` and `on_decision()` hooks; provide a `HumanDecisionEngine` implementation that blocks on preview UI events.
3. Decision payload schema includes `candidateId`, `outcome`, `rationale`, `confidence`, `timestamp`; persisted to `runs/<id>/decisions/*.json` and appended to `run.json`.
4. Dry-run and guardrails respect new modes (auto modes are ignored unless explicitly requested; default remains `review`).
5. Unit tests cover mode resolution precedence and serialization of the decision contract.

## Story 4.1.5 — Lever Apply Execution & Review Integration
As an operator,
I want the CLI to drive Lever apply forms end-to-end and feed the review queue,
so that dry-run sessions capture complete artifacts for human approval before submission.

Acceptance Criteria
1. `python app.py apply run --source lever-google` consumes `LeverGoogleDiscovery.plan` output (plan file path or freshly generated) and iterates each candidate, launching Browser-Use to reach the Lever apply form using `LeverNavigator` fallbacks.
2. For each discovered candidate, the CLI generates a `LeverFormPlan`, executes `LeverFormExecutor`, uploads the resume via `ResumeUploader`, and persists artifacts under `runs/<id>/lever/<candidateId>/` with redacted telemetry mirrored in `run.json`.
3. Each candidate is enqueued as an `ApplicationCandidate` (`discovered → planned → awaiting_decision`) with posting metadata, plan path, and resume status recorded in `queue.json` and exposed through `/api/queue/{runId}`.
4. Summary builder captures the pre-submit payload and screenshot for every candidate and appends them to the preview queue without triggering an actual Lever submission (review mode only, guardrails enforce `jobs.lever.co`, `api.lever.co`, `newassets.hcaptcha.com`).
5. Tests cover the new CLI path (unit + integration): mock Browser-Use controller to verify guardrail enforcement, queue persistence, summary artifacts, and resume upload telemetry; regression suite runs via `pytest sites/lever/tests -q`.

## Story 4.2 â€” Review Queue Persistence & APIs
As an operator,
I want the automation to queue multiple application candidates with deterministic state transitions,
so that I can process several pending jobs in a single session without losing context.

Acceptance Criteria
1. Introduce `ApplicationCandidate` data model (`id`, posting summary, form plan path, discoveredAt, state).
2. CLI enqueues candidates as they become â€œready for reviewâ€; queue state transitions follow `discovered â†’ planned â†’ awaiting_decision â†’ decided â†’ submitted|shelved`.
3. Persist queue snapshots to `runs/<id>/queue.json` on every state change; append summary metrics to telemetry.
4. FastAPI exposes `/api/queue/{runId}` (GET) and `/api/queue/{runId}/decision` (POST) endpoints using the new decision contract; validation errors return structured `ApiError` responses.
5. Integration tests simulate two candidates, verifying queue persistence survives process restart.

## Story 4.3 â€” Preview UI Queue Drawer & Keyboard Flow
As a reviewer,
I want a queue-aware preview UI with keyboard navigation,
so that I can triage multiple pending applications quickly without opening new tabs.

Acceptance Criteria
1. UI adds a collapsible Queue Drawer listing pending, escalated, and recently decided candidates with badges showing status.
2. Keyboard shortcuts: `J/K` moves between queue items, `Shift+A` approves, `Shift+X` escalates back to manual review, `Shift+?` toggles shortcut legend.
3. Preview screen displays suggested outcome pill (placeholder text until Epic 5 provides AI scores) and logs any manual overrides.
4. Busy/disabled states prevent double submissions; queue updates render optimistically then reconcile with API responses.
5. Vitest/RTL coverage for queue navigation, pending counts, and keyboard handlers.

## Story 4.4 â€” Decision Logging & History Surfacing
As a compliance stakeholder,
I want every decision captured in artifacts and history entries,
so that AI assist and later auto modes remain auditable.

Acceptance Criteria
1. `history.jsonl` entries gain `mode`, `decisions` summary (counts, latest outcomes), and `queueDepth` metrics.
2. `runs/<id>/run.json` includes `decisions[]` and `queue` snapshots referencing stored prompt/plan artifacts.
3. CLI `history --last` shows decisions per run (approved, escalated, aborted) with timestamps.
4. Logs redact PII within rationales (hash the text, keep top-level classification) and note when redaction was applied.
5. Regression tests confirm history append remains atomic on Windows with larger payloads.

## Story 4.5 â€” Human Override Controls & Failsafes
As a reviewer,
I want to override or reclaim any candidate mid-run,
so that AI suggestions (coming next epic) never block me and the system recovers from edge cases.

Acceptance Criteria
1. Queue API allows `PUT /api/queue/{runId}/{candidateId}/mode` toggling between `human` and `ai` processing lanes; CLI honours overrides immediately.
2. CLI exposes `apply queue --run <id> --candidate <n> --action escalate` for power users.
3. When a candidate stalls (no decision after configurable timeout), the system emits `AUTO_FAILSAFE_TRIGGERED` and marks it for human attention.
4. Preview UI surfaces override banner with direct â€œTake Backâ€ button; button enters manual decision flow without refreshing the whole run.
5. Unit tests simulate override races (AI decision arrives while user toggles) ensuring last writer wins with clear telemetry.

### Rationale (Epic 4)
This epic establishes the human-first queueing experience that underpins the AI-assisted MVP. By formalizing run modes, queue persistence, and override flows now, we guarantee that later AI capabilities (Epic 5) and full automation (Epic 6) inherit a robust, auditable foundation without duplicating plumbing.
