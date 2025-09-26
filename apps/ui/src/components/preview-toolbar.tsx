import { Edit3, ShieldAlert, ThumbsUp } from "lucide-react";
import { Button } from "./ui/button";

interface PreviewToolbarProps {
  onApprove: () => void;
  onAbort: () => void;
  onEdit: () => void;
  isBusy: boolean;
}

export function PreviewToolbar({ onApprove, onAbort, onEdit, isBusy }: PreviewToolbarProps) {
  return (
    <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-3 rounded-lg border bg-white/70 p-4 shadow-sm">
      <p className="text-sm text-muted-foreground">
        Shortcuts: <kbd className="rounded bg-muted px-1">A</kbd> Approve • {" "}
        <kbd className="rounded bg-muted px-1">E</kbd> Edit • {" "}
        <kbd className="rounded bg-muted px-1">Esc</kbd> Abort
      </p>
      <div className="flex flex-wrap gap-2">
        <Button onClick={onAbort} variant="ghost" disabled={isBusy} className="gap-2">
          <ShieldAlert className="h-4 w-4" /> Abort
        </Button>
        <Button onClick={onEdit} variant="secondary" disabled={isBusy} className="gap-2">
          <Edit3 className="h-4 w-4" /> Edit
        </Button>
        <Button onClick={onApprove} disabled={isBusy} className="gap-2">
          <ThumbsUp className="h-4 w-4" /> Approve
        </Button>
      </div>
    </div>
  );
}
