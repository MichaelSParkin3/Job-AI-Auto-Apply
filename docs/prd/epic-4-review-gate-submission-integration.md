# Epic 4 — Human Review Queue & Decision Engine Foundation

## Expanded Goal
Lay the groundwork for AI-assisted, human-approved applying by formalizing run modes, persisting a review queue, and wiring the preview UI + CLI to a shared decision engine contract. Humans should be able to batch review multiple candidates, see draft AI hints, and override decisions without restarting a run. This epic delivers the infrastructure and UX needed for the Stage 1 MVP (AI assist with human approval); the actual LLM scoring arrives in Epic 5.

## Story 4.1 — Run Mode & Decision Engine Contract
As a developer,
I want explicit run modes and a pluggable decision engine interface,
so that the automation can reason about human vs AI responsibilities without forking the pipeline.

Acceptance Criteria
1. CLI resolves `mode` (`review|auto_review|auto_submit`) via CLI flag → profile override → global config and records it in `run.json` and telemetry.
2. Introduce a `DecisionEngine` protocol with `submit_candidate()` and `on_decision()` hooks; provide a `HumanDecisionEngine` implementation that blocks on preview UI events.
3. Decision payload schema includes `candidateId`, `outcome`, `rationale`, `confidence`, `timestamp`; persisted to `runs/<id>/decisions/*.json` and appended to `run.json`.
4. Dry-run and guardrails respect new modes (auto modes are ignored unless explicitly requested; default remains `review`).
5. Unit tests cover mode resolution precedence and serialization of the decision contract.

## Story 4.2 — Review Queue Persistence & APIs
As an operator,
I want the automation to queue multiple application candidates with deterministic state transitions,
so that I can process several pending jobs in a single session without losing context.

Acceptance Criteria
1. Introduce `ApplicationCandidate` data model (`id`, posting summary, form plan path, discoveredAt, state).
2. CLI enqueues candidates as they become “ready for review”; queue state transitions follow `discovered → planned → awaiting_decision → decided → submitted|shelved`.
3. Persist queue snapshots to `runs/<id>/queue.json` on every state change; append summary metrics to telemetry.
4. FastAPI exposes `/api/queue/{runId}` (GET) and `/api/queue/{runId}/decision` (POST) endpoints using the new decision contract; validation errors return structured `ApiError` responses.
5. Integration tests simulate two candidates, verifying queue persistence survives process restart.

## Story 4.3 — Preview UI Queue Drawer & Keyboard Flow
As a reviewer,
I want a queue-aware preview UI with keyboard navigation,
so that I can triage multiple pending applications quickly without opening new tabs.

Acceptance Criteria
1. UI adds a collapsible Queue Drawer listing pending, escalated, and recently decided candidates with badges showing status.
2. Keyboard shortcuts: `J/K` moves between queue items, `Shift+A` approves, `Shift+X` escalates back to manual review, `Shift+?` toggles shortcut legend.
3. Preview screen displays suggested outcome pill (placeholder text until Epic 5 provides AI scores) and logs any manual overrides.
4. Busy/disabled states prevent double submissions; queue updates render optimistically then reconcile with API responses.
5. Vitest/RTL coverage for queue navigation, pending counts, and keyboard handlers.

## Story 4.4 — Decision Logging & History Surfacing
As a compliance stakeholder,
I want every decision captured in artifacts and history entries,
so that AI assist and later auto modes remain auditable.

Acceptance Criteria
1. `history.jsonl` entries gain `mode`, `decisions` summary (counts, latest outcomes), and `queueDepth` metrics.
2. `runs/<id>/run.json` includes `decisions[]` and `queue` snapshots referencing stored prompt/plan artifacts.
3. CLI `history --last` shows decisions per run (approved, escalated, aborted) with timestamps.
4. Logs redact PII within rationales (hash the text, keep top-level classification) and note when redaction was applied.
5. Regression tests confirm history append remains atomic on Windows with larger payloads.

## Story 4.5 — Human Override Controls & Failsafes
As a reviewer,
I want to override or reclaim any candidate mid-run,
so that AI suggestions (coming next epic) never block me and the system recovers from edge cases.

Acceptance Criteria
1. Queue API allows `PUT /api/queue/{runId}/{candidateId}/mode` toggling between `human` and `ai` processing lanes; CLI honours overrides immediately.
2. CLI exposes `apply queue --run <id> --candidate <n> --action escalate` for power users.
3. When a candidate stalls (no decision after configurable timeout), the system emits `AUTO_FAILSAFE_TRIGGERED` and marks it for human attention.
4. Preview UI surfaces override banner with direct “Take Back” button; button enters manual decision flow without refreshing the whole run.
5. Unit tests simulate override races (AI decision arrives while user toggles) ensuring last writer wins with clear telemetry.

### Rationale (Epic 4)
This epic establishes the human-first queueing experience that underpins the AI-assisted MVP. By formalizing run modes, queue persistence, and override flows now, we guarantee that later AI capabilities (Epic 5) and full automation (Epic 6) inherit a robust, auditable foundation without duplicating plumbing.
