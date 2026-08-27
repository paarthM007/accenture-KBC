import type { components } from "@/types/api";
import { titleCaseMetricId } from "@/lib/metricDisplay";

type HealthyHighlight = components["schemas"]["HealthyHighlight"];

interface HighlightsProps {
  highlights: HealthyHighlight[];
}

/**
 * Visually quieter than anomalies, but present (Phase3-Plan T3.5).
 *
 * The ltv_cac_ratio trap (exit criterion 4): a computed highlight's
 * metric_id may be absent from metric_config.yaml entirely, and there's no
 * live /metrics endpoint to resolve a real display name from either ("No
 * new backend endpoints" — Phase3-Plan). Title-cased uniformly for every
 * highlight rather than throwing, or maintaining a duplicate hardcoded copy
 * of the backend's metric config just for this cosmetic gain.
 */
export function Highlights({ highlights }: HighlightsProps) {
  if (highlights.length === 0) return null;

  return (
    <section>
      <h3 className="text-sm font-medium tracking-wide text-ink-muted uppercase">Also worth noting</h3>
      <ul className="mt-3 grid gap-2 sm:grid-cols-2">
        {highlights.map((highlight, i) => {
          const displayName = titleCaseMetricId(highlight.metric_id);
          return (
            <li key={i} className="rounded-sm border border-rule bg-white/30 p-3">
              <div className="flex items-baseline justify-between gap-2">
                <p className="text-sm font-medium text-ink">{displayName}</p>
                <span className="data text-xs text-ink-muted">{highlight.percentile.toFixed(0)}th pct</span>
              </div>
              <p className="mt-1 text-xs text-ink-muted">{highlight.note}</p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
