"""wrap_bare_report() (Phase1-Plan T1.2) — the shared fallback.

Two very different situations produce the same shape:

  - C1 returned a refusal -> C2 short-circuits, never calls C3
        wrap_bare_report(report, degraded=False, reason=None)
  - C3 raised or timed out -> we still have anomalies
        wrap_bare_report(report, degraded=True, reason="c3_failed")

Because both produce a valid EnrichedReport, the frontend has exactly one
code path: it always reads result.anomaly_report and treats
prescriptions/narrative as optional. No branching on whether C3 ran, no
null-checking `result` itself. Do not quietly undo this.
"""

from typing import Optional

from api.models.shared import AnomalyReport, EnrichedReport, EnrichmentMetadata


def wrap_bare_report(
    report: AnomalyReport, *, degraded: bool, reason: Optional[str] = None
) -> EnrichedReport:
    return EnrichedReport(
        anomaly_report=report,  # nested verbatim — Contract §6.1
        prescriptions=[],
        anomaly_clusters=[],
        matched_cases=[],
        narrative=None,
        metadata=EnrichmentMetadata(
            processing_time_ms=0,
            cases_searched=0,
            cases_matched=0,
            unmatched_anomaly_ids=[],
            degraded=degraded,
            degraded_reason=reason,
        ),
    )
