import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";

import type { PreviewMetadata } from "../store/preview-store";

function formatProfileDisplay(metadata?: PreviewMetadata): string {
  const label = metadata?.profileLabel;
  if (label && label.trim().length > 0) {
    return label;
  }
  const profileId = metadata?.profileId;
  if (!profileId) {
    return "Demo profile";
  }
  const parts = profileId
    .split(/[-_\s]+/)
    .filter((part) => part.length > 0)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1));
  if (parts.length === 0) {
    return "Demo profile";
  }
  const formatted = parts.join(" ");
  if (formatted.toLowerCase().endsWith("profile")) {
    return formatted;
  }
  return `${formatted} profile`;
}

interface PreviewCardProps {
  screenshotUrl: string;
  summary: string;
  dryRun: boolean;
  notes?: string;
  decision?: string;
  decidedAt?: string;
  metadata?: PreviewMetadata;
}

export function PreviewCard({
  screenshotUrl,
  summary,
  dryRun,
  notes,
  decision,
  decidedAt,
  metadata,
}: PreviewCardProps) {
  const startedAtLabel = metadata?.startedAt
    ? new Date(metadata.startedAt).toLocaleString()
    : "Not recorded";
  const decisionLabel = decision
    ? decision.charAt(0).toUpperCase() + decision.slice(1)
    : "Pending";
  const decidedAtLabel = decidedAt
    ? new Date(decidedAt).toLocaleString()
    : decision ? "Pending" : undefined;

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
            <section>
              <h2 className="text-sm font-semibold text-muted-foreground">Run Metadata</h2>
              <dl className="mt-2 grid gap-x-4 gap-y-2 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-muted-foreground/80">Profile</dt>
                  <dd className="text-foreground/80">{formatProfileDisplay(metadata)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground/80">Started</dt>
                  <dd className="text-foreground/80">{startedAtLabel}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground/80">Decision</dt>
                  <dd className="text-foreground/80">{decisionLabel}</dd>
                </div>
                {decidedAtLabel && (
                  <div>
                    <dt className="text-muted-foreground/80">Decided</dt>
                    <dd className="text-foreground/80">{decidedAtLabel}</dd>
                  </div>
                )}
                {typeof metadata?.limit !== "undefined" && (
                  <div>
                    <dt className="text-muted-foreground/80">Limit</dt>
                    <dd className="text-foreground/80">{metadata.limit}</dd>
                  </div>
                )}
              </dl>
            </section>
          </aside>
        </CardContent>
      </Card>
    );
  }
