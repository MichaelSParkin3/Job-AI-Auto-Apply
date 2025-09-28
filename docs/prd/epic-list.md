# Epic List

- Epic 1: Foundation & Review UI — Scaffold CLI, config, and preview server using shadcn/ui; deliver a working review window showing a placeholder screenshot with Approve/Edit/Abort and Dry-Run skeleton.
- Epic 2: Stealth Browser Wrapper & Profiles — Implement Browser-Use headful Chrome with stealth, per-profile sessions (`user_data_dir`), and domain guardrails; reliably open a SimplyHired search URL.
- Epic 3: SimplyHired Quick Apply Automation — Detect and drive the “Quick Apply” flow, fill fields from the active profile, upload resume, and compile a submission summary.
- Epic 4: Human Review Queue & Decision Engine Foundation — Introduce run modes, review queue persistence, and UI/CLI plumbing so humans can batch-approve candidates while seeing AI hints.
- Epic 5: AI Decision Engine & Advisory Mode — Build the LLM-powered decision engine, log confidence/rationales, and surface AI suggestions while still requiring human approval.
- Epic 6: Full Auto Submit & Safety Rails — Allow trusted profiles to auto-submit at high confidence, add watchdogs, and enable mid-run human intervention.
- Epic 7: Artifacts, History & Dedupe Hardening — Persist screenshots/run.json/HTML snapshot, append history JSONL, enforce 30‑day dedupe, retention policies, storage warnings, and add Playwright fallbacks, auto-retry, and session backup/restore.
- Epic 8: Scheduler & Unattended Runs — Package full auto-submit with failsafes, generate Task Scheduler/cron plans, and surface auto-run dashboards + intervention controls.

### Rationale (Epics)
- Sequenced to deliver deployable value early: users get a working review UI in Epic 1, then stealth navigation, then real apply flow. Epic 4 focuses on the human review queue foundation, Epic 5 layers AI assistance without losing human control, Epic 6 unlocks full auto (with guardrails), Epic 7 continues durability/observability, and Epic 8 delivers unattended scheduling last. Cross-cutting concerns (logging, redaction) appear within relevant epics, not as standalone epics.

---
