# Epic List

- Epic 1: Foundation & Review UI — Scaffold the CLI, config loader, and preview server using shadcn/ui; deliver a working review window showing a placeholder screenshot with Approve/Edit/Abort and Dry-Run skeleton.
- Epic 2: Stealth Browser Wrapper & Profiles — Implement Browser-Use headful Chrome with stealth posture, per-profile sessions (`user_data_dir`), and domain guardrails; reliably open a SimplyHired search URL.
- Epic 3: SimplyHired Quick Apply Automation — Detect and drive the “Quick Apply” modal, build the selector/mapping library, deterministically fill forms, upload resumes, and capture a pre-submit summary.
- Epic 4: Human Review Queue & Decision Engine Foundation — Pivot to Lever sourcing, persist the review queue, unify decision contracts, and give humans full override controls before any auto action occurs.
- Epic 5A: AI Answer Generation & Review Loop — Introduce the answer orchestrator, reviewer workflows, and profile persistence that prioritize AI-drafted answers with confidence, rationale, and governance before further autonomy.
- Epic 5: Full AI Form Filling & Assisted Submit — Use LLM-guided Browser-Use to fill and submit Lever applications headfully, leveraging the new drafted answers pipeline, capture blockers (CAPTCHA/MFA) with deterministic handoff packages, and prove the MVP vision with history artifacts.
- Epic 6: AI Decision Engine & Advisory Mode — Layer structured LLM recommendations, confidence scoring, and rationale previews onto the queue while keeping humans in control of final approvals and consuming telemetry from Epic 5A.
- Epic 7: Full Auto Submit & Safety Rails — Allow unattended submission when confidence is high, with kill switches, pause/resume tooling, and observability to keep automation safe.
- Epic 8: Artifacts, History & Dedupe Hardening — Harden storage with comprehensive artifacts, atomic history appends, dedupe enforcement, and reliability fallbacks.
- Epic 9: Scheduler & Unattended Runs — Package auto-submit flows into repeatable schedules, surface dashboards, respect quiet hours, and ensure unattended runs fail safely.

### Rationale (Epics)
The sequence proves trust step-by-step: first build the human-reviewed foundation (Epics 1–4), then prioritize AI-drafted answers and reviewer governance (Epic 5A) so every candidate has high-quality responses before demonstrating autonomous form filling and assisted submission (Epic 5). Only after the answer loop is stable do we introduce advisory AI decisions (Epic 6), full auto submission (Epic 7), durability hardening (Epic 8), and finally unattended scheduling (Epic 9).
