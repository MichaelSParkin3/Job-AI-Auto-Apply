import * as React from "react";

import {
  fetchCurrentRun,
  fetchQueueSnapshot,
  submitQueueDecision,
  overrideCandidateMode,
  editRun,
  type ReviewQueueSnapshot,
  type SubmissionDecision,
  type ApplicationCandidateSummary,
} from "./lib/api";
import { DryRunBanner } from "./components/dry-run-banner";
import { EditDialog } from "./components/edit-dialog";
import { PreviewCard } from "./components/preview-card";
import { PreviewToolbar } from "./components/preview-toolbar";
import { QueueDrawer } from "./components/queue-drawer";
import { ShortcutLegend } from "./components/shortcut-legend";
import { Toaster, toast } from "./components/ui/use-toast";
import { cn } from "./lib/utils";
import { usePreviewStore } from "./store/preview-store";
import type { PreviewStatus } from "./store/preview-store";

const POLL_INTERVAL_MS = 15000;

const useKeyboardShortcuts = (
  enabled: boolean,
  {
    onApprove,
    onEscalate,
    onNext,
    onPrevious,
    onToggleLegend,
    onOpenEdit,
  }: {
    onApprove: () => void;
    onEscalate: () => void;
    onNext: () => void;
    onPrevious: () => void;
    onToggleLegend: () => void;
    onOpenEdit?: () => void;
  }
) => {
  React.useEffect(() => {
    if (!enabled) return;
    const listener = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return;
      if (shouldIgnoreEvent(event)) return;
      const key = event.key.toLowerCase();
      if (event.shiftKey && key === "a") {
        event.preventDefault();
        onApprove();
        return;
      }
      if (event.shiftKey && key === "x") {
        event.preventDefault();
        onEscalate();
        return;
      }
      if (event.shiftKey && event.key === "?") {
        event.preventDefault();
        onToggleLegend();
        return;
      }
      if (!event.shiftKey && key === "j") {
        event.preventDefault();
        onNext();
        return;
      }
      if (!event.shiftKey && key === "k") {
        event.preventDefault();
        onPrevious();
        return;
      }
      if (!event.shiftKey && key === "e" && onOpenEdit) {
        event.preventDefault();
        onOpenEdit();
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [enabled, onApprove, onEscalate, onNext, onPrevious, onToggleLegend, onOpenEdit]);
};

const App: React.FC = () => {
  const {
    runId,
    status,
    preview,
    dryRun,
    metadata,
    set,
    message,
    queue,
    setQueueSnapshot,
    activeCandidateId,
    selectCandidate,
    selectNextCandidate,
    selectPreviousCandidate,
    drawerOpen,
    setDrawerOpen,
    legendVisible,
    setLegendVisible,
    decisionBusy,
    setDecisionBusy,
    decisionError,
    setDecisionError,
    overrides,
    addOverride,
    removeOverride,
    suggestedOutcome,
    applyOptimisticDecision,
    setCandidateMode,
  } = usePreviewStore();
  const [editOpen, setEditOpen] = React.useState(false);
  const [overrideBusy, setOverrideBusy] = React.useState(false);
  const isLoading = status === "loading" || status === "editing";
  const isBusy = isLoading || decisionBusy;

  const toPreviewStatus = React.useCallback(
    (value: string | undefined, fallback: PreviewStatus): PreviewStatus => {
      if (!value) return fallback;
      if (value === "review") return "ready";
      return value as PreviewStatus;
    },
    []
  );

  const refreshQueue = React.useCallback(async () => {
    if (!runId) return;
    try {
      const snapshot = await fetchQueueSnapshot(runId);
      setQueueSnapshot(snapshot);
      setDecisionError(undefined);
    } catch (error) {
      const description = error instanceof Error ? error.message : String(error);
      setDecisionError(description);
    }
  }, [runId, setQueueSnapshot, setDecisionError]);

  React.useEffect(() => {
    let mounted = true;
    let attempts = 0;
    const bootstrap = async () => {
      if (!mounted) return;
      if (attempts === 0) set({ status: "loading", message: undefined });
      try {
        const data = await fetchCurrentRun();
        if (!mounted) return;
        set({
          runId: data.runId,
          status: toPreviewStatus(data.status, "ready"),
          dryRun: data.dryRun,
          preview: data.preview,
          metadata: data.metadata,
        });
      } catch (error) {
        if (!mounted) return;
        attempts += 1;
        // Some servers warm the run state lazily; retry a few times before surfacing.
        if (attempts <= 8) {
          window.setTimeout(bootstrap, Math.min(500 * attempts, 2000));
        } else {
          const description = error instanceof Error ? error.message : String(error);
          set({ status: "error", message: description });
        }
      }
    };
    bootstrap();
    return () => {
      mounted = false;
    };
  }, [set, toPreviewStatus]);

  React.useEffect(() => {
    if (!runId) return;
    refreshQueue();
  }, [runId, refreshQueue]);

  React.useEffect(() => {
    if (!runId) return;
    const interval = window.setInterval(() => {
      refreshQueue();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [runId, refreshQueue]);

  const handleDecision = React.useCallback(
    async (outcome: "approve" | "needs_review") => {
      if (!runId || !queue || decisionBusy) return;
      const candidate =
        (activeCandidateId &&
          getActiveCandidate(queue, activeCandidateId)) ??
        queue.pending[0] ??
        queue.escalated[0];
      if (!candidate) {
        toast({
          title: "No candidate available",
          description: "Select a candidate from the queue to record a decision.",
          variant: "destructive",
        });
        return;
      }
      const previousSnapshot = cloneSnapshot(queue);
      const previousActiveId = activeCandidateId;
      const decision: SubmissionDecision = {
        decisionId: generateDecisionId(),
        candidateId: candidate.id,
        outcome,
        mode: "human",
        confidence: outcome === "approve" ? 0.9 : 0.5,
        timestamp: new Date().toISOString(),
      };
      setDecisionBusy(true);
      setDecisionError(undefined);
      applyOptimisticDecision(candidate.id, decision);
      addOverride({ decision, createdAt: decision.timestamp });
      selectNextCandidate();
      try {
        await submitQueueDecision(runId, decision);
        toast({
          title: outcome === "approve" ? "Candidate approved" : "Candidate escalated",
          description:
            candidate.posting?.title ?? "Decision recorded for queued candidate.",
        });
        await refreshQueue();
      } catch (error) {
        const description = error instanceof Error ? error.message : String(error);
        removeOverride(decision.decisionId);
        set({
          queue: previousSnapshot ?? queue,
          activeCandidateId: previousActiveId,
        });
        setDecisionError(description);
        toast({
          title: "Failed to record decision",
          description,
          variant: "destructive",
        });
      } finally {
        setDecisionBusy(false);
      }
    },
    [
      runId,
      queue,
      decisionBusy,
      activeCandidateId,
      setDecisionBusy,
      setDecisionError,
      applyOptimisticDecision,
      addOverride,
      selectNextCandidate,
      refreshQueue,
      removeOverride,
      set,
    ]
  );

  const handleApprove = React.useCallback(() => handleDecision("approve"), [handleDecision]);

  const handleEscalate = React.useCallback(
    () => handleDecision("needs_review"),
    [handleDecision]
  );

  const handleEditSubmit = React.useCallback(
    async (text: string) => {
      if (!runId) return;
      set({ status: "editing", message: undefined });
      try {
        const result = await editRun(runId, text);
        const updatedPreview =
          result.preview ?? (preview ? { ...preview, edits: text } : preview);
        set({
          status: toPreviewStatus(result.status, "ready"),
          preview: updatedPreview,
          metadata: result.metadata ?? metadata,
        });
        toast({
          title: "Edit captured",
          description: result.message ?? "Preview updated with your manual note.",
        });
      } catch (error) {
        const description = error instanceof Error ? error.message : String(error);
        set({ status: "error", message: description });
        toast({
          title: "Failed to submit edit",
          description,
          variant: "destructive",
        });
      } finally {
        setEditOpen(false);
      }
    },
    [metadata, preview, runId, set, toPreviewStatus]
  );

  const shortcutsEnabled =
    (status === "ready" || status === "editing") && !legendVisible && !editOpen;

  useKeyboardShortcuts(shortcutsEnabled, {
    onApprove: handleApprove,
    onEscalate: handleEscalate,
    onNext: selectNextCandidate,
    onPrevious: selectPreviousCandidate,
    onToggleLegend: () => setLegendVisible(!legendVisible),
    onOpenEdit: () => setEditOpen(true),
  });

  const activeCandidate = React.useMemo(
    () => (queue ? getActiveCandidate(queue, activeCandidateId) : undefined),
    [queue, activeCandidateId]
  );

  const handleTakeBack = React.useCallback(async () => {
    if (!runId || !activeCandidate || overrideBusy) return;
    const previousSnapshot = cloneSnapshot(queue);
    const previousActiveId = activeCandidateId;
    setCandidateMode(activeCandidate.id, "human");
    setOverrideBusy(true);
    try {
      const snapshot = await overrideCandidateMode(
        runId,
        activeCandidate.id,
        "human",
        "take_back"
      );
      setQueueSnapshot(snapshot);
      toast({
        title: "Candidate reassigned to manual review",
        description:
          activeCandidate.posting?.title ?? "Candidate moved back to human lane.",
      });
    } catch (error) {
      const description = error instanceof Error ? error.message : String(error);
      if (previousSnapshot) {
        set({ queue: previousSnapshot, activeCandidateId: previousActiveId });
      }
      toast({
        title: "Failed to take back candidate",
        description,
        variant: "destructive",
      });
    } finally {
      setOverrideBusy(false);
    }
  }, [
    activeCandidate,
    activeCandidateId,
    overrideBusy,
    queue,
    runId,
    set,
    setCandidateMode,
    setQueueSnapshot,
  ]);

  const effectiveMessage = message ?? decisionError;

  return (
    <div className={cn("min-h-screen bg-slate-100", drawerOpen && "sm:pl-80")}>
      <QueueDrawer
        open={drawerOpen}
        snapshot={queue}
        activeCandidateId={activeCandidateId}
        onSelectCandidate={(candidateId) => selectCandidate(candidateId)}
        onToggle={setDrawerOpen}
        overrides={overrides}
      />
      {!drawerOpen && (
        <button
          type="button"
          className="fixed left-4 top-24 z-30 rounded-md border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 shadow"
          onClick={() => setDrawerOpen(true)}
        >
          Show Queue
        </button>
      )}
      <DryRunBanner isDryRun={dryRun} />
      <main className="mx-auto grid max-w-5xl gap-6 px-4 py-10">
        <header className="space-y-2 text-center">
          <h1 className="text-3xl font-bold tracking-tight">Review &amp; Decide</h1>
          <p className="text-muted-foreground">
            Navigate the review queue, approve or escalate candidates, and keep manual overrides in sync with the API state.
          </p>
        </header>
        {effectiveMessage && (
          <div className="rounded-md border border-destructive bg-destructive/10 p-4 text-sm text-destructive">
            {effectiveMessage}
          </div>
        )}
        {(status === "ready" || status === "editing" || status === "approved") && preview && (
          <>
            {activeCandidate?.assignedMode === "ai" && (
              <div className="rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold">AI review in progress</p>
                    <p className="text-amber-700/80">
                      This candidate is currently handled by the AI lane. Take back control to
                      continue manual review.
                    </p>
                  </div>
                  <button
                    type="button"
                    className="rounded-md border border-amber-300 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-wide text-amber-800 transition hover:bg-amber-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
                    onClick={handleTakeBack}
                    disabled={overrideBusy}
                  >
                    {overrideBusy ? "Reassigning…" : "Take Back"}
                  </button>
                </div>
              </div>
            )}
            <PreviewToolbar
              onApprove={handleApprove}
              onEscalate={handleEscalate}
              onEdit={() => setEditOpen(true)}
              onToggleLegend={() => setLegendVisible(!legendVisible)}
              isBusy={isBusy}
              legendVisible={legendVisible}
            />
            <PreviewCard
              screenshotUrl={preview.screenshotUrl}
              summary={preview.summary}
              notes={preview.notes ?? preview.edits}
              dryRun={dryRun}
              decision={preview.decision}
              decidedAt={preview.decidedAt}
              metadata={metadata}
              suggestedOutcome={suggestedOutcome}
              overrides={overrides}
              candidate={activeCandidate}
            />
          </>
        )}
        {status === "loading" && (
          <div className="flex items-center justify-center py-20 text-sm text-muted-foreground">
            Preparing queue preview…
          </div>
        )}
        {status === "approved" && (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700">
            Latest decision recorded. Queue will continue refreshing.
          </div>
        )}
      </main>
      <ShortcutLegend open={legendVisible} onOpenChange={setLegendVisible} />
      <EditDialog open={editOpen} onOpenChange={setEditOpen} onSubmit={handleEditSubmit} />
      <Toaster />
    </div>
  );
};

export default App;

function shouldIgnoreEvent(event: KeyboardEvent): boolean {
  const target = event.target as HTMLElement | null;
  if (!target) return false;
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    target.isContentEditable
  );
}

function generateDecisionId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `decision_${Math.random().toString(36).slice(2, 10)}`;
}

function getActiveCandidate(
  snapshot: ReviewQueueSnapshot,
  candidateId: string | undefined
): ApplicationCandidateSummary | undefined {
  if (!candidateId) {
    return snapshot.pending[0] ?? snapshot.escalated[0];
  }
  return (
    snapshot.pending.find((candidate) => candidate.id === candidateId) ??
    snapshot.escalated.find((candidate) => candidate.id === candidateId)
  );
}

function cloneSnapshot(
  snapshot: ReviewQueueSnapshot | undefined
): ReviewQueueSnapshot | undefined {
  if (!snapshot) return undefined;
  return {
    ...snapshot,
    pending: [...snapshot.pending],
    escalated: [...snapshot.escalated],
    decided: [...snapshot.decided],
  };
}
