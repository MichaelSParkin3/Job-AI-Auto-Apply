# Frontend Architecture

## Component Architecture
- Organization: Small, focused components in `apps/ui/src`; shadcn/ui primitives; feature folders for preview.

```text
apps/ui/src/
  components/
    PreviewCard.tsx
    Toolbar.tsx
  features/preview/
    PreviewScreen.tsx
    EditDialog.tsx
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

export const usePreview = create<PreviewState>((set) => ({
  status: "idle",
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
```

---
