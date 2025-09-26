# Requirements

## Functional (FR)
- FR1: Provide a Typer-based CLI with subcommands: `apply`, `profiles`, `config`, `history`.
- FR2: Load global defaults from `config/config.yaml`; resolve precedence CLI → profile → global.
- FR3: Manage per-profile YAML (identity, Q&A, overrides) with `documents.resume_path` under `data/resumes/{profile}/resume.pdf` and persistent Chrome `user_data_dir` per profile.
- FR4: Given a SimplyHired search URL, iterate up to `--limit` items (default `2`); detect “Quick Apply”; open application flow.
- FR5: Fill forms using the active profile with heuristic selectors tolerant to A/B variants; follow top-down, human-like pacing.
- FR6: Upload the profile’s PDF resume during the application flow.
- FR7: Present a preview window (FastAPI, port `4950`) that shows at minimum the final review page screenshot with controls: Approve, Edit, Abort; apply simple textual edits and retry once; Dry-Run never submits.
- FR8: On approval, submit the application; detect confirmation or error and auto-retry once on failure; otherwise return to preview.
- FR9: Persist per-run artifacts: screenshots (default) and optional video; `actions.log` with PII redacted; `run.json` containing full submitted details.
- FR10: Append an entry to `history/history.jsonl` for every run and persist `runs/.../run.json`; capture and store full job description text and an HTML snapshot; compute a dedupe fingerprint and skip duplicates within 30 days.
- FR11: Use headful Chrome with Browser-Use stealth enabled, one-tab flows, persistent sessions, and domain guardrails to `*.simplyhired.com`.
- FR12: Provide deterministic Playwright fallbacks for uploads/quirky widgets when LLM actions are insufficient.
- FR13: Expose artifact and retention settings via config/CLI (screenshots, video, keep days) and warn at configurable storage thresholds.
- FR14: Support quick profile switching and isolation: list/select active profile; ensure user data dir and documents are profile-scoped.
- FR15: Emit clear CLI status and exit codes; redact PII in logs while preserving a complete audit trail in artifacts.
- FR16: Load OpenRouter API keys from `.env.local`; default model `deepseek/deepseek-chat-v3.1:free`; allow overrides per profile/CLI.
- FR17: Implement deduplication (fingerprint = `posting_url + sha256(job_description_full)`); allow re-apply after 30 days.
- FR18: Enforce guardrails (domain restriction, default `--limit 2`, manual login persistence) to reduce risk and brittleness.

## Non-Functional (NFR)
- NFR1: Privacy — All PII and artifacts remain local; no cloud storage of user data.
- NFR2: Performance — Median Review-mode submit ≤ 120s; preview decision ≤ 10s.
- NFR3: Reliability — ≥ 95% submit success in Review mode; auto-retry once on failure.
- NFR4: Stealth — Headful Chrome, human-like pacing, stable viewport/timezone/locale, one-tab flow, persistent sessions.
- NFR5: Security — Redact PII in step logs; store full PII only in `run.json`; secrets in `.env.local`; respect site ToS; restrict domains.
- NFR6: Usability — Profile switch ≤ 2s; ≤ 1 manual correction per application; minimal yet clear preview UI.
- NFR7: Compatibility — Windows 10/11, Chrome stable, Python 3.11+, Playwright Chromium installed.
- NFR8: Observability — Artifacts for 100% of runs; `history.jsonl` append latency ≤ 1s; error taxonomy captured.
- NFR9: Maintainability — File-first storage contracts; modular site playbooks; dry-run supports local testing.
- NFR10: Scalability — Support configurable `--limit`; retention policies and threshold warnings for storage growth.
- NFR11: Resilience — Session backup/restore; recreate on corruption; model override and backoff when default unavailable.
- NFR12: Compliance — No CAPTCHA bypass; stays within SimplyHired “Quick Apply”; do not follow off-site flows.

### Rationale (Requirements)
- Source of truth is docs/brief.md; FRs directly map to CLI, automation flow, preview, artifacting, and history requirements described there. Trade-offs favor local-first privacy and reliability over breadth (single-site MVP). Stealth constraints (headful, pacing, domain guardrails) limit speed but reduce bot detection risk. Assumptions include availability of OpenRouter free model and Chrome on Windows. Key items needing validation: acceptable pacing defaults, edit loop UX, and JD snapshot legality for local storage.

---
