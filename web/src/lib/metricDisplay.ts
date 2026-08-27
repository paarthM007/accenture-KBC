/**
 * Fallback display name for a metric_id that isn't in metric_config.yaml —
 * computed highlights like ltv_cac_ratio carry such an id by design
 * (Contract §5.2, Phase0's healthy fixture is the regression test for it).
 * Any display-name lookup must fall back to title-casing rather than
 * throwing (Phase3-Plan T3.5, exit criterion 4).
 */
export function titleCaseMetricId(metricId: string): string {
  return metricId
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
