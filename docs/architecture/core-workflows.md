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
  CLI->>Artifacts: Save run.json, screenshots, logs; append history.jsonl
```

---
