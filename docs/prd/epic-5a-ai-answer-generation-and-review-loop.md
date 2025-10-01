# Epic 5A — AI Answer Generation & Review Loop

## Goal
Deliver governed AI-drafted answers for Lever applications so the automation can complete forms end-to-end while keeping reviewers in control. The epic introduces an answer orchestration layer, reviewer approval workflow, and profile persistence so downstream auto-submit, decision engine, and scheduling initiatives have reliable answer coverage.

## Why Now
- Planner (Story 5.1) and executor (Stories 5.2/5.2.1) already map fields and drive Browser-Use, but missing profile answers still force manual intervention.
- Stakeholders have prioritized AI-authored answers ahead of further autonomy features (decision engine, auto-submit) to reduce review queue churn and increase perceived intelligence.
- Confidence and rationale metadata are prerequisites for the decision engine policies defined in Epic 6; completing this epic unblocks that roadmap.

## Success Metrics
- ≥90% of required Lever fields receive an answer without manual typing during review mode.
- ≥80% of drafted answers above the configurable confidence threshold are approved by reviewers.
- Time-to-approve per candidate decreases by 30% vs. baseline (Story 5.2.1), measured via queue telemetry.
- No PII leakage confirmed in prompts/responses during QA privacy audit.

## Key Deliverables
1. **Answer Orchestrator** providing deterministic precedence and LLM fallback with telemetry and audit artifacts.
2. **Reviewer Experience** that exposes drafted answers, confidence/rationale metadata, and actions to apply/save/edit/reject answers.
3. **Profile Evolution & Analytics** capturing reviewer-approved answers, updating per-field provenance, and reporting draft accuracy trends.

## Story Breakdown
- **Story 5.3 — AI Answer Orchestrator & Drafting Pipeline**
  - Build orchestration layer, prompt/response schema, telemetry, and configuration controls.
- **Story 5.4 — Reviewer UX & Answer Approval Loop**
  - Extend Preview UI + backend to surface drafted answers and collect reviewer decisions that feed automation.
- **Story 5.5 — Profile Answer Evolution & Analytics**
  - Persist approved answers back to profiles, expand monitoring/reporting, and document opt-out/privacy guardrails.

## Dependencies
- Requires planner/executor/resume ordering from Stories 5.1–5.2.1.
- Must complete before Epic 6 (AI Decision Engine), Epic 7 (Auto-Submit Safety Rails), and Epic 9 (Scheduler) begin implementation.
- Leverages resume parsing outputs and profile schema from Epic 3 foundations.

## Risks & Mitigations
| Risk | Mitigation |
| --- | --- |
| LLM hallucination or policy violations | Enforce confidence thresholds, rationale logging, deterministic fallbacks, and reviewer approval gates. |
| Reviewer overload from excessive drafts | Provide concise rationale snippets, keyboard shortcuts, and batch approve tooling in Story 5.4. |
| Profile contamination with poor answers | Track provenance metadata, require explicit reviewer opt-in to save, and maintain audit trail for reversions. |
| Privacy exposure in prompts/responses | Apply redaction helpers, store hashed value lengths only, and document prompt sanitization in QA checklists. |

## Acceptance Gates
- Architecture addendum describing answer data flow and governance reviewed and signed off by Architect + Product Owner.
- QA test plan updated with drafted answer fixtures, reviewer workflow scripts, and privacy validation steps.
- Telemetry dashboards validated in staging demonstrating drafted/approved/rejected counters.

## Out of Scope
- Automatic resume parsing improvements (handled in Epic 3 enhancements).
- Decision automation policies (Epic 6) and fully unattended submissions (Epic 7); these rely on 5A outputs but are separate efforts.
