# AI Review & Full Auto Mode Planning Notes

## 1. Research Highlights
- Browser-use core capabilities already demonstrate autonomous job-application agents that can read a CV, locate roles, and begin applying in new tabs, confirming the feasibility of moving beyond human-in-the-loop review when paired with our guardrails.【06f2b7†L9-L38】
- Our existing architecture is a local-first Python monolith with a FastAPI preview server, React review UI, Browser-Use (0.7.9) automation, file-backed run store, and redacted telemetry. Any new automation mode must coexist with this stack and reuse its guardrails (single tab, domain restrictions, crash-safe logging).【F:docs/architecture/backend-architecture.md†L1-L38】【F:docs/architecture/unified-project-structure.md†L1-L24】
- PRD goals emphasize review-first trust, append-only history, redaction, and automation guardrails; any autonomous mode must either respect those defaults or surface opt-in toggles with safe defaults. Human review remains the default for transparency.【F:docs/prd/requirements.md†L1-L120】【F:docs/prd/user-interface-design-goals.md†L1-L80】

## 2. Current Workflow Snapshot
1. CLI orchestrates a run (`apply` command) using profile, config precedence, Browser-Use discovery, and Quick Apply form mapping (Story 3.2). Outputs persist in `runs/<id>` with `run.json`, `actions.log`, and history JSONL entries.【F:docs/architecture/development-workflow.md†L1-L80】【F:docs/stories/3.2.form-structure-mapping-selector-library.md†L1-L160】
2. Preview server serves React review UI on port 4950. User manually approves/edits/aborts each application; automation only submits once explicitly approved.【F:docs/prd/epic-1-foundation-review-ui.md†L1-L120】【F:docs/prd/user-interface-design-goals.md†L12-L80】
3. Guardrails: single tab, SimplyHired-only, Browser-Use 0.7.9 DOM mapping with telemetry events, crash-safe logging, dedupe fingerprint (URL + JD hash), opt-in dry-run mode.【F:docs/prd/requirements.md†L80-L140】【F:docs/architecture/components.md†L1-L120】

## 3. Desired Future Modes
- **Human Review Mode (default):** Maintain current flow but extend UI to manage queues of pending applications. Allow multiple pending submissions awaiting user action (tabs or sequential queue) with ability to approve/deny/edit each. Auto-snooze or expiration for stale reviews to keep scheduling queue healthy.
- **AI Review / Full Auto Mode:** Automation performs review/approval decisions without human input. Should support two variants:
  - **Auto-approve-with-audit:** AI produces structured justification, stores summary in history, optionally emails/alerts user for post-run review.
  - **Auto-submit-immediate:** For trusted pipelines (e.g., daily scheduled run) automation directly submits after LLM verification thresholds, falling back to human review when confidence drops.

## 4. High-Level Architecture Adjustments
- Introduce a **Run Mode** concept (`review`, `auto_review`, `auto_submit`) in CLI config/profile overrides. Propagate to run metadata, history entries, telemetry, and UI state.
- Extend orchestration pipeline with a **Decision Engine** interface that produces `SubmissionDecision` objects (`approve`, `edit_request`, `abort`, `needs_review`). Implementations:
  - `HumanDecisionEngine`: proxies to UI events (current behavior).
  - `LLMDecisionEngine`: uses profile instructions, job summary, and diff heuristics to auto-decide. Configurable thresholds; returns `needs_review` when uncertain.
- For `LLMDecisionEngine`, reuse Browser-Use artifacts (screenshot, structured form plan, scraped job description) to craft prompts. Add caching to avoid re-prompting when re-running.
- Update FastAPI server to expose endpoints for asynchronous decision ingestion (queue state, AI decisions) so UI can show status even in auto mode.
- Add **Run Scheduler** abstraction (future Docker compatibility). For now, plan CLI subcommand `scheduler plan <profile> <searchUrl> --time 14:00 --mode auto_submit` generating OS-specific instructions (Windows Task Scheduler `.xml`, Linux cron snippet). Later, integrate with containerized scheduler service.

## 5. Pipeline & Workflow Changes
- **Job Discovery Loop**
  - Continue to respect dedupe + limit. For auto modes, optionally allow concurrency >1 but keep sequential to avoid anti-bot issues.
  - Introduce `review_backlog` queue storing `ApplicationCandidate` objects with state machine (`discovered → filled → awaiting_decision → decided`).
- **Decision Handling**
  - In human mode, queue displayed in UI with navigation controls (next/previous) rather than multiple Chrome tabs to minimize resource use. Provide quick filters (needs edit, errors).
  - In AI modes, `LLMDecisionEngine` consumes backlog. For uncertain results (confidence < threshold, ambiguous answers), emit `needs_review` pushing candidate back into human queue.
  - Each decision writes to `run.json` (`decisions[]`) with reasoning payload; history entry references aggregated stats (count approved, AI confidence distribution).
- **Submission Execution**
  - For `auto_submit`, orchestrator submits immediately after `approve` decision. If submission fails or ATS flow diverges, fallback to human queue or abort.
  - For `auto_review`, orchestrator stops at ready-to-submit stage, logging instructions for human follow-up. Provide CLI command `apply resume --run <id> --candidate <n>` to resume at submission once user inspects history.

## 6. Data Model & Contract Updates
- Update `run.json` schema: add `mode`, `decisions[]`, `autoReviewSummary`, `confidenceScores`, `pendingQueue` snapshots. Mirror fields in `history.jsonl` (aggregated view) while preserving PII redaction rules.
- Extend `FormFillPlan` to include `reviewHints` (confidence, unresolved questions) so both human and AI reviewers share context.
- Document JSON Schema updates and add contract tests for new fields.

## 7. UI/UX Considerations
- Human review queue view: list/detail layout with keyboard navigation; badges for AI suggestions. Provide ability to edit AI-generated responses before submission.
- Auto mode dashboard: show run progress, AI decisions, ability to intervene mid-run (flip candidate back to manual review, abort run).
- Notifications: optional local notifications (toast/system) when AI completes runs, with links to history entries.
- Ensure UI states degrade gracefully when scheduler triggers headless runs (maybe no UI). Provide CLI summary output for auto runs.

## 8. Observability & Safety
- Extend telemetry event taxonomy with `AUTO_DECISION`, `AUTO_OVERRIDE`, `AUTO_FAILSAFE_TRIGGERED`.
- Add kill-switch config to force human review if repeated failures (e.g., 3 consecutive low-confidence results).
- Update logging to record AI prompts/responses with redaction & encryption (store hashed references, not raw job text where possible).
- Add test coverage: simulate AI decision engine with deterministic fixture responses; ensure scheduler/triggers respect quiet hours.

## 9. Documentation Update Plan
- **Architecture:** Update `core-workflows.md`, `components.md`, `backend-architecture.md`, `frontend-architecture.md`, and `data-models.md` to document new decision engine, scheduler, and run mode concept.
- **PRD:** Amend `requirements.md` with optional AI mode scope, update `user-interface-design-goals.md` for queue/dashboard UX, adjust epic roadmaps (likely new epic or extended Epic 4/5) to capture scheduling & AI decisioning stories.
- **Story Backlog:** Draft new stories (e.g., `4.x AI decision engine`, `4.y human queue`, `5.x scheduler integration`). Update change logs.

## 10. Recommended Implementation Phasing
1. **Phase A — Groundwork:** Introduce run mode flag, queue data model, and UI support for multiple pending reviews while keeping human-only decisions.
2. **Phase B — AI Assist:** Implement `LLMDecisionEngine` in advisory mode (suggested decisions surfaced to human reviewer). Validate prompt quality, scoring heuristics, and logging.
3. **Phase C — Auto Review:** Allow automation to auto-approve with stored justification but stop short of submit; deliver CLI/UX for human follow-up.
4. **Phase D — Full Auto Submit:** Enable auto submission with failsafes; require explicit opt-in per profile/config and integrate scheduler for unattended runs.
5. **Phase E — Scheduler/Container:** Build scheduler service/CLI integration, add Docker compatibility, document Task Scheduler/cron usage, and implement daily run automation.

## 10.1 Epic Mapping
- **Epic 4** ↔ Phase A (human queue + decision engine contract)
- **Epic 5** ↔ Phase B (AI advisory mode)
- **Epic 6** ↔ Phases C & D (auto submit and safety rails)
- **Epic 8** ↔ Phase E (scheduler + unattended runs)

## 11. Open Questions & Risks
- Acceptance criteria for “safe to auto submit” will be based on a configurable confidence level.
- Full AI mode will rely on a single model; dual-model consensus is not required.
- For CAPTCHA or multi-factor prompts in auto mode, research will be done on how other browser-automation tools handle this and a fallback strategy (e.g., pause and notify) will be implemented.
- AI prompt/response data will be stored locally.
- The scheduler and Docker implementation will be deferred to a later phase.

## 12. Recommendations for Product & Stakeholders
- Maintain human review as default; gate AI modes behind explicit profile-level setting with guardrails and documentation of risks.
- Invest in observability and sandbox testing before enabling unattended submissions; consider canary run mode for limited job categories.
- Legal/compliance review regarding fully automated applications and JD snapshot storage is not required.
- Prioritize user education: update onboarding, tooltips, and docs to explain difference between human review, AI assist, and full auto modes.
- Plan for configurable scheduling windows and concurrency caps to prevent spammy behavior.

## 13. Stealth and Anti-Bot Detection Strategy
- **Problem:** The `browser-use` library, while powerful for natural language control, does not have built-in features to prevent bot detection. Standard Playwright is easily identified by anti-bot systems.
- **Research:** A review of available tools confirmed that a stealth plugin is necessary. The primary candidates were `playwright-stealth`, `undetected-chromedriver`, and newer frameworks like `Botright`.
- **Recommendation:** `playwright-stealth` is the best tool for this project.
    - It is actively maintained (the `AtuboDad/playwright_stealth` fork).
    - It integrates directly with the existing Playwright engine used by `browser-use`.
    - Alternatives would require a major migration (e.g., to Selenium for `undetected-chromedriver`) or a significant rewrite of the automation logic.
- **Implementation:** The `playwright-stealth` library should be integrated to make the automated browser less detectable. This will be a key dependency for the "Full Auto Mode" to function reliably.

## 14. Next Steps for Documentation & Code Changes (Future Work)
- Draft PRD updates outlining acceptance criteria for AI decision engine, queue UI, and scheduler features.
- Update architecture diagrams (system context, workflow sequence) to include decision engine and scheduler components.
- Prototype decision engine interface in code (without enabling AI auto submit) to validate data flow.
- Design UX wireframes for queue dashboard and auto-mode status pages prior to implementation.

