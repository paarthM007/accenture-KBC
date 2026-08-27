"use client";

import { useState } from "react";
import type { components } from "@/types/api";
import type { ValidateResponse } from "@/lib/api";
import { titleCaseMetricId } from "@/lib/metricDisplay";

type MappingProposal = components["schemas"]["MappingProposal"];
type ParseWarning = components["schemas"]["ParseWarning"];

interface MappingConfirmationProps {
  validateResponse: ValidateResponse;
  onConfirm: (overrides: Record<string, string>) => void;
  onBack: () => void;
  isSubmitting: boolean;
}

const MATCH_TYPE_LABEL: Record<string, string> = {
  exact: "exact match",
  alias: "alias match",
  normalized: "name match",
  unresolved: "not recognised",
};

function groupWarningsByMetric(warnings: ParseWarning[]): Map<string, ParseWarning[]> {
  const groups = new Map<string, ParseWarning[]>();
  for (const warning of warnings) {
    const key = warning.metric_id ?? "__general__";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(warning);
  }
  return groups;
}

/**
 * The sleeper hit (Phase3-Plan T3.7): shows the system being careful before
 * it's confident. For unresolved columns with no candidates, the API gives
 * us nothing to build a full picker from ("No new backend endpoints" — no
 * live /metrics list to draw a dropdown from) — noted here rather than
 * faked with a hardcoded duplicate of the backend's metric config.
 */
export function MappingConfirmation({ validateResponse, onConfirm, onBack, isSubmitting }: MappingConfirmationProps) {
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const warningsByMetric = groupWarningsByMetric(validateResponse.warnings);

  const setOverride = (label: string, metricId: string) => {
    setOverrides((prev) => (metricId ? { ...prev, [label]: metricId } : Object.fromEntries(Object.entries(prev).filter(([k]) => k !== label))));
  };

  const effectivelyReady =
    validateResponse.ready ||
    (validateResponse.blocking_errors.length === 0 &&
      validateResponse.proposals.every((p) => p.match_type !== "unresolved" || overrides[p.source_label]));

  return (
    <section className="mx-auto max-w-[880px] space-y-8 py-8">
      <div>
        <h2 className="font-display text-2xl font-medium text-ink">Confirm what we found</h2>
        <p className="mt-1 text-sm text-ink-muted">
          {validateResponse.inferred.shape && <>Detected as a {validateResponse.inferred.shape} file · </>}
          {validateResponse.inferred.periods} period{validateResponse.inferred.periods === 1 ? "" : "s"}
          {validateResponse.inferred.granularity && <> · {validateResponse.inferred.granularity}</>}
          {validateResponse.inferred.revenue_band && <> · revenue band {validateResponse.inferred.revenue_band}</>}
        </p>
      </div>

      {validateResponse.blocking_errors.length > 0 && (
        <div className="rounded-sm border border-flag/40 bg-flag/[0.06] p-4">
          <p className="text-sm font-medium text-ink">We couldn&apos;t read this file</p>
          <ul className="mt-2 space-y-1">
            {validateResponse.blocking_errors.map((error, i) => (
              <li key={i} className="text-sm whitespace-pre-wrap text-ink-muted">
                {error}
              </li>
            ))}
          </ul>
        </div>
      )}

      <ul className="space-y-3">
        {validateResponse.proposals.map((proposal) => (
          <ProposalRow
            key={proposal.source_label}
            proposal={proposal}
            warnings={warningsByMetric.get(proposal.resolved_metric_id ?? "__general__") ?? []}
            override={overrides[proposal.source_label]}
            onOverride={(metricId) => setOverride(proposal.source_label, metricId)}
          />
        ))}
      </ul>

      {warningsByMetric.get("__general__") && (
        <div className="rounded-sm border border-rule bg-white/40 p-4">
          <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">General notices</p>
          <ul className="mt-2 space-y-1">
            {warningsByMetric.get("__general__")!.map((w, i) => (
              <li key={i} className="text-sm text-ink-muted">
                {w.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex items-center gap-3 border-t border-rule pt-6">
        <button
          type="button"
          onClick={onBack}
          className="rounded-sm border border-rule px-4 py-2 text-sm text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          Back
        </button>
        <button
          type="button"
          disabled={!effectivelyReady || isSubmitting}
          onClick={() => onConfirm(overrides)}
          className="rounded-sm border border-ink bg-ink px-4 py-2 text-sm font-medium text-ground disabled:cursor-not-allowed disabled:border-rule disabled:bg-rule disabled:text-ink-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          {isSubmitting ? "Analysing…" : "Analyse"}
        </button>
        {!effectivelyReady && (
          <span className="text-xs text-ink-muted">Resolve every column, or fix what&apos;s above, to continue.</span>
        )}
      </div>
    </section>
  );
}

function ProposalRow({
  proposal,
  warnings,
  override,
  onOverride,
}: {
  proposal: MappingProposal;
  warnings: ParseWarning[];
  override: string | undefined;
  onOverride: (metricId: string) => void;
}) {
  const isUnresolved = proposal.match_type === "unresolved" && !override;
  const resolvedName = override ?? proposal.resolved_metric_id;

  return (
    <li className={`rounded-sm border p-4 ${isUnresolved ? "border-flag/40 bg-flag/[0.04]" : "border-rule"}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm">
          <span className="font-medium text-ink">{proposal.source_label}</span>
          {resolvedName && (
            <>
              <span className="text-ink-muted"> → </span>
              <span className="font-medium text-ink">{titleCaseMetricId(resolvedName)}</span>
            </>
          )}
        </p>
        <span className="text-xs text-ink-muted">
          {override ? "manually mapped" : MATCH_TYPE_LABEL[proposal.match_type]}
        </span>
      </div>

      {proposal.sample_values.length > 0 && (
        <p className="data mt-1.5 text-xs text-ink-muted">Sample: {proposal.sample_values.join(", ")}</p>
      )}

      {warnings.map((w, i) => (
        <p key={i} className="mt-1.5 text-xs text-flag">
          {w.message}
        </p>
      ))}

      {proposal.match_type === "unresolved" && !override && proposal.candidates.length > 0 && (
        <label className="mt-2 flex items-center gap-2 text-xs text-ink-muted">
          Did you mean:
          <select
            className="rounded-sm border border-rule bg-white px-2 py-1 text-ink"
            defaultValue=""
            onChange={(e) => onOverride(e.target.value)}
          >
            <option value="" disabled>
              choose…
            </option>
            {proposal.candidates.map((candidate) => (
              <option key={candidate} value={candidate}>
                {titleCaseMetricId(candidate)}
              </option>
            ))}
          </select>
        </label>
      )}

      {proposal.match_type === "unresolved" && !override && proposal.candidates.length === 0 && (
        <p className="mt-2 text-xs text-ink-muted italic">
          Not recognised — this column will be excluded from analysis.
        </p>
      )}
    </li>
  );
}
