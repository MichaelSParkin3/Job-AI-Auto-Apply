# Epic 5A — AI Answer Generation & Review Loop

## Expanded Goal
Position AI-drafted answers as the centerpiece of the roadmap by delivering a reliable answer orchestration pipeline, reviewer experience, and profile persistence loop before pursuing additional autonomy. The epic ensures every Lever application candidate benefits from confidence-scored, rationale-backed answer suggestions that reviewers can approve, edit, or promote into long-term profile knowledge without breaking existing guardrails.

## Story 5A.1 — Answer Orchestrator & Fallback Pipeline
As a developer,
I want a unified orchestrator that resolves each field using saved answers before invoking the LLM,
so that autofill plans deliver complete answer candidates while respecting deterministic overrides.

Acceptance Criteria
1. Extend `ProfileAnswerResolver` into an `AnswerOrchestrator` that evaluates precedence: profile saved answer → deterministic override → resume/resume-analysis extraction → LLM draft.
2. LLM prompts include profile identity, resume highlights, prior approved answers (redacted), and field metadata; responses follow a typed schema with `{ value, confidence, rationale, tokens, sourceHints[] }`.
3. Orchestrator emits telemetry events (`AI_FIELD_REQUESTED`, `AI_FIELD_DRAFTED`, `AI_FIELD_SKIPPED`) with token counts and guardrail reasons when drafts are rejected.
4. Draft artifacts persist under `runs/<id>/answers/<candidate>/<field>.json` with hashed values; raw prompts/responses stored in `runs/<id>/autofill/prompts/` and redacted copy in `history` entry.
5. Dry-run fixtures cover deterministic, resume-derived, and LLM-derived branches without invoking external APIs.

## Story 5A.2 — Draft Answer Registry & API Contract
As a backend developer,
I want the preview server to expose drafted answers with confidence and rationale metadata,
so that the UI can present per-field review controls without embedding orchestration logic.

Acceptance Criteria
1. `/api/queue/{runId}` responses include `draftAnswers[]` for each candidate with `{ fieldKey, question, draftedValuePreview, confidence, rationalePreview, source, lastUpdatedAt }`.
2. New endpoint `POST /api/queue/{runId}/candidate/{candidateId}/answers/{fieldKey}/decision` accepts `{ action: approve|approve_save|edit|edit_save, value?, reviewerNotes? }` and returns the updated answer payload plus queue snapshot timestamp.
3. API validates confidence thresholds from profile/global config before allowing `approve` actions in auto modes; low confidence returns `400` with actionable error codes.
4. Decision responses append to `runs/<id>/answers/decisions.jsonl` for audit, linking to the draft artifact hash.
5. Contract tests cover payload schema, invalid actions, and optimistic concurrency (stale `lastUpdatedAt` yields `409`).

## Story 5A.3 — Reviewer UX for Drafted Answers
As a reviewer,
I want to inspect, approve, edit, and save drafted answers inline within the preview queue,
so that I can keep momentum while curating reusable knowledge.

Acceptance Criteria
1. Preview UI renders a Draft Answers panel per candidate with collapsed summaries and expandable detail showing drafted value, rationale, and confidence bar.
2. Keyboard shortcuts map to reviewer actions: `Ctrl+Enter` approve, `Ctrl+Shift+Enter` approve & save, `Ctrl+E` edit, `Ctrl+Shift+S` edit & save.
3. Approve/apply updates the pending form fill preview immediately; approve & save also surfaces a toast confirming profile persistence.
4. Edit flows support multiline inputs with diff highlighting versus the draft; edited values feed back to orchestrator cache for subsequent candidates in the run.
5. Accessibility: actions exposed via buttons with aria labels; confidence bar meets contrast guidelines; focus order respects keyboard navigation.

## Story 5A.4 — Profile Persistence & Governance
As a product owner,
I want approved answers to update profile metadata with provenance,
so that future runs reuse validated content while maintaining audit history.

Acceptance Criteria
1. Profile schema gains `answers[]` entries with `{ fieldKey, value, source, confidence, lastReviewedAt, reviewerId?, history[] }` persisted to `data/profiles/<id>.yaml`.
2. Saving to profile requires explicit reviewer confirmation; CLI surfaces summary of newly stored answers at run completion.
3. History entries log promotion events with `AI_ANSWER_PROMOTED` telemetry, capturing reviewer identity (if available) and prior confidence.
4. Profiles retain previous values by appending to `history[]` with timestamp, old value hash, reviewer, and reason.
5. Unit tests serialize/deserialize new profile schema and ensure backwards compatibility for profiles lacking `answers`.

## Story 5A.5 — Confidence Policies, Telemetry & Documentation
As an operator,
I want configurable confidence thresholds and analytics around drafted answers,
so that we can tune automation risk and track quality over time.

Acceptance Criteria
1. Global/profile config introduces `answers.min_confidence.review` and `answers.min_confidence.auto_submit`; orchestrator enforces them before surfacing drafts in auto modes.
2. Telemetry aggregates per-run stats (`answersDrafted`, `answersApproved`, `answersSavedToProfile`, confidence histograms) recorded in `run.json` and appended to history entries.
3. CLI `history show --answers` summarizes draft outcomes across runs (approval rate, average confidence, most-edited fields).
4. Documentation updates (`docs/prd/requirements.md`, user guide) explain AI answer workflows, opt-out flags, and privacy considerations.
5. Analytics fixtures generate deterministic sample telemetry to validate histogram calculations without external calls.

### Rationale (Epic 5A)
AI-drafted answers unlock end-to-end coverage by filling the largest remaining gap: high-quality responses when profiles lack data. Completing this epic before deeper autonomy ensures every downstream workflow—decision engine, auto-submit, scheduling—operates on richer, confidence-scored data with human-in-the-loop safeguards. The stories intentionally span orchestration, API, UX, persistence, and telemetry so that reviewers trust the drafts, the system learns from approvals, and policies remain tunable.
