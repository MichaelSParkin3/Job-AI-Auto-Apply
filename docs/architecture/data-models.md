# Data Models

## Profile
**Purpose:** Encapsulate per‑role identity, Q&A overrides, and resume path.

**Key Attributes:**
- `id`: string — profile slug
- `resumePath`: string — path to PDF
- `qaOverrides`: Record<string,string> — question→answer map

### TypeScript Interface
```ts
export interface Profile {
  id: string;
  displayName: string;
  documents: {
    resumePath: string;
  };
  qaOverrides?: Record<string, string>;
  userDataDir: string; // persistent Chrome session dir
}
```

### Relationships
- Used by Run to parameterize automation

## JobPosting
**Purpose:** Captured metadata and full description for dedupe and audit.

**Key Attributes:**
- `postingUrl`: string — canonical URL
- `title`: string — job title

### TypeScript Interface
```ts
export interface JobPosting {
  postingUrl: string;
  title: string;
  company?: string;
  location?: string;
  descriptionText: string;
  descriptionHtmlPath: string; // stored snapshot
}
```

### Relationships
- Referenced by Run; fingerprint computed from `postingUrl + sha256(descriptionText)`

## Run
**Purpose:** Single application attempt with artifacts and outcomes.

**Key Attributes:**
- `id`: string — run id
- `profileId`: string — link to Profile
- `mode`: `review|ai_autofill|auto_review|auto_submit`
- `status`: `pending|review|auto_pending|submitting|success|error|aborted`
- `autofill`: metadata about AI fill attempts (`attempted`, `blockedReason`, `handoffSnapshotPath`, `manualAttempts`, `lastLaunchedAt`)
- `decisions[]`: ordered list of decision payloads with hashed rationales (see below)
- `queue`: snapshot of outstanding candidates with state machine metadata and queue depth counters

### TypeScript Interface
```ts
export interface RunRecord {
  id: string;
  startedAt: string;
  profileId: string;
  mode: "review" | "ai_autofill" | "auto_review" | "auto_submit";
  posting: JobPosting;
  preview: {
    screenshotPath?: string;
    edits?: string;
    approved: boolean;
    dryRun: boolean;
    suggestedDecision?: SubmissionDecision;
  };
  autofill?: {
    attempted: boolean;
    blockedReason?: "captcha" | "mfa" | "unknown_form_change";
    handoffSnapshotPath?: string;
    manualAttempts?: number;
    lastLaunchedAt?: string;
  };
  submission?: {
    submittedAt?: string;
    confirmation?: string;
    error?: string;
    retried?: boolean;
  };
  artifactsDir: string;
  logsPath: string; // redacted step log
  decisions: SubmissionDecision[];
  queue: ReviewQueueSnapshot;
}
```

### Relationships
- Appended summary written to `history.jsonl`

## SubmissionDecision
**Purpose:** Canonical response from human or AI reviewers.

**Key Attributes:**
- `candidateId`: string — identifier for the queue item
- `outcome`: `approve|abort|edit_request|needs_review`
- `confidence`: number 0-1
- `mode`: `human|ai`
- `rationaleHash`: deterministic SHA-256 hash for correlating rationale text stored elsewhere
- `rationalePreview?`: sanitized and truncated summary of the rationale (no raw PII)
- `rationaleRedacted`: boolean flag indicating whether redaction modified the preview
- `rationaleTruncated`: boolean flag indicating whether preview was shortened for length
- `rationaleLength`: number — original character count prior to redaction
- `requestedChanges?`: array of structured edits (field/value pairs)
- `artifactPath?`: relative path to the persisted decision artifact under the run directory
- `timestamp`: ISO string

```ts
export interface SubmissionDecision {
  decisionId: string;
  candidateId: string;
  outcome: "approve" | "abort" | "edit_request" | "needs_review";
  confidence: number;
  mode: "human" | "ai";
  rationaleHash: string;
  rationalePreview?: string;
  rationaleRedacted: boolean;
  rationaleTruncated: boolean;
  rationaleLength: number;
  requestedChanges?: Array<{ field: string; value: string; reason?: string }>;
  artifactPath?: string;
  timestamp: string;
}
```

## ReviewQueueSnapshot
**Purpose:** Persist queue state for auditability and resume support.

```ts
export interface ReviewQueueSnapshot {
  mode: "review" | "auto_review" | "auto_submit";
  pending: ApplicationCandidateSummary[];
  decided: SubmissionDecision[];
  escalated: ApplicationCandidateSummary[]; // waiting for human review after AI fallback
  lastUpdated: string;
}

export interface ApplicationCandidateSummary {
  id: string;
  posting: Pick<JobPosting, "postingUrl" | "title" | "company" | "location">;
  formPlanPath: string;
  discoveredAt: string;
  state: "discovered" | "planned" | "awaiting_decision" | "handoff_pending" | "decided" | "submitted" | "shelved";
  lastDecisionId?: string;
  assignedMode: "human" | "ai";
  updatedAt?: string;
}
```

## AutoFillSnapshot
**Purpose:** Persist AI-populated form state for manual assisted submit.

**Key Attributes:**
- `candidateId`: string — queue identifier
- `fieldValues`: array of `{ selector, valueHash, widgetType }`
- `resume`: `{ uploaded: boolean; path?: string }`
- `blockedReason`: `captcha|mfa|unknown_form_change`
- `capturedAt`: ISO timestamp

```json
{
  "candidateId": "lever-123",
  "blockedReason": "captcha",
  "fieldValues": [
    { "selector": "#first-name", "valueHash": "sha256:...", "widgetType": "text" },
    { "selector": "#cover-letter", "valueHash": "sha256:...", "widgetType": "textarea" }
  ],
  "resume": { "uploaded": true, "path": "runs/2025-01-05/autofill/resume.pdf" },
  "capturedAt": "2025-01-05T17:12:44Z"
}
```

## LeverAutofillPlan
**Purpose:** Persist normalized fill intents per Lever candidate, combining deterministic selectors with optional LLM enrichment.

**Key Attributes:**
- `candidateId`: string — queue identifier
- `model`: string — plan refinement model resolved via CLI → profile → global precedence
- `llmUsed`: boolean — indicates if LLM output shaped the intents
- `generatedAt`: ISO timestamp
- `fields`: array of `{ key, label, selector, fieldType, strategy, confidence, fallbackSelector, metadata }`
- `telemetry`: `{ tokenUsage: { prompt, completion, total }, latencyMs, confidence: { average, min, max } }`
- `answers`: map keyed by valueKey summarising precedence (`status`, `source`)
- `promptArtifacts`: hashed prompt bundles stored under `runs/<id>/autofill/prompts/`

```json
{
  "candidateId": "lever-123",
  "model": "deepseek/deepseek-chat-v3.1:free",
  "llmUsed": false,
  "generatedAt": "2025-12-18T03:41:02Z",
  "fields": [
    {
      "key": "fullName",
      "label": "Full name",
      "selector": "input[data-qa='name-input']",
      "fieldType": "text",
      "strategy": "profile_answer",
      "confidence": 0.9,
      "fallbackSelector": "input[data-qa='name-input']",
      "metadata": { "answerSource": "identity.full_name" }
    },
    {
      "key": "securityAnswer",
      "label": "Security question",
      "selector": "textarea[data-qa='security-answer']",
      "fieldType": "textarea",
      "strategy": "deterministic_selector",
      "confidence": 0.55,
      "fallbackSelector": "textarea[data-qa='security-answer']",
      "metadata": {}
    }
  ],
  "telemetry": {
    "tokenUsage": { "prompt": 0, "completion": 0, "total": 0 },
    "latencyMs": 0,
    "confidence": { "average": 0.725, "min": 0.55, "max": 0.9 }
  },
  "answers": {
    "fullName": { "status": "resolved", "source": "identity.full_name" },
    "securityAnswer": { "status": "missing", "source": "qa_override" }
  }
}
```

---
