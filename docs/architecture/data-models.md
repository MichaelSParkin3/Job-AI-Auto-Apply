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
- `status`: `pending|review|submitting|success|error`

### TypeScript Interface
```ts
export interface RunRecord {
  id: string;
  startedAt: string;
  profileId: string;
  posting: JobPosting;
  preview: {
    screenshotPath?: string;
    edits?: string;
    approved: boolean;
    dryRun: boolean;
  };
  submission?: {
    submittedAt?: string;
    confirmation?: string;
    error?: string;
    retried?: boolean;
  };
  artifactsDir: string;
  logsPath: string; // redacted step log
}
```

### Relationships
- Appended summary written to `history.jsonl`

---
