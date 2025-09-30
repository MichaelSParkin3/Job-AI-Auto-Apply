# Frontend Architecture

## Component Architecture
- Organization: Small, focused components in `apps/ui/src`; shadcn/ui primitives; feature folders for preview.

```text
apps/ui/src/
  components/
    PreviewCard.tsx
    Toolbar.tsx
    DecisionConfidenceBadge.tsx
    HandoffBanner.tsx
  features/preview/
    PreviewScreen.tsx
    EditDialog.tsx
    QueuePanel.tsx
    AutoRunDashboard.tsx
    store.ts
  lib/
    api.ts
    errors.ts
  main.tsx
```

### Component Template
```tsx
import { Card } from "@/components/ui/card";

export function PreviewCard({ screenshotUrl, summary }: { screenshotUrl: string; summary: string }) {
  return (
    <Card className="p-4 space-y-3">
      <img src={screenshotUrl} alt="Final review screenshot" className="rounded border" />
      <pre className="text-sm whitespace-pre-wrap">{summary}</pre>
    </Card>
  );
}
```

## State Management Architecture
- Zustand store for simple UI state and API calls; no global framework deps.

```ts
import { create } from "zustand";

interface PreviewState {
  runId?: string;
  status: "idle" | "loading" | "ready" | "submitting" | "error";
  error?: string;
  set: (p: Partial<PreviewState>) => void;
}

interface QueueState {
  pending: ApplicationCandidateSummary[];
  escalated: ApplicationCandidateSummary[];
  decisions: SubmissionDecision[];
  mode: "review" | "ai_autofill" | "auto_review" | "auto_submit";
  handoffPending: ApplicationCandidateSummary[];
}

export const usePreview = create<PreviewState & QueueState>((set) => ({
  status: "idle",
  pending: [],
  escalated: [],
  decisions: [],
  handoffPending: [],
  mode: "review",
  set: (p) => set(p),
}));
```

## Routing Architecture
- React Router optional; MVP can be single‑route `/ui`.

## Frontend Services Layer
```ts
// apps/ui/src/lib/api.ts
export async function approve(runId: string) {
  const res = await fetch(`/api/run/${runId}/approve`, { method: "POST" });
  if (!res.ok) throw new Error("approve_failed");
}

export async function fetchQueue(runId: string) {
  const res = await fetch(`/api/queue/${runId}`);
  if (!res.ok) throw new Error("queue_fetch_failed");
  return (await res.json()) as QueueState;
}
```

## Key Views
- **PreviewScreen:** remains the focused, single-candidate review with AI suggestion badges, assisted submit banners, and keyboard shortcuts.
- **QueuePanel:** collapsible side drawer listing pending, escalated, and recently decided items; supports filters (`needs review`, `auto submitted`).
- **HandoffBanner:** inline component that surfaces `handoff_pending` candidates with “Resume in Browser” CTA, live status, and confirmation buttons.
- **AutoRunDashboard:** provides run-level telemetry (decisions per minute, AI confidence histogram) for unattended sessions; enables manual overrides mid-run.

All views are driven by the shared Zustand store so human reviewers and observers see real-time queue updates regardless of mode.

---
