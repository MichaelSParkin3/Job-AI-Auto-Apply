# Epic 7 — Full Auto Submit & Safety Rails

## Expanded Goal
Enable trusted profiles to run in unattended, fully automated mode. Building on Epic 5’s autonomous fill and Epic 6’s decision engine, the system should submit immediately when confidence thresholds are met, monitor for success/failure, and fall back to human review if anything looks risky. Guardrails (kill switches, confidence floors, notification hooks) must be in place before auto submission is allowed.

## Story 7.1 — Auto Submit Execution Path
As an operator,
I want the CLI to submit automatically when AI confidence is high,
so that I can run unattended batches for well-understood profiles.

Acceptance Criteria
1. `auto_submit` mode triggers submission immediately after a decision with `outcome=approve` and `confidence ≥ profile.threshold`.
2. Submission path records `autoSubmitted=true` in `run.json` and `history.jsonl` with timestamps.
3. Failures (submission error, unexpected page) automatically convert candidate to manual queue with rationale.
4. Dry-run mode logs what would have happened without clicking submit.
5. Integration tests simulate success and failure flows, ensuring fallbacks fire.

## Story 7.2 — Confidence Policies & Kill Switches
As a compliance stakeholder,
I want explicit policies governing when auto submit is allowed,
so that the system errs on the side of safety.

Acceptance Criteria
1. Profiles declare `automation.auto_submit` block (`enabled`, `confidence_threshold`, `max_consecutive_failures`).
2. CLI refuses to start auto submit unless profile + CLI flag confirm the choice; prints summary of guardrails.
3. If more than `max_consecutive_failures` occur, auto submit halts and flips remaining candidates to manual review while emitting alert toast/CLI warning.
4. Provide `apply disable-auto-submit` command that rewrites profile config to disable auto.
5. Unit tests cover threshold enforcement and failure counter logic.

## Story 7.3 — Notifications & Run Summaries
As a user,
I want to know what happened during unattended runs,
so that I can review and intervene quickly.

Acceptance Criteria
1. CLI prints end-of-run summary with counts (auto submitted, escalated, failures) and average confidence.
2. Optional local notification (Windows toast / macOS notification center) triggers on completion with run hyperlink.
3. History entries include `autoReviewSummary` (counts + avg confidence) and pointer to queue snapshot.
4. Preview UI shows real-time progress bar + ETA when in auto submit mode.
5. Tests verify summary formatting and notification toggles.

## Story 7.4 — Mid-Run Intervention Tools
As a reviewer,
I want to pause or reclaim auto mode candidates mid-run,
so that I can intervene if something looks off.

Acceptance Criteria
1. CLI exposes `apply pause --run <id>` and `apply resume --run <id>` commands; pause stops new submissions but keeps queue state.
2. Preview UI adds “Pause Auto Mode” button; when paused, AI decisions continue but mark candidates `awaiting_manual_resume`.
3. Manual overrides while paused automatically move candidate to human lane with `overrideReason=pause`.
4. Resume replays pending approvals in queue order, respecting fresh confidence checks.
5. Integration tests simulate pause/resume sequences with queued candidates.

## Story 7.5 — Observability & Audit Enhancements
As an auditor,
I want deep visibility into auto submit behaviour,
so that I can trust the system over time.

Acceptance Criteria
1. Telemetry emits `AUTO_SUBMIT_ATTEMPT`, `AUTO_SUBMIT_SUCCESS`, `AUTO_SUBMIT_FAILURE` with relevant metadata (confidence, duration, error code).
2. `runs/<id>/actions.log` includes annotated timeline combining AI decision, submit click, confirmation detection.
3. CLI `history --auto` filters for runs containing auto submit events.
4. Provide `scripts/report_auto_confidence.py` to aggregate confidence distributions over time.
5. Regression tests ensure telemetry payloads respect redaction rules.

### Rationale (Epic 7)
Full auto unlocks the third stage of the autonomy roadmap. By codifying strict policies, pause/resume tooling, and rich telemetry, we can expand beyond AI-assisted runs without sacrificing safety or auditability.
