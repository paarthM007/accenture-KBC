/**
 * The largest element on the page (Phase3-Plan T3.3). The null case is not a
 * footnote: Contract §7.1 is explicit that a refusal must never render
 * "50/100" — this is the highest-traffic path in the refusal demo.
 */
interface HealthScoreProps {
  score: number | null;
}

export function HealthScore({ score }: HealthScoreProps) {
  if (score === null) {
    return (
      <div>
        <div className="data font-display text-6xl font-medium tracking-tight text-ink-muted sm:text-7xl">N/A</div>
        <p className="mt-2 text-sm text-ink-muted">not scored — insufficient data</p>
      </div>
    );
  }

  return (
    <div>
      <div className="data font-display text-6xl font-medium tracking-tight text-ink sm:text-7xl">
        {score.toFixed(1)}
        <span className="text-2xl font-normal text-ink-muted sm:text-3xl"> / 100</span>
      </div>
      <p className="mt-2 text-sm text-ink-muted">overall health score</p>
    </div>
  );
}
