import { cn } from "../lib/utils";
import type {
  ApplicationCandidateSummary,
  ManualOverrideEntry,
  ReviewQueueSnapshot,
} from "../lib/api";

interface QueueDrawerProps {
  open: boolean;
  snapshot?: ReviewQueueSnapshot;
  activeCandidateId?: string;
  onSelectCandidate: (candidateId: string) => void;
  onToggle: (open: boolean) => void;
  overrides: ManualOverrideEntry[];
}

function formatCandidate(candidate: ApplicationCandidateSummary): string {
  const posting = candidate.posting;
  if (posting?.title && posting?.company) {
    return `${posting.title} — ${posting.company}`;
  }
  if (posting?.title) return posting.title;
  if (posting?.company) return posting.company;
  return candidate.id;
}

function formatOverride(entry: ManualOverrideEntry): string {
  const outcome = entry.decision.outcome === "needs_review" ? "Escalated" : "Approved";
  const timestamp = new Date(entry.createdAt).toLocaleTimeString();
  return `${outcome} · ${timestamp}`;
}

export function QueueDrawer({
  open,
  snapshot,
  activeCandidateId,
  onSelectCandidate,
  onToggle,
  overrides,
}: QueueDrawerProps) {
  const pending = snapshot?.pending ?? [];
  const escalated = snapshot?.escalated ?? [];
  const decided = snapshot?.decided ?? [];
  const counts = {
    pending: pending.length,
    escalated: escalated.length,
    decided: decided.length,
  };

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-40 w-80 transform border-r border-slate-200 bg-white shadow-lg transition-transform",
        open ? "translate-x-0" : "-translate-x-full"
      )}
      aria-label="Queue drawer"
    >
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Review Queue
        </h2>
        <button
          type="button"
          className="rounded-md border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-100"
          onClick={() => onToggle(false)}
          aria-label="Close queue drawer"
        >
          Hide
        </button>
      </div>
      <div className="h-full overflow-y-auto px-4 pb-6 pt-3 text-sm">
        <StatusSection
          label="Pending"
          tooltip="Candidates awaiting a manual decision"
          count={counts.pending}
          badgeClass="bg-blue-100 text-blue-700"
          items={pending}
          activeCandidateId={activeCandidateId}
          onSelectCandidate={onSelectCandidate}
        />
        <StatusSection
          label="Escalated"
          tooltip="Candidates escalated for more review"
          count={counts.escalated}
          badgeClass="bg-amber-100 text-amber-700"
          items={escalated}
          activeCandidateId={activeCandidateId}
          onSelectCandidate={onSelectCandidate}
        />
        <section className="mt-6 space-y-3">
          <header className="flex items-center justify-between">
            <p className="font-medium text-slate-700">Decided</p>
            <span
              className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700"
              aria-label={`Decided count ${counts.decided}`}
            >
              {counts.decided}
            </span>
          </header>
          <ul className="space-y-2" aria-label="Recently decided candidates">
            {decided.length === 0 && (
              <li className="text-xs text-muted-foreground">No recent decisions</li>
            )}
            {decided.map((decision) => (
              <li key={decision.decisionId} className="rounded-md border border-emerald-100 bg-emerald-50 p-2 text-xs">
                <p className="font-semibold text-emerald-700">{decision.outcome}</p>
                <p className="text-muted-foreground">
                  {new Date(decision.timestamp).toLocaleString()}
                </p>
              </li>
            ))}
          </ul>
        </section>
        {overrides.length > 0 && (
          <section className="mt-6 space-y-2" aria-label="Manual override log">
            <header className="font-medium text-slate-700">Manual Overrides</header>
            <ul className="space-y-1 text-xs text-muted-foreground">
              {overrides.map((entry) => (
                <li key={entry.decision.decisionId}>{formatOverride(entry)}</li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </aside>
  );
}

interface StatusSectionProps {
  label: string;
  tooltip: string;
  count: number;
  badgeClass: string;
  items: ApplicationCandidateSummary[];
  activeCandidateId?: string;
  onSelectCandidate: (candidateId: string) => void;
}

function StatusSection({
  label,
  tooltip,
  count,
  badgeClass,
  items,
  activeCandidateId,
  onSelectCandidate,
}: StatusSectionProps) {
  return (
    <section className="space-y-3" aria-label={`${label} candidates`}>
      <header className="flex items-center justify-between">
        <p className="font-medium text-slate-700" title={tooltip}>
          {label}
        </p>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
            badgeClass
          )}
          aria-label={`${label} count ${count}`}
        >
          {count}
        </span>
      </header>
      <ul className="space-y-2">
        {items.length === 0 && (
          <li className="text-xs text-muted-foreground">No candidates</li>
        )}
        {items.map((candidate) => (
          <li key={candidate.id}>
            <button
              type="button"
              className={cn(
                "w-full rounded-md border px-3 py-2 text-left text-xs transition hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500",
                candidate.id === activeCandidateId
                  ? "border-blue-500 bg-blue-50 text-blue-700"
                  : "border-slate-200 bg-white"
              )}
              onClick={() => onSelectCandidate(candidate.id)}
            >
              <span className="font-semibold block">{formatCandidate(candidate)}</span>
              <span className="text-muted-foreground block text-[11px]">
                {candidate.state.replace(/_/g, " ")}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
