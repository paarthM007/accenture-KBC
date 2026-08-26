import time
from typing import Union, List
from .schemas import AnomalyReport, EnrichedReport, EnrichmentMetadata, Prescription
from .gatekeeper import check_refusal
from .clustering import build_anomaly_clusters
from .prescriptions import build_prescription
from .case_matcher import match_cases_for_clusters, load_case_studies
from .narrative import generate_narrative

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
    prescriptions: list[Prescription] = []
    unmatched_anomaly_ids: list[str] = []
    
    for anomaly in anomaly_report.anomalies:
        prescription = build_prescription(anomaly_report, anomaly, unmatched_anomaly_ids)
        if prescription is not None:
            prescriptions.append(prescription)
            
    # 5. Case Matching (§6.7)
    matched_cases = match_cases_for_clusters(
        sector_id=anomaly_report.sector_id,
        clusters=anomaly_clusters,
        anomalies=anomaly_report.anomalies
    )
    
    # 6. Narrative Generation (LLM call with Degraded Mode) (§6.7)
    narrative, is_degraded, llm_meta = generate_narrative(
        anomaly_report=anomaly_report,
        prescriptions=prescriptions,
        matched_cases=matched_cases
    )
    
    # 7. Metadata and response packaging
    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    
    cases_searched = len(load_case_studies())
    
    llm_model = None
    llm_tokens_used = None
    if not is_degraded and llm_meta:
        llm_model = llm_meta.get("llm_model")
        llm_tokens_used = llm_meta.get("token_usage", {}).get("total_tokens")
        
    metadata = EnrichmentMetadata(
        llm_model=llm_model,
        llm_tokens_used=llm_tokens_used,
        processing_time_ms=elapsed_ms,
        cases_searched=cases_searched,
        cases_matched=len(matched_cases),
        unmatched_anomaly_ids=unmatched_anomaly_ids,
        degraded=is_degraded
    )
    
    return EnrichedReport(
        anomaly_report=anomaly_report,
        prescriptions=prescriptions,
        anomaly_clusters=anomaly_clusters,
        matched_cases=matched_cases,
        narrative=narrative,
        metadata=metadata
    )
