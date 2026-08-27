"""Stand-in for C3's `enrich_report`. Implements the MANDATORY defensive
refusal guard from pipeline-Contract-V1.md §6.3: primary enforcement lives in
C2's orchestrator (§3, C2 never calls C3 on a refusal), but this guard exists
so that a future call path that forgets the check still fails safe — no LLM
call, no prescriptions, no invented explanation.
"""

import time

from api.models.shared import (
    ActionItem,
    Adjustment,
    AnomalyReport,
    DeviationDirection,
    EnrichedReport,
    EnrichmentMetadata,
    MatchedCase,
    Narrative,
    Prescription,
    SeverityLabel,
)

_PRIORITY_BY_SEVERITY = {
    SeverityLabel.SEVERE: "HIGH",
    SeverityLabel.CRITICAL: "HIGH",
    SeverityLabel.WARNING: "MEDIUM",
    SeverityLabel.INFO: "LOW",
}


def _adjustment_for(anomaly) -> Adjustment:
    dev = anomaly.deviation
    # current_value/target_value come straight from C1's own report — never
    # invented (Contract §6.4). The anomaly's metric was, by construction,
    # submitted by the user, so current_value_source is always "submitted" here.
    action = "DECREASE" if dev.direction == DeviationDirection.ABOVE_EXPECTED else "INCREASE"
    return Adjustment(
        target_metric_id=anomaly.metric_id,
        target_display_name=anomaly.metric_display_name,
        action=action,
        direction_symbol="-" if action == "DECREASE" else "+",
        current_value=dev.observed_current,
        current_value_source="submitted",
        target_value=dev.expected_value,
        target_basis="profile_baseline",  # Contract §6.5 — use expected_value directly
        delta=round(dev.expected_value - dev.observed_current, 3),
        priority=_PRIORITY_BY_SEVERITY.get(anomaly.severity_label, "MEDIUM"),
        rationale=f"Move {anomaly.metric_display_name} toward the expected baseline for this profile.",
    )


class MockC3:
    def __init__(self, fail_llm: bool = False, raise_on_call: bool = False, sleep_s: float = 1.5):
        self.fail_llm = fail_llm
        self.raise_on_call = raise_on_call
        self.sleep_s = sleep_s  # mimics the LLM call latency

    def enrich_report(self, report: AnomalyReport) -> EnrichedReport:
        if self.raise_on_call:
            raise RuntimeError("MockC3 configured to raise (raise_on_call=True)")

        if report.refusal is not None:
            # Defensive guard (Contract §6.3) — no LLM call, no cost, no delay.
            return EnrichedReport(
                anomaly_report=report,
                prescriptions=[],
                anomaly_clusters=[],
                matched_cases=[],
                narrative=None,
                metadata=EnrichmentMetadata(
                    processing_time_ms=0,
                    cases_searched=0,
                    cases_matched=0,
                    unmatched_anomaly_ids=[],
                    degraded=False,
                ),
            )

        time.sleep(self.sleep_s)

        prescriptions = [
            Prescription(
                anomaly_id=a.anomaly_id,
                prescribed_adjustments=[_adjustment_for(a)],
                prescription_summary=f"Address {a.metric_display_name} to move back toward baseline.",
            )
            for a in report.anomalies
        ]

        clustered_ids = sorted({a.anomaly_id for a in report.anomalies if a.correlated_anomalies})
        anomaly_clusters = [clustered_ids] if clustered_ids else []

        matched_cases = [
            MatchedCase(
                case_id=f"case_mock_{i:03d}",
                cluster_index=0,
                similarity_score=0.82,
                problem_description=f"Historical case resembling the {a.metric_display_name} deviation.",
                root_causes=["Mock root cause A", "Mock root cause B"],
                recommended_actions=["Mock recommended action"],
            )
            for i, a in enumerate(report.anomalies, start=1)
        ]

        if self.fail_llm:
            narrative = None
            degraded = True
            llm_model = None
            llm_tokens_used = None
        else:
            narrative = Narrative(
                situation_summary=(
                    "Mock narrative: the submitted metrics show a coordinated deterioration "
                    "consistent with the flagged anomalies."
                ),
                likely_root_causes=(
                    [a.natural_language_summary for a in report.anomalies]
                    or ["No anomalies detected; company is tracking near its expected baseline."]
                ),
                prioritized_actions=[
                    ActionItem(
                        action=f"Investigate {a.metric_display_name}",
                        priority=_PRIORITY_BY_SEVERITY.get(a.severity_label, "MEDIUM"),
                        rationale="Flagged anomaly in this report.",
                    )
                    for a in report.anomalies
                ],
                positives=[h.note for h in report.non_anomalous_highlights],
            )
            degraded = False
            llm_model = "mock-llm-v1"
            llm_tokens_used = 512

        metadata = EnrichmentMetadata(
            llm_model=llm_model,
            llm_tokens_used=llm_tokens_used,
            processing_time_ms=int(self.sleep_s * 1000),
            cases_searched=len(report.anomalies) * 5,
            cases_matched=len(matched_cases),
            unmatched_anomaly_ids=[],
            degraded=degraded,
        )

        return EnrichedReport(
            anomaly_report=report,
            prescriptions=prescriptions,
            anomaly_clusters=anomaly_clusters,
            matched_cases=matched_cases,
            narrative=narrative,
            metadata=metadata,
        )
