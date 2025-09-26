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

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || "Request failed");
  }
  return response.json() as Promise<T>;
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
