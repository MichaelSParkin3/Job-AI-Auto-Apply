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
- `mode`: `review|auto_review|auto_submit`
- `status`: `pending|review|auto_pending|submitting|success|error|aborted`
- `decisions[]`: ordered list of decision payloads (see below)
- `queue`: snapshot of outstanding candidates with state machine metadata

### TypeScript Interface
```ts
export interface RunRecord {
  id: string;
  startedAt: string;
  profileId: string;
  mode: "review" | "auto_review" | "auto_submit";
  posting: JobPosting;
  preview: {
    screenshotPath?: string;
    edits?: string;
    approved: boolean;
    dryRun: boolean;
    suggestedDecision?: SubmissionDecision;
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
- `rationale`: string — sanitized explanation for audit trail
- `requestedChanges?`: array of structured edits (field/value pairs)
- `timestamp`: ISO string

```ts
export interface SubmissionDecision {
  decisionId: string;
  candidateId: string;
  outcome: "approve" | "abort" | "edit_request" | "needs_review";
  confidence: number;
  mode: "human" | "ai";
  rationale: string;
  requestedChanges?: Array<{ field: string; value: string; reason?: string }>;
  timestamp: string;
}
```

## ReviewQueueSnapshot
**Purpose:** Persist queue state for auditability and resume support.

```ts
export interface ReviewQueueSnapshot {
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
  state: "discovered" | "planned" | "awaiting_decision" | "decided" | "submitted" | "shelved";
  lastDecisionId?: string;
}
```

---
