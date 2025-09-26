interface PreviewResponse {
  runId: string;
  status: string;
  preview: {
    screenshotUrl: string;
    summary: string;
    notes?: string;
    edits?: string;
  };
  dryRun: boolean;
}

interface EditRequest {
  text: string;
}

async function parseJson(response: Response) {
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || "Request failed");
  }
  return response.json();
}

export async function createPreviewRun(): Promise<PreviewResponse> {
  const response = await fetch("/api/run/preview", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ dryRun: true }),
  });
  return parseJson(response);
}

export async function approveRun(runId: string) {
  const response = await fetch(`/api/run/${runId}/approve`, { method: "POST" });
  return parseJson(response);
}

export async function abortRun(runId: string) {
  const response = await fetch(`/api/run/${runId}/abort`, { method: "POST" });
  return parseJson(response);
}

export async function editRun(runId: string, text: string) {
  const payload: EditRequest = { text };
  const response = await fetch(`/api/run/${runId}/edit`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseJson(response);
}
