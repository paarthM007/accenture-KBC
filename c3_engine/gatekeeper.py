import time
from typing import Optional
from .schemas import AnomalyReport, EnrichedReport, EnrichmentMetadata

def check_refusal(anomaly_report: AnomalyReport, start_time: float) -> Optional[EnrichedReport]:
    """
    If anomaly_report.refusal is not None, immediately return an EnrichedReport
    containing the untouched anomaly_report, empty lists/nulls, and bypasses
    all downstream processing.
    """
    if anomaly_report.refusal is not None:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return EnrichedReport(
            anomaly_report=anomaly_report,
            prescriptions=[],
            anomaly_clusters=[],
            matched_cases=[],
            narrative=None,
            metadata=EnrichmentMetadata(
                llm_model=None,
                llm_tokens_used=None,
                processing_time_ms=elapsed_ms,
                cases_searched=0,
                cases_matched=0,
                unmatched_anomaly_ids=[],
                degraded=False
            )
        )
    return None
