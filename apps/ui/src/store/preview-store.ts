import { create } from "zustand";

import type {
  ApplicationCandidateSummary,
  ManualOverrideEntry,
  PreviewPayload,
  PreviewResponse,
  ReviewQueueSnapshot,
  SubmissionDecision,
} from "../lib/api";

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

export interface PreviewQueueState extends ReviewQueueSnapshot {}

interface PreviewState {
  runId?: string;
  status: PreviewStatus;
  dryRun: boolean;
  preview?: PreviewData;
  metadata?: PreviewMetadata;
  message?: string;
  queue?: PreviewQueueState;
  activeCandidateId?: string;
  drawerOpen: boolean;
  legendVisible: boolean;
  decisionBusy: boolean;
  decisionError?: string;
  suggestedOutcome?: string;
  overrides: ManualOverrideEntry[];
  set: (partial: Partial<PreviewState>) => void;
  reset: () => void;
  setQueueSnapshot: (snapshot: ReviewQueueSnapshot) => void;
  selectCandidate: (candidateId?: string) => void;
  selectNextCandidate: () => void;
  selectPreviousCandidate: () => void;
  setDrawerOpen: (open: boolean) => void;
  setLegendVisible: (visible: boolean) => void;
  setDecisionBusy: (busy: boolean) => void;
  setDecisionError: (message?: string) => void;
  addOverride: (entry: ManualOverrideEntry) => void;
  removeOverride: (decisionId: string) => void;
  applyOptimisticDecision: (candidateId: string, decision: SubmissionDecision) => void;
}

export const usePreviewStore = create<PreviewState>((set) => ({
  status: "idle",
  dryRun: true,
  drawerOpen: typeof window !== "undefined"
    ? window.sessionStorage.getItem("queueDrawerOpen") === "false"
      ? false
      : true
    : true,
  legendVisible: false,
  decisionBusy: false,
  overrides: [],
  set: (partial) => set((state) => ({ ...state, ...partial })),
  reset: () =>
    set({
      runId: undefined,
      status: "idle",
      dryRun: true,
      preview: undefined,
      metadata: undefined,
      message: undefined,
      queue: undefined,
      activeCandidateId: undefined,
      drawerOpen: true,
      legendVisible: false,
      decisionBusy: false,
      decisionError: undefined,
      suggestedOutcome: undefined,
      overrides: [],
    }),
  setQueueSnapshot: (snapshot) =>
    set((state) => {
      const overrideDecisions = state.overrides.map((entry) => entry.decision);
      const dedupedDecisions = dedupeDecisions([
        ...snapshot.decided,
        ...overrideDecisions,
      ]);
      const collections: PreviewQueueState = {
        ...snapshot,
        decided: dedupedDecisions,
      };
      const selectableCandidates: ApplicationCandidateSummary[] = [
        ...collections.pending,
        ...collections.escalated,
      ];
      const activeExists = selectableCandidates.some(
        (candidate) => candidate.id === state.activeCandidateId
      );
      const fallbackCandidate = selectableCandidates[0]?.id;
      const suggestedOutcome = deriveSuggestedOutcome(snapshot);
      return {
        ...state,
        queue: collections,
        activeCandidateId: activeExists
          ? state.activeCandidateId
          : fallbackCandidate,
        suggestedOutcome,
      };
    }),
  selectCandidate: (candidateId) =>
    set((state) => ({
      ...state,
      activeCandidateId: candidateId,
    })),
  selectNextCandidate: () =>
    set((state) => ({
      ...state,
      activeCandidateId: getNextCandidateId(state, 1),
    })),
  selectPreviousCandidate: () =>
    set((state) => ({
      ...state,
      activeCandidateId: getNextCandidateId(state, -1),
    })),
  setDrawerOpen: (open) => {
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem("queueDrawerOpen", String(open));
    }
    set((state) => ({ ...state, drawerOpen: open }));
  },
  setLegendVisible: (visible) =>
    set((state) => ({ ...state, legendVisible: visible })),
  setDecisionBusy: (busy) =>
    set((state) => ({ ...state, decisionBusy: busy })),
  setDecisionError: (message) =>
    set((state) => ({ ...state, decisionError: message })),
  addOverride: (entry) =>
    set((state) => ({
      ...state,
      overrides: [...state.overrides, entry],
      queue: state.queue
        ? {
            ...state.queue,
            decided: dedupeDecisions([
              ...state.queue.decided,
              entry.decision,
            ]),
          }
        : state.queue,
    })),
  removeOverride: (decisionId) =>
    set((state) => ({
      ...state,
      overrides: state.overrides.filter(
        (entry) => entry.decision.decisionId !== decisionId
      ),
      queue: state.queue
        ? {
            ...state.queue,
            decided: state.queue.decided.filter(
              (decision) => decision.decisionId !== decisionId
            ),
          }
        : state.queue,
    })),
  applyOptimisticDecision: (candidateId, decision) =>
    set((state) => {
      if (!state.queue) {
        return state;
      }
      const filteredPending = state.queue.pending.filter(
        (candidate) => candidate.id !== candidateId
      );
      const filteredEscalated = state.queue.escalated.filter(
        (candidate) => candidate.id !== candidateId
      );
      return {
        ...state,
        queue: {
          ...state.queue,
          pending: filteredPending,
          escalated: filteredEscalated,
          decided: dedupeDecisions([
            ...state.queue.decided,
            decision,
          ]),
        },
      };
    }),
}));

function deriveSuggestedOutcome(snapshot: ReviewQueueSnapshot): string | undefined {
  const activeCandidate = snapshot.pending[0] ?? snapshot.escalated[0];
  if (!activeCandidate) {
    return undefined;
  }
  switch (snapshot.mode) {
    case "auto_review":
      return "Suggested: Monitor auto-review";
    case "auto_submit":
      return "Suggested: Auto-submit pending";
    default:
      return "Suggested: Manual review";
  }
}

function getNextCandidateId(state: PreviewState, step: 1 | -1): string | undefined {
  if (!state.queue) return state.activeCandidateId;
  const ordered: ApplicationCandidateSummary[] = [
    ...state.queue.pending,
    ...state.queue.escalated,
  ];
  if (ordered.length === 0) {
    return undefined;
  }
  const currentIndex = state.activeCandidateId
    ? ordered.findIndex((candidate) => candidate.id === state.activeCandidateId)
    : 0;
  const normalizedIndex = currentIndex >= 0 ? currentIndex : 0;
  const nextIndex = (normalizedIndex + step + ordered.length) % ordered.length;
  return ordered[nextIndex]?.id ?? state.activeCandidateId;
}

function dedupeDecisions(decisions: SubmissionDecision[]): SubmissionDecision[] {
  const map = new Map<string, SubmissionDecision>();
  for (const decision of decisions) {
    map.set(decision.decisionId, decision);
  }
  return Array.from(map.values());
}
