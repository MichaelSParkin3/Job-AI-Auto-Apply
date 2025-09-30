# Core Workflows

```mermaid
sequenceDiagram
  participant U as User
  participant CLI as Typer CLI
  participant BR as Browser-Use
  participant P as Preview (FastAPI)
  participant UI as React UI
  participant G as Google SERP
  participant L as Lever (ATS)

  U->>CLI: apply --source lever-google --limit 2 --profile <id> --mode review
  CLI->>BR: Open Google query (site:jobs.lever.co/apply + filters)
  BR->>G: Collect result anchors and /apply URLs
  BR->>L: Open Lever form, map + fill, upload resume
  BR-->>CLI: Capture pre-submit screenshot + summary / auto-fill handoff
  CLI->>P: POST /api/run/preview (payload)
  UI->>U: Approve/Edit/Abort
  P->>CLI: Decision (review mode only; do not submit)
```
```

- **Session resilience** â€” after the readiness sequence returns `ready`, the CLI spawns a background copy of the resolved Chrome profile into `.local/browser/backups/<profile>/` and records the outcome in both the console payload (`backups.*`) and `runs/<id>/run.json`. If a subsequent launch detects a corrupt session (missing `Preferences`, launch error) the CLI restores the latest snapshot once before surfacing a fatal error. Operators can disable this behaviour per-run or per-profile when ephemeral sessions are desired.

## Run Modes & Decision Flow

- **Mode selection** happens before the Browser-Use session launches. The CLI resolves `mode` from CLI flag â†’ profile override â†’ global config and records it in `run.json` so the preview UI and history know which guardrails to enforce. `ai_autofill` uses the same guardrails as `review` but enables LLM-driven fill + submit attempts.
- **Decision engines** share a `SubmissionDecision` contract (`{ outcome: approve|edit_request|abort|needs_review, confidence, rationale, nextActions[] }`).
  - `HumanDecisionEngine` subscribes to preview UI events; the queue pauses while waiting for a person to respond.
  - `LLMDecisionEngine` consumes queue entries asynchronously, scoring each candidate and auto-resolving when confidence â‰¥ threshold, otherwise returning `needs_review` to fall back to the human queue.
  - `AutoFillOrchestrator` replays Browser-Use steps and submit attempts; it emits `AUTOFILL_*` telemetry and packages `handoff_pending` snapshots when blockers appear.
- **Queue states** evolve deterministically: `discovered â†’ planned â†’ awaiting_decision â†’ (handoff_pending)? â†’ decided â†’ submitted|shelved`. Queue snapshots are persisted to `run.json.decisions[]` so auto-mode runs can be audited after the fact.

```mermaid
stateDiagram-v2
  [*] --> discovered
  discovered --> planned: Form plan ready
  planned --> awaiting_decision
  awaiting_decision --> handoff_pending: auto-fill blocked (captcha/mfa)
  awaiting_decision --> decided: Human/AI returns approve/abort/edit
  handoff_pending --> awaiting_decision: resume request queued
  handoff_pending --> submitted: user confirms assisted success
  handoff_pending --> shelved: user aborts after handoff
  decided --> submitted: approve + run mode auto_submit
  decided --> awaiting_decision: needs_review fallback
  decided --> shelved: abort or timeout
```

## AI Auto Fill Assisted Submit Flow

```mermaid
sequenceDiagram
  participant CLI as Typer CLI
  participant BR as Browser-Use
  participant DEC as AutoFillOrchestrator
  participant UI as Preview UI
  participant U as User

  CLI->>BR: Launch ai_autofill run (headful Chrome)
  BR->>DEC: Execute LLM-guided plan
  DEC-->>CLI: AUTOFILL_HANDOFF_READY {blockedReason, snapshot}
  CLI->>UI: Update queue item state handoff_pending
  U->>UI: Click "Resume in Browser"
  UI->>CLI: POST /api/run/{id}/handoff/{candidate}/launch
  CLI->>BR: Rehydrate session + replay saved field state
  CLI-->>U: Focus submit button, wait for manual solve
  U->>UI: Confirm outcome (Success/Still Blocked)
  UI->>CLI: POST /api/queue/{id}/handoff-confirmation
  CLI->>DEC: Persist submission result + history
```

## Auto Review & Full Auto Variants

```mermaid
sequenceDiagram
  participant SCHED as Scheduler (optional)
  participant CLI as Typer CLI
  participant DEC as Decision Engine
  participant BR as Browserâ€‘Use
  participant QUEUE as Review Queue
  participant HIST as Run Store

  SCHED-->>CLI: apply --mode auto_review --schedule 14:00
  CLI->>BR: Discover + fill candidate
  CLI->>QUEUE: enqueue(ApplicationCandidate)
  DEC->>QUEUE: pull next candidate
  DEC->>CLI: Decision (approve/confidence)
  CLI->>BR: (auto_submit mode only) submit
  CLI->>HIST: Append decision audit + summary
  CLI->>QUEUE: mark resolved / fallback to human queue
```

- **AI Auto Fill (`ai_autofill`)** performs autonomous form fill + submit attempts. On success it records immediate submission; on blockers it serializes handoff snapshots so humans can resume without re-entering data.
- **Auto Review (`auto_review`)** stops short of submission. Decisions plus rationale are stored, and the user can resume later via CLI/UI to submit manually.
- **Full Auto (`auto_submit`)** immediately executes approved decisions, but any low-confidence or error state automatically flips the candidate back into the human queue and triggers a notification.

---
