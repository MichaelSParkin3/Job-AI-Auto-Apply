# Project Brief: Job AI Auto Apply

## Executive Summary
A local, single‑user Windows app that automates SimplyHired “Quick Apply” submissions using Browser‑Use (Playwright‑based, LLM‑driven browser automation) with a stealth‑first setup and OpenRouter (DeepSeek free tier) for reasoning—while keeping all data and artifacts strictly on the user’s machine.

- Stealth posture (priority): Headful Chrome with Browser‑Use stealth enabled, persistent `user_data_dir` per profile to reuse real cookies/sessions, OS‑matched locale/timezone, stable viewport, one tab at a time, and human‑like pacing (top‑down fill order, small jittered waits). Domain guardrails to `*.simplyhired.com`.
- Profiles: Separate per‑role profiles (e.g., Frontend Dev, Video Editor, Music Producer) each with its own PDF resume, portfolio links, and Q&A bank; quick switching between profiles.
- Review‑by‑default: Minimal preview window (port 4950) that at minimum shows the final review page screenshot; Approve/Edit/Abort and auto‑close after submit. Dry‑run mode for safe testing (never submit). Optional full‑auto later.
- Local‑first storage: YAML profiles, global config, per‑run artifacts (screenshots/video), and an append‑only application history with full JD text and HTML snapshot, all stored locally.

Success (MVP): Given a SimplyHired search URL with a left job list and right detail pane, iterate up to N items, open Quick Apply, fill from the selected profile, present preview, submit on approval, and store a complete local audit trail with PII‑redacted step logs.

---

## Problem Statement
- Manual repetition: Applicants re‑enter identity, eligibility, and upload resumes across many postings.
- Multi‑profile, multi‑resume reality: Many people pursue 2–3 unrelated role families (e.g., Frontend Developer and Music Producer), requiring different resumes, portfolios, and answers. Switching narratives manually is slow and error‑prone; a “profile” is needed to encapsulate each role’s story.
- Site variability/A‑B tests: SimplyHired “Quick Apply” UI can shift (labels, widgets, steps), breaking brittle scripts.
- Anti‑bot friction: Headless/ultra‑fast automation triggers detection and failed submits; human‑like, stealthy behavior with persistent sessions is required.
- Time pressure and fatigue: Higher daily throughput without accuracy loss is crucial.
- Privacy/trust: Users want PII to stay local; cloud tools are a non‑starter for many.

Why others fall short: Single‑profile tools and generic form‑fillers can’t manage multiple narratives or uploads reliably; many solutions store PII in the cloud or ignore stealth best practices.

---

## Proposed Solution
- Local‑first app
  - Typer CLI with subcommands: `apply`, `profiles`, `config`, `history`.
  - Minimal preview server (FastAPI) on port 4950; Chrome app‑mode window; auto‑closes after submission.
  - All data/artifacts stored locally: `config/`, `data/profiles/`, `data/resumes/{profile}/`, `.local/browser/profiles/{profile}/`, `runs/`, `history/`.

- Stealth‑first automation (Browser‑Use + Playwright fallback)
  - Headful Chrome with stealth enabled, persistent per‑profile `user_data_dir`, and `keep_alive` browser session.
  - Domain guardrails to `*.simplyhired.com`; one tab/flow at a time; human‑like pacing and top‑down fill order.
  - Heuristic selectors for A/B variants; quick “manual tweak + resume” flow when layout differs; deterministic Playwright fallback for uploads/quirky widgets.

- Profiles and configuration
  - Global config: `config/config.yaml` (defaults for model, artifacts, review, preview_port=4950, redaction policy, Chrome channel, run/user_data roots, dedupe and retention policies, reserved proxy flag).
  - Per‑profile YAML: `data/profiles/{profile}.yaml` encapsulating identity, Q&A, constraints, LLM/browser overrides, and `documents.resume_path` under `data/resumes/{profile}/resume.pdf` (PDF only for MVP). Precedence: CLI flags → profile → global.

- Apply flow (SimplyHired Quick Apply)
  - Input: a search page URL (left job list, right detail panel).
  - Iterate up to `--limit` items; for each: open detail, detect Quick Apply, open application, fill from profile, upload PDF, compile a submission summary.
  - Review gate (default): preview window shows at minimum the final review page screenshot; controls: Approve/Edit/Abort. Edit provides a small text box for corrections (e.g., “set salary to 125k”); agent retries once then returns to preview. Dry‑run never submits.

- LLM integration (OpenRouter)
  - Default model: `deepseek/deepseek-chat-v3.1:free`; override in profile/CLI. Keys in `.env.local`.

- Artifacts and logging
  - Screenshots by default; optional video via `--artifacts video|both`.
  - `actions.log` with PII redacted; per‑run `run.json` holds full submitted details for local audit.

- Application History
  - Storage: append‑only JSONL at `history/history.jsonl` + per‑run `runs/.../run.json`.
  - Fields: `run_id`, timestamps, `profile_id`, `job_title`, `company`, `location`, `source="simplyhired"`, `search_url`, `posting_url`, `apply_url`, `quick_apply`, `resume_path`, `review_mode`, `artifacts`, `status` (submitted|failed|aborted|skipped|duplicate|error), `confirmation`/`error`, `run_path`, `screenshots`, `answers_summary` (non‑PII), `stage_history`, offer fields, `job_description_full`, and `job_description_html_path`.
  - De‑dupe: fingerprint = `posting_url + sha256(job_description_full)`; re‑apply allowed after 30 days.

---

## Target Users
- Primary: Local, privacy‑conscious job seekers with multiple personas (Windows + Chrome), applying via SimplyHired “Quick Apply,” maintaining 2–3 role profiles with distinct resumes/answers; prefer review now and full‑auto later.
- Secondary: Portfolio‑career/career‑switcher power users needing auditability (history, JD snapshots) and easy re‑runs without duplicates.

---

## Goals & Success Metrics
- Business Objectives: median ≤ 120s per Review‑mode submit by week 2; ≥ 95% submit success in Review mode; 0 duplicate re‑applies within 30 days; ≤ 5% anti‑bot/CAPTCHA; 100% local PII.
- User Metrics: ≤ 1 manual correction/app in Review mode; preview decision ≤ 10s; profile switch ≤ 2s; artifacts present for 100% of runs.
- KPIs: success rate (review/auto) per profile; CAPTCHA/blocks; upload failures; JD capture 100%; history append latency ≤ 1s; error taxonomy; median action pacing.

---

## MVP Scope
- Must have: Typer CLI; YAML profiles; global config; Browser‑Use wrapper (headful Chrome, stealth, keep_alive, per‑profile `user_data_dir`, allowed_domains); SimplyHired Quick Apply playbook; review preview window (port 4950) with Approve/Edit/Abort; dry‑run mode; screenshots + per‑run `run.json`; `actions.log` with PII redacted; JSONL history with full JD text and HTML snapshot; default `--limit 2`; manual login persisted.
- Out of scope (MVP): multiple resumes per profile with auto‑select; other ATS; scheduler and shadcn Web UI; Docker; SQLite store; proxies/fingerprint spoofers.
- MVP success: Iterate up to 2 jobs, fill Quick Apply, preview, submit on approval, store artifacts and history without duplicates within 30 days.

---

## Post‑MVP Vision
- Phase 2: Multi‑resume per profile; Auto mode default with confidence gating; search page automation/pagination; in‑app scheduler; SQLite history + UI; shadcn Web UI; additional ATS (Indeed core, Greenhouse, Lever, Workday) with shared selector library.
- Long‑term: Profile intelligence (keyword scoring); cover‑letter generation with review; robust dedupe across sources; reliability suite (selector tests against snapshots); optional local LLM.

---

## Technical Considerations
- Platform: Windows 10/11; Chrome stable; Python 3.11+; Playwright (Chromium installed).
- Stack: Typer (CLI), FastAPI (preview server), file‑first storage moving to SQLite later, OpenRouter LLM.
- Repo layout: `app.py`, `browseruse_wrapper.py`, `sites/simplyhired.py`, `preview_server.py`, `config_loader.py`, `run_store.py` + folders (`config/`, `data/`, `.local/`, `runs/`, `history/`).
- Security: PII redaction in `actions.log`; full details only in `run.json`; `.env.local` for secrets; no CAPTCHA bypass; respect ToS.
- Performance: ≤ 120s median per Review‑mode submit; one tab/flow; human‑like pacing.
- Stealth: Headful + persistent sessions; OS locale/timezone; stable UA/viewport; minimal automation fingerprints.

---

## Constraints & Assumptions
- Constraints: Local‑only runtime/storage; Windows + Chrome; port 4950 reserved; one PDF resume per profile (MVP); no CAPTCHA bypass/proxies; redacted step logs; OpenRouter free model by default.
- Assumptions: User provides SimplyHired search URL and logs in once; Quick Apply supports PDF uploads and common fields; OpenRouter model available; JD capture permissible; future features (multi‑resume, scheduler, shadcn, Docker) won’t break current file contracts.

---

## Risks & Open Questions
- Key Risks (and mitigations):
  - Layout drift/A‑B tests (heuristic selectors, Playwright fallback, manual tweak + resume)
  - Anti‑bot friction (headful, pacing, one‑tab flows, review pause on CAPTCHA)
  - Session corruption (auto‑backup last good session per profile; recreate on failure)
  - Upload quirks (deterministic upload, PDF only, retry/backoff)
  - LLM mapping errors (review default, edit loop, confidence thresholds)
  - Duplicates (fingerprint + 30‑day dedupe window)
  - History integrity (atomic append, daily rotation, checksum)
  - PII exposure (redact in step logs; full PII only in run.json)
  - Model availability (override, retry/backoff)
  - Storage growth (retention policy; warn at thresholds)
  - ToS/compliance (review default; restrict to simplyhired.com)

- Decisions captured:
  - Quick Apply scope: MVP applies only to SimplyHired Quick Apply; skip off‑site flows.
  - Preview summary: must show the final review page screenshot at minimum.
  - Edit memory: store user edit notes per profile to improve future runs.
  - De‑dupe window: re‑apply allowed after 30 days.
  - Search traversal: add optional keyword‑exclusion setting (e.g., skip titles with “Senior/Lead”).
  - Retention: default keep 30 days (entire run folder including HTML snapshot); configurable, including “forever”.
  - Error handling: on failed submit after approval, auto‑retry once; otherwise return to preview.
  - Proxies: reserved config flag (off by default).

- Areas for further research: Browser‑Use stealth and browser settings best practices; hook patterns for pause/resume; reliable pacing on Windows/Chrome.

---

## Next Steps
1) Scaffold CLI (Typer) and config loader; establish folder structure and `.env.local`.
2) Implement Browser‑Use wrapper (stealth/headful, `user_data_dir`, domain guardrails, pacing).
3) Build SimplyHired playbook: traverse left list → open detail → detect Quick Apply → fill → upload PDF.
4) Add preview server (FastAPI, port 4950) with screenshot‑first UI; Approve/Edit/Abort; auto‑close.
5) Write run store & history (JSONL + per‑run artifacts), including full JD text and HTML snapshot.
6) Deliver a dry‑run for 2 items on a sample search URL; manual login persists session.
7) Iterate selectors and pacing; add the “manual tweak + resume” flow.

---

## References
- Browser‑Use GitHub repository: https://github.com/browser-use/browser-use
- Browser‑Use documentation (selected pages):
  - Browser settings (sessions, channel, keep‑alive, domains): https://docs.browser-use.com/customize/browser-settings
  - Agent settings (actions per step, extraction model): https://docs.browser-use.com/customize/agent-settings
  - Hooks (pause/resume, step lifecycle): https://docs.browser-use.com/customize/hooks
  - Output format and run history: https://docs.browser-use.com/customize/agent-output-format
  - Supported models (OpenAI‑compatible / OpenRouter): https://docs.browser-use.com/customize/supported-models
  - Playwright integration examples: https://docs.browser-use.com/customize/examples/playwright-integration
