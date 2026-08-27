import type { components } from "@/types/api";

type ParseWarning = components["schemas"]["ParseWarning"];

interface ParseWarningsNoticeProps {
  warnings: ParseWarning[];
}

/**
 * Surfaces Phase 2's parse warnings on the results screen, not just the
 * refusal screen. Without this, a metric excluded by UNIT_SCALE_SUSPECT (or
 * any other validation-layer exclusion) simply vanishes from the report with
 * no explanation once the user is past mapping confirmation — distinct from
 * anomaly_report.metadata.skipped_metrics, which only covers unrecognised
 * metric_ids, not C2's own validation exclusions.
 */
export function ParseWarningsNotice({ warnings }: ParseWarningsNoticeProps) {
  if (warnings.length === 0) return null;

  return (
    <div className="rounded-sm border border-rule bg-white/30 p-3 text-sm">
      <span className="font-medium text-ink">About your submission: </span>
      <ul className="mt-1 space-y-1">
        {warnings.map((warning, i) => (
          <li key={i} className="text-ink-muted">
            {warning.message}
          </li>
        ))}
      </ul>
    </div>
  );
}
