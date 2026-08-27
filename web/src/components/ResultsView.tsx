"use client";

import { useState } from "react";
import type { ApiResponse } from "@/lib/api";
import { HealthScore } from "./HealthScore";
import { DegradedBanner } from "./DegradedBanner";
import { Narrative } from "./Narrative";
import { AnomalyCard } from "./AnomalyCard";
import { PrescriptionCard } from "./PrescriptionCard";
import { MatchedCases } from "./MatchedCases";
import { Highlights } from "./Highlights";
import { SkippedMetricsNotice } from "./SkippedMetricsNotice";
import { ParseWarningsNotice } from "./ParseWarningsNotice";
import { RefusalView } from "./RefusalView";

interface ResultsViewProps {
  response: ApiResponse;
  onReset: () => void;
}

/**
 * Top to bottom (Phase3-Plan T3.3): health score -> degraded banner
 * (conditional) -> narrative -> anomalies -> highlights -> skipped-metrics
 * notice. A report you read top to bottom, not a grid dashboard.
 */
export function ResultsView({ response, onReset }: ResultsViewProps) {
  const [highlightedId, setHighlightedId] = useState<string | null>(null);

  if (!response.result) {
    // status: "failed" — no result to render. Callers should route this to
    // an error message before reaching ResultsView, but stay defensive.
    return (
      <p className="text-sm text-ink-muted">
        {response.error ? `Something went wrong (${response.error}).` : "No result available."}
      </p>
    );
  }

  const { anomaly_report, prescriptions, matched_cases, narrative, metadata } = response.result;

  if (response.status === "refused" && anomaly_report.refusal) {
    return <RefusalView refusal={anomaly_report.refusal} warnings={response.warnings} onReset={onReset} />;
  }

  const sortedAnomalies = [...anomaly_report.anomalies].sort((a, b) => b.severity_score - a.severity_score);
  const prescriptionsByAnomalyId = new Map(prescriptions.map((p) => [p.anomaly_id, p]));

  return (
    <div className="mx-auto max-w-[880px] space-y-10 py-8">
      <header className="space-y-4">
        <HealthScore score={anomaly_report.overall_health_score ?? null} />
        {metadata.degraded && <DegradedBanner degradedReason={metadata.degraded_reason} />}
        <SkippedMetricsNotice skippedMetrics={anomaly_report.metadata.skipped_metrics} />
        <ParseWarningsNotice warnings={response.warnings} />
      </header>

      {narrative && (
        <section>
          <h2 className="text-sm font-medium tracking-wide text-ink-muted uppercase">Narrative</h2>
          <div className="mt-3">
            <Narrative narrative={narrative} />
          </div>
        </section>
      )}

      {sortedAnomalies.length > 0 && (
        <section>
          <h2 className="text-sm font-medium tracking-wide text-ink-muted uppercase">
            Anomalies ({sortedAnomalies.length})
          </h2>
          <div className="mt-3 space-y-4">
            {sortedAnomalies.map((anomaly, i) => (
              <div
                key={anomaly.anomaly_id}
                className="motion-safe:animate-[fade-in_300ms_ease-out_backwards]"
                style={{ animationDelay: `${i * 40}ms` }}
              >
                <AnomalyCard anomaly={anomaly} highlightedId={highlightedId} onHighlight={setHighlightedId} />
                {prescriptionsByAnomalyId.has(anomaly.anomaly_id) && (
                  <div className="mt-2 rounded-sm border border-rule border-t-0 p-5">
                    <PrescriptionCard prescription={prescriptionsByAnomalyId.get(anomaly.anomaly_id)!} />
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {matched_cases.length > 0 && (
        <section>
          <h2 className="text-sm font-medium tracking-wide text-ink-muted uppercase">Similar cases</h2>
          <div className="mt-3">
            <MatchedCases cases={matched_cases} />
          </div>
        </section>
      )}

      <Highlights highlights={anomaly_report.non_anomalous_highlights} />
    </div>
  );
}
