import type { components } from "@/types/api";
import { SeverityConfidenceBar } from "./SeverityConfidenceBar";
import { Sparkline } from "./Sparkline";

type Anomaly = components["schemas"]["Anomaly"];

interface AnomalyCardProps {
  anomaly: Anomaly;
  highlightedId: string | null;
  onHighlight: (id: string | null) => void;
}

const DIRECTION_LABEL: Record<string, string> = {
  above_expected: "above expected",
  below_expected: "below expected",
};

/**
 * The most important component in the app (Phase3-Plan T3.4). Carries the
 * signature severity/confidence marker plus every null-handling case that
 * WILL occur on real data.
 */
export function AnomalyCard({ anomaly, highlightedId, onHighlight }: AnomalyCardProps) {
  const isSelf = highlightedId === anomaly.anomaly_id;
  const isPartner = highlightedId !== null && anomaly.correlated_anomalies.includes(highlightedId);
  const isHighlighted = isSelf || isPartner;

  // deviation.direction: "as_expected" semantics are still open (Contract
  // O13) — it can only appear on an Anomaly, but an anomaly deviated by
  // definition, so seeing it at all is worth a console note. Render
  // neutrally either way; never crash on the unhandled/unrecognised case.
  let directionLabel = DIRECTION_LABEL[anomaly.deviation.direction];
  if (directionLabel === undefined) {
    console.warn(`AnomalyCard: unhandled deviation.direction "${anomaly.deviation.direction}" (O13 still open)`);
    directionLabel = "relative to expected";
  }

  const delta = anomaly.deviation.observed_current - anomaly.deviation.expected_value;
  const hasTrendData = anomaly.trend.values_over_time !== null && anomaly.trend.values_over_time !== undefined;

  return (
    <article
      id={`anomaly-${anomaly.anomaly_id}`}
      className={`rounded-sm border p-5 transition-colors duration-150 motion-reduce:transition-none ${
        isHighlighted ? "border-accent bg-accent/[0.04]" : "border-rule bg-white/40"
      }`}
      onMouseEnter={() => onHighlight(anomaly.anomaly_id)}
      onMouseLeave={() => onHighlight(null)}
    >
      <header className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">{anomaly.category}</p>
          <h3 className="font-display text-lg font-medium text-ink">{anomaly.metric_display_name}</h3>
        </div>
        <span className="shrink-0 text-xs font-medium tracking-wide text-ink-muted uppercase">
          {anomaly.severity_label}
        </span>
      </header>

      <div className="mt-4">
        <SeverityConfidenceBar severityScore={anomaly.severity_score} noiseConfidence={anomaly.noise_confidence} />
      </div>

      <div className="data mt-4 grid grid-cols-3 gap-3 text-sm">
        <div>
          <p className="text-xs text-ink-muted">Observed</p>
          <p className="text-ink">{anomaly.deviation.observed_current.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-xs text-ink-muted">Expected</p>
          <p className="text-ink">{anomaly.deviation.expected_value.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-xs text-ink-muted">Delta</p>
          <p className="text-ink">
            {delta >= 0 ? "+" : ""}
            {delta.toFixed(2)} <span className="text-ink-muted">({directionLabel})</span>
          </p>
        </div>
      </div>

      <div className="mt-4 flex items-end justify-between gap-4">
        <div>
          {hasTrendData ? (
            <Sparkline points={anomaly.trend.values_over_time!} />
          ) : (
            <p className="text-xs text-ink-muted italic">trend needs 6+ periods</p>
          )}
          {/* slope / acceleration / periods_deviating: omit the row entirely when null, don't render a blank. */}
          {anomaly.trend.slope !== null && anomaly.trend.slope !== undefined && (
            <p className="data mt-1 text-xs text-ink-muted">
              slope {anomaly.trend.slope >= 0 ? "+" : ""}
              {anomaly.trend.slope.toFixed(3)}/period
              {anomaly.trend.periods_deviating !== null && anomaly.trend.periods_deviating !== undefined && (
                <> · {anomaly.trend.periods_deviating} periods deviating</>
              )}
            </p>
          )}
        </div>
        <p className="text-xs text-ink-muted capitalize">{anomaly.trend.direction}</p>
      </div>

      {anomaly.context_tags.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {anomaly.context_tags.map((tag) => (
            <span
              key={tag}
              className="rounded-sm border border-rule px-1.5 py-0.5 text-[11px] text-ink-muted"
            >
              {tag.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      )}

      {anomaly.correlated_anomalies.length > 0 && (
        <p className="mt-3 text-xs text-ink-muted">
          Correlated with{" "}
          {anomaly.correlated_anomalies.map((id, i) => (
            <span key={id}>
              {i > 0 && ", "}
              <button
                type="button"
                className="cursor-pointer underline decoration-dotted underline-offset-2 hover:text-accent"
                onMouseEnter={() => onHighlight(id)}
                onFocus={() => onHighlight(id)}
                onClick={() => document.getElementById(`anomaly-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" })}
              >
                {id}
              </button>
            </span>
          ))}
        </p>
      )}
    </article>
  );
}
