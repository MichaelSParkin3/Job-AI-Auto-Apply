import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";

interface PreviewCardProps {
  screenshotUrl: string;
  summary: string;
  dryRun: boolean;
  notes?: string;
}

export function PreviewCard({ screenshotUrl, summary, dryRun, notes }: PreviewCardProps) {
  return (
    <Card className="max-w-4xl mx-auto">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Preview Submission</span>
          {dryRun && (
            <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-amber-700">
              Dry Run Mode
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-[2fr,1fr]">
        <figure className="overflow-hidden rounded-lg border bg-muted">
          <img
            src={screenshotUrl}
            alt="Preview screenshot before submission"
            className="h-full w-full object-cover"
          />
        </figure>
        <aside className="space-y-4">
          <section>
            <h2 className="text-sm font-semibold text-muted-foreground">Summary</h2>
            <p className="mt-2 text-sm leading-relaxed text-foreground/80 whitespace-pre-wrap">
              {summary}
            </p>
          </section>
          {notes && (
            <section>
              <h2 className="text-sm font-semibold text-muted-foreground">Notes</h2>
              <p className="mt-2 text-sm leading-relaxed text-foreground/80 whitespace-pre-wrap">
                {notes}
              </p>
            </section>
          )}
        </aside>
      </CardContent>
    </Card>
  );
}
