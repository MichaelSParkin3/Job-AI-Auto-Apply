import { Edit3, Keyboard, ShieldAlert, ThumbsUp } from "lucide-react";

import { Button } from "./ui/button";

interface PreviewToolbarProps {
  onApprove: () => void;
  onEscalate: () => void;
  onEdit: () => void;
  onToggleLegend: () => void;
  isBusy: boolean;
  legendVisible: boolean;
}

export function PreviewToolbar({
  onApprove,
  onEscalate,
  onEdit,
  onToggleLegend,
  isBusy,
  legendVisible,
}: PreviewToolbarProps) {
  return (
    <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-3 rounded-lg border bg-white/70 p-4 shadow-sm">
      <p className="text-sm text-muted-foreground">
        Shortcuts: <kbd className="rounded bg-muted px-1">Shift+A</kbd> Approve • {" "}
        <kbd className="rounded bg-muted px-1">Shift+X</kbd> Escalate • {" "}
        <kbd className="rounded bg-muted px-1">J</kbd>/<kbd className="rounded bg-muted px-1">K</kbd> Navigate • {" "}
        <kbd className="rounded bg-muted px-1">Shift+?</kbd> Legend
      </p>
      <div className="flex flex-wrap gap-2">
        <Button onClick={onEscalate} variant="ghost" disabled={isBusy} className="gap-2">
          <ShieldAlert className="h-4 w-4" /> Escalate
        </Button>
        <Button onClick={onEdit} variant="secondary" disabled={isBusy} className="gap-2">
          <Edit3 className="h-4 w-4" /> Edit
        </Button>
        <Button onClick={onApprove} disabled={isBusy} className="gap-2">
          <ThumbsUp className="h-4 w-4" /> Approve
        </Button>
        <Button
          onClick={onToggleLegend}
          type="button"
          variant={legendVisible ? "default" : "outline"}
          className="gap-2"
        >
          <Keyboard className="h-4 w-4" /> Legend
        </Button>
      </div>
    </div>
  );
}
