export interface PreviewMetadata {
  profileId?: string;
  profileLabel?: string;
  startedAt?: string;
  limit?: number;
  mode?: string;
}

export interface PreviewPayload {
  screenshotUrl: string;
  summary: string;
  notes?: string;
  edits?: string;
  decision?: string;
  decidedAt?: string;
  lastEditAt?: string;
}

export interface PreviewResponse {
  runId: string;
  status: string;
  preview: PreviewPayload;
  dryRun: boolean;
  metadata?: PreviewMetadata;
}

interface EditRequest {
  text: string;
}

export interface ActionResponse {
  ok: boolean;
  status: string;
  message?: string;
  preview?: PreviewPayload;
  metadata?: PreviewMetadata;
  decidedAt?: string;
}

export interface CandidatePosting {
  postingUrl?: string;
  title?: string;
  company?: string;
  location?: string;
}

export interface ApplicationCandidateSummary {
  id: string;
  posting?: CandidatePosting;
  formPlanPath?: string;
  discoveredAt?: string;
  state:
    | "discovered"
    | "planned"
    | "awaiting_decision"
    | "decided"
    | "submitted"
    | "shelved";
  lastDecisionId?: string;
  assignedMode: "human" | "ai";
  updatedAt?: string;
}

export interface SubmissionDecision {
  decisionId: string;
  candidateId: string;
  outcome: "approve" | "abort" | "edit_request" | "needs_review";
  mode: "human" | "ai";
  confidence: number;
  rationale?: string;
  requestedChanges?: Array<{ field: string; value: string; reason: string }>;
  timestamp: string;
}

export interface ReviewQueueSnapshot {
  mode: "review" | "auto_review" | "auto_submit";
  pending: ApplicationCandidateSummary[];
  decided: SubmissionDecision[];
  escalated: ApplicationCandidateSummary[];
  lastUpdated: string;
}

export interface ManualOverrideEntry {
  decision: SubmissionDecision;
  createdAt: string;
}

interface ApiErrorDetail {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown>;
    requestId?: string;
  };
}

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const message = await extractErrorMessage(response);
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const json = (await response.json()) as ApiErrorDetail;
    const description = json.error?.message || json.error?.code;
    if (description) {
      return description;
    }
  } catch (error) {
    // Ignore JSON parsing errors and fall back to text payload.
  }
  const detail = await response.text();
  return detail || "Request failed";
}

export async function createPreviewRun(): Promise<PreviewResponse> {
  const response = await fetch("/api/run/preview", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ dryRun: true }),
  });
  return parseJson<PreviewResponse>(response);
}

export async function approveRun(runId: string): Promise<ActionResponse> {
  const response = await fetch(`/api/run/${runId}/approve`, { method: "POST" });
  return parseJson<ActionResponse>(response);
}

export async function abortRun(runId: string): Promise<ActionResponse> {
  const response = await fetch(`/api/run/${runId}/abort`, { method: "POST" });
  return parseJson<ActionResponse>(response);
}

export async function editRun(runId: string, text: string): Promise<ActionResponse> {
  const payload: EditRequest = { text };
  const response = await fetch(`/api/run/${runId}/edit`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseJson<ActionResponse>(response);
}

export async function fetchQueueSnapshot(
  runId: string
): Promise<ReviewQueueSnapshot> {
  const response = await fetch(`/api/queue/${runId}`);
  return parseJson<ReviewQueueSnapshot>(response);
}

export async function submitQueueDecision(
  runId: string,
  decision: SubmissionDecision
): Promise<void> {
  const response = await fetch(`/api/queue/${runId}/decision`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(decision),
  });
  if (!response.ok) {
    const message = await extractErrorMessage(response);
    throw new Error(message);
  }
}

export async function overrideCandidateMode(
  runId: string,
  candidateId: string,
  mode: "human" | "ai",
  reason?: string
): Promise<ReviewQueueSnapshot> {
  const response = await fetch(`/api/queue/${runId}/${candidateId}/mode`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ mode, reason }),
  });
  const payload = await parseJson<{ queue: ReviewQueueSnapshot }>(response);
  return payload.queue;
}
