/**
 * Client-side preview only — mirrors config/metric_config.yaml's
 * revenue_bands (O12: lower bound inclusive, upper exclusive) so the form
 * can show the derived band live as the user types (Phase3-Plan T3.8). The
 * backend recomputes this authoritatively; this is cosmetic, not a source
 * of truth, and there's no live endpoint to fetch it from ("No new backend
 * endpoints").
 */
export function previewRevenueBand(annualRevenue: number | null): string | null {
  if (annualRevenue === null || Number.isNaN(annualRevenue)) return null;
  if (annualRevenue < 1_000_000) return "<1M";
  if (annualRevenue < 10_000_000) return "1M-10M";
  if (annualRevenue < 100_000_000) return "10M-100M";
  return ">100M";
}
