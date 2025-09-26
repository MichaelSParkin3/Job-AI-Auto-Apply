import * as React from "react";

import { abortRun, approveRun, createPreviewRun, editRun } from "./lib/api";
import { DryRunBanner } from "./components/dry-run-banner";
import { EditDialog } from "./components/edit-dialog";
import { PreviewCard } from "./components/preview-card";
import { PreviewToolbar } from "./components/preview-toolbar";
import { Toaster, toast } from "./components/ui/use-toast";
import { usePreviewStore } from "./store/preview-store";

const useKeyboardShortcuts = (
  handlers: Record<string, () => void>,
  enabled: boolean
) => {
  React.useEffect(() => {
    if (!enabled) return;
    const listener = (event: KeyboardEvent) => {
      const key = event.key.toLowerCase();
      if (handlers[key]) {
        event.preventDefault();
        handlers[key]!();
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [handlers, enabled]);
};

const App: React.FC = () => {
  const { runId, status, preview, dryRun, set, message } = usePreviewStore();
  const [editOpen, setEditOpen] = React.useState(false);
  const isBusy = status === "loading" || status === "editing";

  React.useEffect(() => {
    let mounted = true;
    const bootstrap = async () => {
      set({ status: "loading", message: undefined });
      try {
        const data = await createPreviewRun();
        if (!mounted) return;
        set({
          runId: data.runId,
          status: "ready",
          dryRun: data.dryRun,
          preview: data.preview,
        });
      } catch (error) {
        const description = error instanceof Error ? error.message : String(error);
        set({ status: "error", message: description });
      }
    };
    bootstrap();
    return () => {
      mounted = false;
    };
  }, [set]);

  const handleApprove = React.useCallback(async () => {
    if (!runId) return;
    set({ status: "loading" });
    try {
      await approveRun(runId);
      set({ status: "approved" });
      toast({
        title: "Preview approved",
        description: "Submission will remain in dry-run mode.",
      });
    } catch (error) {
      const description = error instanceof Error ? error.message : String(error);
      set({ status: "error", message: description });
      toast({
        title: "Failed to approve",
        description,
        variant: "destructive",
      });
    }
  }, [runId, set]);

  const handleAbort = React.useCallback(async () => {
    if (!runId) return;
    set({ status: "loading" });
    try {
      await abortRun(runId);
      set({ status: "aborted" });
      toast({
        title: "Preview aborted",
        description: "Dry run halted without sending a submission.",
      });
    } catch (error) {
      const description = error instanceof Error ? error.message : String(error);
      set({ status: "error", message: description });
      toast({
        title: "Failed to abort",
        description,
        variant: "destructive",
      });
    }
  }, [runId, set]);

  const handleEditSubmit = React.useCallback(
    async (text: string) => {
      if (!runId) return;
      set({ status: "editing" });
      try {
        await editRun(runId, text);
        const updatedPreview = preview ? { ...preview, edits: text } : preview;
        set({ status: "editing", preview: updatedPreview });
        toast({
          title: "Edit captured",
          description: "Preview updated with your manual note.",
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
    [preview, runId, set]
  );

  useKeyboardShortcuts(
    {
      a: handleApprove,
      e: () => setEditOpen(true),
      escape: handleAbort,
    },
    status === "ready" || status === "editing"
  );

  return (
    <div className="min-h-screen bg-slate-100">
      <DryRunBanner isDryRun={dryRun} />
      <main className="mx-auto grid max-w-5xl gap-6 px-4 py-10">
        <header className="space-y-2 text-center">
          <h1 className="text-3xl font-bold tracking-tight">Review & Approve</h1>
          <p className="text-muted-foreground">
            Inspect the captured screenshot, request quick edits, or approve the submission before it ships.
          </p>
        </header>
        {status === "error" && (
          <div className="rounded-md border border-destructive bg-destructive/10 p-4 text-sm text-destructive">
            {message ?? "An unexpected error occurred."}
          </div>
        )}
        {(status === "ready" || status === "editing" || status === "approved" || status === "aborted") && preview && (
          <>
            <PreviewToolbar
              onApprove={handleApprove}
              onAbort={handleAbort}
              onEdit={() => setEditOpen(true)}
              isBusy={isBusy}
            />
            <PreviewCard
              screenshotUrl={preview.screenshotUrl}
              summary={preview.summary}
              notes={preview.notes ?? preview.edits}
              dryRun={dryRun}
            />
          </>
        )}
        {status === "loading" && (
          <div className="flex items-center justify-center py-20 text-sm text-muted-foreground">
            Preparing demo preview…
          </div>
        )}
        {status === "approved" && (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700">
            Preview approved. Submission would proceed if not in dry run.
          </div>
        )}
        {status === "aborted" && (
          <div className="rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700">
            Preview aborted. No action was taken.
          </div>
        )}
      </main>
      <EditDialog open={editOpen} onOpenChange={setEditOpen} onSubmit={handleEditSubmit} />
      <Toaster />
    </div>
  );
};

export default App;
