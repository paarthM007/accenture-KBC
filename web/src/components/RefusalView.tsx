import type { components } from "@/types/api";

type RefusalDetail = components["schemas"]["RefusalDetail"];
type ParseWarning = components["schemas"]["ParseWarning"];

interface RefusalViewProps {
  refusal: RefusalDetail;
  warnings: ParseWarning[];
  onReset: () => void;
}

const REFUSAL_COPY: Record<string, { headline: string; explanation: string; resolution: string }> = {
  no_metrics_submitted: {
    headline: "No data was submitted.",
    explanation: "None of the columns in your file resolved to a metric we recognise.",
    resolution: "Check the mapping confirmation step and correct any unresolved columns.",
  },
  low_data_confidence: {
    headline: "The data confidence was too low to answer this responsibly.",
    explanation: "Every submitted metric had confidence below the threshold needed for analysis.",
    resolution: "Submit values from a cleaner source, or confirm ambiguous mappings before resubmitting.",
  },
  // Our enum uses INSUFFICIENT_PERIODS; still unconfirmed against C1's exact
  // string (Phase2/3-Plan parallel actions). Handle it regardless of the
  // final name, and fall through to the default branch if it ever changes —
  // never a two-branch switch on this enum.
  insufficient_periods: {
    headline: "Not enough data to answer this responsibly.",
    explanation: "Every submitted metric has fewer periods than needed for trend analysis.",
    resolution: "With 6 months of history on any one metric, we can run a full analysis.",
  },
  contradictory_evidence: {
    headline: "The evidence was contradictory.",
    explanation: "Submitted metrics gave conflicting signals that couldn't be reconciled.",
    resolution: "Review the submitted values for consistency, then resubmit.",
  },
};

const DEFAULT_COPY = {
  headline: "Not enough evidence to answer this responsibly.",
  explanation: "The submitted data didn't meet the bar for a reliable analysis.",
  resolution: "Add more data, then resubmit.",
};

/**
 * The differentiating screen (Phase3-Plan T3.6). Must not read as an error:
 * no red, no warning triangle, no apology. This is the system working
 * correctly. A plain statement of what happened, what would resolve it, and
 * a clear path back.
 */
export function RefusalView({ refusal, warnings, onReset }: RefusalViewProps) {
  const copy = REFUSAL_COPY[refusal.reason] ?? DEFAULT_COPY;
  const explanation = refusal.message ?? copy.explanation;
  const resolution =
    (typeof refusal.suggested_resolution === "string" ? refusal.suggested_resolution : null) ?? copy.resolution;

  return (
    <section className="mx-auto max-w-prose space-y-6 py-8">
      <div>
        <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">Health score: N/A</p>
        <h2 className="font-display mt-2 text-2xl font-medium text-ink">{copy.headline}</h2>
      </div>

      <p className="text-base leading-relaxed text-ink">{explanation}</p>
      <p className="text-base leading-relaxed text-ink-muted">{resolution}</p>

      {warnings.length > 0 && (
        <div className="rounded-sm border border-rule bg-white/40 p-4">
          <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">What we saw in your file</p>
          <ul className="mt-2 space-y-1.5">
            {warnings.map((warning, i) => (
              <li key={i} className="text-sm leading-relaxed text-ink-muted">
                {warning.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      <button
        type="button"
        onClick={onReset}
        className="rounded-sm border border-ink bg-ink px-4 py-2 text-sm font-medium text-ground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        Add more data
      </button>
    </section>
  );
}
