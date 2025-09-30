import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";

interface ShortcutLegendProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const shortcuts = [
  { keys: "Shift + A", description: "Approve selected candidate" },
  { keys: "Shift + X", description: "Escalate back to manual review" },
  { keys: "J", description: "Next candidate" },
  { keys: "K", description: "Previous candidate" },
  { keys: "Shift + ?", description: "Toggle this shortcut legend" },
];

export function ShortcutLegend({ open, onOpenChange }: ShortcutLegendProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Keyboard Shortcuts</DialogTitle>
          <DialogDescription>
            Hold Shift for decision actions. Navigation shortcuts are available when dialogs and inputs are unfocused.
          </DialogDescription>
        </DialogHeader>
        <dl className="space-y-3 text-sm">
          {shortcuts.map((shortcut) => (
            <div key={shortcut.keys} className="flex items-start justify-between gap-4">
              <dt className="font-semibold text-slate-700">{shortcut.keys}</dt>
              <dd className="text-muted-foreground">{shortcut.description}</dd>
            </div>
          ))}
        </dl>
      </DialogContent>
    </Dialog>
  );
}
