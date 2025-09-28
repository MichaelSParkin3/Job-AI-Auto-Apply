# Core Workflows

## Review‑First Apply (Sequence)
```mermaid
sequenceDiagram
  participant U as User
  participant CLI as Typer CLI
  participant BR as Browser‑Use
  participant P as Preview (FastAPI)
  participant UI as React UI
  participant SH as SimplyHired

  U->>CLI: apply --search <url> --limit 2 --profile <id> --dry-run
  CLI->>BR: Navigate search, detect Quick Apply, open flow
  BR->>SH: Fill forms (stealth pacing), upload resume
  BR-->>CLI: Capture final review screenshot + details
  CLI->>P: POST /api/run/preview (payload)
  UI->>U: Show screenshot + summary (Approve/Edit/Abort)
  U->>P: Approve or Edit or Abort
  P->>CLI: Approve → proceed to submit (or Edit once, then retry)
  CLI->>BR: Submit; on error → retry once; else success
  CLI->>Artifacts: Save run.json, screenshots, logs; append history.jsonl with decision trail
```

- **Session resilience** — after the readiness sequence returns `ready`, the CLI spawns a background copy of the resolved Chrome profile into `.local/browser/backups/<profile>/` and records the outcome in both the console payload (`backups.*`) and `runs/<id>/run.json`. If a subsequent launch detects a corrupt session (missing `Preferences`, launch error) the CLI restores the latest snapshot once before surfacing a fatal error. Operators can disable this behaviour per-run or per-profile when ephemeral sessions are desired.

## Run Modes & Decision Flow

- **Mode selection** happens before the Browser-Use session launches. The CLI resolves `mode` from CLI flag → profile override → global config and records it in `run.json` so the preview UI and history know which guardrails to enforce.
- **Decision engines** share a `SubmissionDecision` contract (`{ outcome: approve|edit_request|abort|needs_review, confidence, rationale, nextActions[] }`).
  - `HumanDecisionEngine` subscribes to preview UI events; the queue pauses while waiting for a person to respond.
  - `LLMDecisionEngine` consumes queue entries asynchronously, scoring each candidate and auto-resolving when confidence ≥ threshold, otherwise returning `needs_review` to fall back to the human queue.
- **Queue states** evolve deterministically: `discovered → planned → awaiting_decision → decided → submitted|shelved`. Queue snapshots are persisted to `run.json.decisions[]` so auto-mode runs can be audited after the fact.

```mermaid
stateDiagram-v2
  [*] --> discovered
  discovered --> planned: Form plan ready
  planned --> awaiting_decision
  awaiting_decision --> decided: Human/AI returns approve/abort/edit
  decided --> submitted: approve + run mode auto_submit
  decided --> awaiting_decision: needs_review fallback
  decided --> shelved: abort or timeout
```

## Auto Review & Full Auto Variants

```mermaid
sequenceDiagram
  participant SCHED as Scheduler (optional)
  participant CLI as Typer CLI
  participant DEC as Decision Engine
  participant BR as Browser‑Use
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

- **Auto Review (`auto_review`)** stops short of submission. Decisions plus rationale are stored, and the user can resume later via CLI/UI to submit manually.
- **Full Auto (`auto_submit`)** immediately executes approved decisions, but any low-confidence or error state automatically flips the candidate back into the human queue and triggers a notification.

---
