import time
import json
from typing import Union, List
from .schemas import AnomalyReport, EnrichedReport, EnrichmentMetadata, Prescription
from .gatekeeper import check_refusal
from .clustering import build_anomaly_clusters
from .prescriptions import build_prescription

def enrich_report(anomaly_report_input: Union[AnomalyReport, dict, str]) -> EnrichedReport:
    """
    Main entry point for C3 Module. Enriches AnomalyReport with prescriptions,
    anomaly clusters, matched cases, and narrative.
    
    Accepts AnomalyReport Pydantic object, raw dictionary, or JSON string.
    """
    start_time = time.perf_counter()
    
    # 1. Parse and validate input
    if isinstance(anomaly_report_input, str):
        anomaly_report = AnomalyReport.model_validate_json(anomaly_report_input)
    elif isinstance(anomaly_report_input, dict):
        anomaly_report = AnomalyReport.model_validate(anomaly_report_input)
    elif isinstance(anomaly_report_input, AnomalyReport):
        anomaly_report = anomaly_report_input
    else:
        raise TypeError("Input must be a JSON string, dict, or AnomalyReport instance")
        
    # 2. Gate 0 / Refusal Check (§6.3)
    refusal_report = check_refusal(anomaly_report, start_time)
    if refusal_report is not None:
        return refusal_report
        
    # 3. Graph-Based Clustering Engine (§3)
    anomaly_clusters = build_anomaly_clusters(anomaly_report.anomalies)
    
    # 4. Deterministic Prescription Engine (§6.5)
    prescriptions: List[Prescription] = []
    unmatched_anomaly_ids: List[str] = []
    
    for anomaly in anomaly_report.anomalies:
        prescription = build_prescription(anomaly_report, anomaly, unmatched_anomaly_ids)
        if prescription is not None:
            prescriptions.append(prescription)
            
    # 5. Case Matching and Narrative (Stubbed for Phase 1 deterministic core)
    matched_cases = []
    narrative = None
    
    # 6. Metadata and response packaging
    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    
    metadata = EnrichmentMetadata(
        llm_model=None,
        llm_tokens_used=None,
        processing_time_ms=elapsed_ms,
        cases_searched=0,
        cases_matched=0,
        unmatched_anomaly_ids=unmatched_anomaly_ids,
        degraded=False
    )
    
    return EnrichedReport(
        anomaly_report=anomaly_report,
        prescriptions=prescriptions,
        anomaly_clusters=anomaly_clusters,
        matched_cases=matched_cases,
        narrative=narrative,
        metadata=metadata
    )
