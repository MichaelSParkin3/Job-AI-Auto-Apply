# Epic 6 — AI Decision Engine & Advisory Mode

## Expanded Goal
Deliver the AI-assisted MVP by wiring the LLM decision engine into the queue from Epic 4 and the autonomous fill groundwork in Epic 5. The system should generate structured recommendations with confidence scores, expose rationale summaries to reviewers, and gracefully fall back when confidence is low. Humans remain the final approvers; no auto submission occurs in this epic.

## Story 6.1 — Prompt Assembly & Context Gathering
As a developer,
I want a reusable prompt builder that pulls from artifacts and profiles,
so that AI decisions have consistent, auditable inputs.

Acceptance Criteria
1. Prompt builder consumes job summary, profile highlights, form fill plan, and recent decision history; all inputs redact PII beyond what’s needed for the decision.
2. Prompts/responses stored under `runs/<id>/decisions/prompts/<candidateId>.json` with hashed references in logs.
3. Support configurable model + temperature per profile (`profiles/<id>.yaml` `automation` block).
4. Unit tests verify deterministic prompt structure given fixture data.

## Story 6.2 — LLM Decision Engine Implementation
As an operator,
I want AI-suggested decisions with confidence scores,
so that I can approve routine applications quickly while reviewing the rationale.

Acceptance Criteria
1. Implement `LLMDecisionEngine` that calls OpenRouter model, parses structured JSON output (`outcome`, `confidence`, `rationale`, `requestedChanges[]`).
2. Confidence threshold defaults to 0.85; values below threshold emit `needs_review` and push candidate back to human lane.
3. Telemetry events: `AUTO_DECISION` (always logged), `AUTO_OVERRIDE` (when human differs), `AUTO_FAILSAFE_TRIGGERED` (LLM error or invalid response).
4. Dry-run mode skips network call and returns stub suggestion for testing.
5. Integration test stubs model responses to cover approve/abort/edit/needs_review paths.

## Story 6.3 — Preview UI AI Insight Panel
As a reviewer,
I want to see clear AI recommendations with rationale,
so that I can accept or modify them quickly.

Acceptance Criteria
1. Preview UI displays AI outcome pill, confidence badge, and collapsible rationale summary.
2. “Accept AI Suggestion” button approves immediately but still logs human as final decision; “Adjust & Approve” opens edit dialog seeded with AI `requestedChanges`.
3. Low-confidence (< threshold) suggestions show warning state and default to manual review.
4. UI indicates when AI timed out or failed; provides quick “Re-run AI” action.
5. Frontend tests verify state transitions, badge rendering, and override telemetry payloads.

## Story 6.4 — Queue Prioritization & Escalation Rules
As a reviewer,
I want AI-sorted queues that surface the easiest wins first,
so that I can maximize throughput when trusting the suggestions.

Acceptance Criteria
1. Queue ordering sorts by AI confidence desc, then discovery time; manual escalations always bubble to top.
2. CLI exposes `apply queue --mode ai-first|fifo` to control ordering; default `ai-first` when AI suggestions enabled.
3. Escalated items include reason + timestamp; UI displays filter for “Needs manual review.”
4. Telemetry captures per-run stats (AI approvals accepted vs overridden) for later analytics.
5. Tests assert ordering logic using mixed-confidence fixture responses.

## Story 6.5 — Guardrails & Rate Limits
As a compliance stakeholder,
I want guardrails around AI usage,
so that the system remains safe and transparent.

Acceptance Criteria
1. Profiles must set `automation.allow_auto_review=true` before LLM suggestions run.
2. Rate limit AI calls to configurable `max_decisions_per_minute`; excess candidates fall back to manual review with a toast explaining why.
3. Provide CLI flag `--no-ai` to disable suggestions even if profile allows them.
4. Logs store hashed rationale and model metadata (`model`, `latency_ms`, `tokens_used`) for auditing.
5. Unit tests cover opt-in enforcement and rate-limit fallback.

### Rationale (Epic 6)
This epic completes the AI-assisted MVP. Reviewers get tangible value—ranked queues, rationale summaries, single-click approvals—while retaining final control. The structured data it produces also powers confidence analytics and paves the way for the auto-submit work in Epic 7.
