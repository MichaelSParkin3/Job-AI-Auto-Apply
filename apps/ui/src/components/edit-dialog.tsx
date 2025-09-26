import * as React from "react";

import { Button } from "./ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "./ui/dialog";

interface EditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (text: string) => void;
}

export function EditDialog({ open, onOpenChange, onSubmit }: EditDialogProps) {
  const [text, setText] = React.useState("");

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit(text.trim());
    setText("");
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Request Edit</DialogTitle>
          <DialogDescription>
            Provide quick edits for the summary before retrying submission.
          </DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={handleSubmit}>
          <textarea
            className="min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            placeholder="Add quick edit notes to apply before re-running..."
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button type="button" variant="ghost">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={!text.trim()}>
              Submit Edit
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
