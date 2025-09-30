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
  "required": ["id", "startedAt", "profileId", "mode", "posting", "artifactsDir", "logsPath", "status", "decisions", "queue"],
  "properties": {
    "id": { "type": "string" },
    "startedAt": { "type": "string", "format": "date-time" },
    "profileId": { "type": "string" },
    "mode": { "type": "string", "enum": ["review", "auto_review", "auto_submit"] },
    "status": { "type": "string", "enum": ["pending", "review", "auto_pending", "submitting", "submitted", "error", "aborted", "duplicate"] },
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
        "dryRun": { "type": "boolean" },
        "suggestedDecision": { "$ref": "#/$defs/SubmissionDecision" }
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
    "logsPath": { "type": "string" },
    "decisions": {
      "type": "array",
      "items": { "$ref": "#/$defs/SubmissionDecision" }
    },
    "queue": { "$ref": "#/$defs/ReviewQueueSnapshot" }
  }
}
```

`$defs` additions:

```json
  "$defs": {
    "SubmissionDecision": {
      "type": "object",
      "required": [
        "decisionId",
        "candidateId",
        "outcome",
        "confidence",
        "mode",
        "timestamp",
        "rationaleHash",
        "rationaleRedacted",
        "rationaleTruncated",
        "rationaleLength"
      ],
      "properties": {
        "decisionId": { "type": "string" },
        "candidateId": { "type": "string" },
        "outcome": { "type": "string", "enum": ["approve", "abort", "edit_request", "needs_review"] },
        "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
        "mode": { "type": "string", "enum": ["human", "ai"] },
        "rationalePreview": { "type": "string", "nullable": true },
        "rationaleHash": { "type": "string" },
        "rationaleRedacted": { "type": "boolean" },
        "rationaleTruncated": { "type": "boolean" },
        "rationaleLength": { "type": "integer", "minimum": 0 },
        "requestedChanges": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["field", "value"],
            "properties": {
              "field": { "type": "string" },
              "value": { "type": "string" },
              "reason": { "type": "string" }
            }
          }
        },
        "artifactPath": { "type": "string", "nullable": true },
        "timestamp": { "type": "string", "format": "date-time" }
      }
    },
    "ReviewQueueSnapshot": {
      "type": "object",
      "required": ["mode", "pending", "decided", "escalated", "lastUpdated"],
      "properties": {
        "mode": { "type": "string", "enum": ["review", "auto_review", "auto_submit"] },
        "pending": {
          "type": "array",
          "items": { "$ref": "#/$defs/ApplicationCandidateSummary" }
        },
        "decided": {
          "type": "array",
          "items": { "$ref": "#/$defs/SubmissionDecision" }
        },
        "escalated": {
          "type": "array",
          "items": { "$ref": "#/$defs/ApplicationCandidateSummary" }
        },
        "lastUpdated": { "type": "string", "format": "date-time" }
      }
    },
    "ApplicationCandidateSummary": {
      "type": "object",
      "required": [
        "id",
        "posting",
        "formPlanPath",
        "discoveredAt",
        "state",
        "assignedMode"
      ],
      "properties": {
        "id": { "type": "string" },
        "posting": {
          "type": "object",
          "required": ["postingUrl"],
          "properties": {
            "postingUrl": { "type": "string", "format": "uri" },
            "title": { "type": "string" },
            "company": { "type": "string" },
            "location": { "type": "string" }
          }
        },
        "formPlanPath": { "type": "string" },
        "discoveredAt": { "type": "string", "format": "date-time" },
        "state": {
          "type": "string",
          "enum": ["discovered", "planned", "awaiting_decision", "decided", "submitted", "shelved"]
        },
        "lastDecisionId": { "type": "string" },
        "assignedMode": { "type": "string", "enum": ["human", "ai"] },
        "updatedAt": { "type": "string", "format": "date-time" }
      }
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
  "required": ["id", "timestamp", "profileId", "postingUrl", "fingerprint", "mode", "status"],
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
    "mode": { "type": "string", "enum": ["review", "auto_review", "auto_submit"] },
    "status": { "type": "string", "enum": ["submitted", "failed", "aborted", "skipped", "duplicate", "error", "auto_review_pending"] },
    "confirmation": { "type": "string", "nullable": true },
    "error": { "type": "string", "nullable": true },
    "runPath": { "type": "string", "nullable": true },
    "queuePath": { "type": "string", "nullable": true },
    "screenshots": { "type": "array", "items": { "type": "string" }, "nullable": true },
    "autoReviewSummary": {
      "type": "object",
      "nullable": true,
      "properties": {
        "approved": { "type": "integer" },
        "escalated": { "type": "integer" },
        "autoSubmitted": { "type": "integer" },
        "averageConfidence": { "type": "number" }
      }
    },
    "decisions": {
      "type": "object",
      "nullable": true,
      "properties": {
        "total": { "type": "integer" },
        "byOutcome": {
          "type": "object",
          "additionalProperties": { "type": "integer" }
        },
        "byMode": {
          "type": "object",
          "additionalProperties": { "type": "integer" }
        },
        "latest": {
          "type": "object",
          "additionalProperties": { "type": "string", "format": "date-time" }
        },
        "lastDecisionAt": { "type": "string", "format": "date-time", "nullable": true }
      }
    },
    "queueDepth": {
      "type": "object",
      "nullable": true,
      "properties": {
        "pending": { "type": "integer" },
        "decided": { "type": "integer" },
        "escalated": { "type": "integer" },
        "lastUpdated": { "type": "string", "format": "date-time", "nullable": true }
      }
    },
    "decision": {
      "type": "object",
      "nullable": true,
      "required": [
        "outcome",
        "mode",
        "confidence",
        "timestamp",
        "rationaleHash",
        "rationaleRedacted",
        "rationaleLength"
      ],
      "properties": {
        "id": { "type": "string", "nullable": true },
        "candidateId": { "type": "string", "nullable": true },
        "outcome": { "type": "string", "enum": ["approve", "abort", "edit_request", "needs_review"] },
        "mode": { "type": "string", "enum": ["human", "ai"] },
        "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
        "timestamp": { "type": "string", "format": "date-time" },
        "artifactPath": { "type": "string", "nullable": true },
        "rationalePreview": { "type": "string", "nullable": true },
        "rationaleHash": { "type": "string" },
        "rationaleRedacted": { "type": "boolean" },
        "rationaleTruncated": { "type": "boolean" },
        "rationaleLength": { "type": "integer", "minimum": 0 }
      }
    }
  }
}
```

---
