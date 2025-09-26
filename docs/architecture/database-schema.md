# Database Schema

MVP uses file‑first storage. JSON Schemas help validate structure; optional SQLite index can be added later without changing contracts.

## Data Contracts (JSON Schema)

### RunRecord — `runs/<id>/run.json`
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:schema:run-record:1-0-0",
  "title": "RunRecord",
  "type": "object",
  "required": ["id", "startedAt", "profileId", "posting", "artifactsDir", "logsPath", "status"],
  "properties": {
    "id": { "type": "string" },
    "startedAt": { "type": "string", "format": "date-time" },
    "profileId": { "type": "string" },
    "status": { "type": "string", "enum": ["pending", "review", "submitting", "submitted", "error", "aborted", "duplicate"] },
    "posting": {
      "type": "object",
      "required": ["postingUrl", "descriptionText", "descriptionHtmlPath"],
      "properties": {
        "postingUrl": { "type": "string", "format": "uri" },
        "title": { "type": "string" },
        "company": { "type": "string" },
        "location": { "type": "string" },
        "descriptionText": { "type": "string" },
        "descriptionHtmlPath": { "type": "string" }
      }
    },
    "preview": {
      "type": "object",
      "properties": {
        "screenshotPath": { "type": "string" },
        "edits": { "type": "string" },
        "approved": { "type": "boolean" },
        "dryRun": { "type": "boolean" }
      }
    },
    "submission": {
      "type": "object",
      "properties": {
        "submittedAt": { "type": "string", "format": "date-time" },
        "confirmation": { "type": "string" },
        "error": { "type": "string" },
        "retried": { "type": "boolean" }
      }
    },
    "artifactsDir": { "type": "string" },
    "logsPath": { "type": "string" }
  }
}
```

### HistoryEntry — `history/history.jsonl` (one JSON per line)
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:schema:history-entry:1-0-0",
  "title": "HistoryEntry",
  "type": "object",
  "required": ["id", "timestamp", "profileId", "postingUrl", "fingerprint", "status"],
  "properties": {
    "id": { "type": "string" },
    "timestamp": { "type": "string", "format": "date-time" },
    "profileId": { "type": "string" },
    "postingUrl": { "type": "string", "format": "uri" },
    "searchUrl": { "type": "string", "format": "uri", "nullable": true },
    "jobTitle": { "type": "string", "nullable": true },
    "company": { "type": "string", "nullable": true },
    "location": { "type": "string", "nullable": true },
    "source": { "type": "string", "enum": ["simplyhired"] },
    "fingerprint": { "type": "string" },
    "status": { "type": "string", "enum": ["submitted", "failed", "aborted", "skipped", "duplicate", "error"] },
    "confirmation": { "type": "string", "nullable": true },
    "error": { "type": "string", "nullable": true },
    "runPath": { "type": "string", "nullable": true },
    "screenshots": { "type": "array", "items": { "type": "string" }, "nullable": true }
  }
}
```

---
