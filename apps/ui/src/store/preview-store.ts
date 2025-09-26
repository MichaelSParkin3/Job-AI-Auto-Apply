import { create } from "zustand";

import type { PreviewPayload, PreviewResponse } from "../lib/api";

export type PreviewStatus =
  | "idle"
  | "loading"
  | "ready"
  | "approved"
  | "editing"
  | "aborted"
  | "error";

export type PreviewData = PreviewPayload;

export type PreviewMetadata = PreviewResponse["metadata"];

interface PreviewState {
  runId?: string;
  status: PreviewStatus;
  dryRun: boolean;
  preview?: PreviewData;
  metadata?: PreviewMetadata;
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
      metadata: undefined,
      message: undefined,
    }),
}));
