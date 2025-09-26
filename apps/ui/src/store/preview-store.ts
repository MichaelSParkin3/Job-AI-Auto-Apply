import { create } from "zustand";

export type PreviewStatus =
  | "idle"
  | "loading"
  | "ready"
  | "approved"
  | "editing"
  | "aborted"
  | "error";

export interface PreviewData {
  screenshotUrl: string;
  summary: string;
  notes?: string;
  edits?: string;
}

interface PreviewState {
  runId?: string;
  status: PreviewStatus;
  dryRun: boolean;
  preview?: PreviewData;
  message?: string;
  set: (partial: Partial<PreviewState>) => void;
  reset: () => void;
}

export const usePreviewStore = create<PreviewState>((set) => ({
  status: "idle",
  dryRun: true,
  set: (partial) => set((state) => ({ ...state, ...partial })),
  reset: () =>
    set({
      runId: undefined,
      status: "idle",
      dryRun: true,
      preview: undefined,
      message: undefined,
    }),
}));
