import { titleCaseMetricId } from "@/lib/metricDisplay";

interface SkippedMetricsNoticeProps {
  skippedMetrics: string[];
}

/**
 * A quiet notice listing unrecognised metric_ids (Phase3-Plan T3.6). The
 * slot for filtered_metrics (O11 — "we looked at burn rate and concluded
 * the movement was noise") stays ready but empty until C1 ships that field.
 */
export function SkippedMetricsNotice({ skippedMetrics }: SkippedMetricsNoticeProps) {
  if (skippedMetrics.length === 0) return null;

  return (
    <div className="rounded-sm border border-rule bg-white/30 p-3 text-sm text-ink-muted">
      <span className="font-medium text-ink">Not recognised: </span>
      {skippedMetrics.map(titleCaseMetricId).join(", ")}
    </div>
  );
}
