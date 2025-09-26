# Epic List

- Epic 1: Foundation & Review UI — Scaffold CLI, config, and preview server using shadcn/ui; deliver a working review window showing a placeholder screenshot with Approve/Edit/Abort and Dry-Run skeleton.
- Epic 2: Stealth Browser Wrapper & Profiles — Implement Browser-Use headful Chrome with stealth, per-profile sessions (`user_data_dir`), and domain guardrails; reliably open a SimplyHired search URL.
- Epic 3: SimplyHired Quick Apply Automation — Detect and drive the “Quick Apply” flow, fill fields from the active profile, upload resume, and compile a submission summary.
- Epic 4: Review Gate & Submission Integration — Feed the final review screenshot into the UI, support one-shot Edit/Retry, and submit on approval with clear confirmation/error handling.
- Epic 5: Artifacts, History & Dedupe Hardening — Persist screenshots/run.json/HTML snapshot, append history JSONL, enforce 30‑day dedupe, retention policies, storage warnings, and add Playwright fallbacks, auto-retry, and session backup/restore.

### Rationale (Epics)
- Sequenced to deliver deployable value early: users get a working review UI in Epic 1, then stealth navigation, then real apply flow, then integrated submission, and finally durability/observability. Cross-cutting concerns (logging, redaction) appear within relevant epics, not as standalone epics.

---
