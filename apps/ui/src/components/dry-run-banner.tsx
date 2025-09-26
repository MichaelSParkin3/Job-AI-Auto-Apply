interface DryRunBannerProps {
  isDryRun: boolean;
}

export function DryRunBanner({ isDryRun }: DryRunBannerProps) {
  if (!isDryRun) return null;
  return (
    <div className="w-full bg-amber-100 py-2 text-center text-sm font-medium text-amber-800 shadow">
      Dry Run Mode is active – no submissions will be sent.
    </div>
  );
}
