from datetime import datetime, date
from typing import Literal, Optional, Any
from pydantic import BaseModel, ConfigDict, Field

class ReportingPeriod(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    type: Literal["monthly", "quarterly", "annual"]
    start: date
    end: date

class CompanyProfileSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    revenue_band: str
    employee_count: int
    region: str

class DeviationDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    observed_current: float
    expected_value: float
    expected_std: float
    z_score: float
    percentile: float
    direction: Literal["above_expected", "below_expected", "as_expected"]

class TrendPoint(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    period: str
    value: float
    interpolated: bool = False

class TrendDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    direction: Literal["improving", "stable", "deteriorating"]
    slope: Optional[float] = None
    acceleration: Optional[float] = None
    periods_deviating: Optional[int] = None
    values_over_time: Optional[list[TrendPoint]] = None

class Anomaly(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    anomaly_id: str
    metric_id: str
    metric_display_name: str
    category: str
    severity_score: float
    severity_label: Literal["INFO", "WARNING", "CRITICAL", "SEVERE"]
    deviation: DeviationDetail
    trend: TrendDetail
    correlated_anomalies: list[str]
    noise_confidence: float
    context_tags: list[str]
    natural_language_summary: str

class HealthyHighlight(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    metric_id: str
    metric_display_name: str
    observed_value: Optional[float] = None
    expected_value: Optional[float] = None
    percentile: Optional[float] = None
    context_tags: Optional[list[str]] = None
    natural_language_summary: Optional[str] = None

class RefusalDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    reason: str
    message: str
    required_data: Optional[str] = None

class ReportMetadata(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    model_version: str
    synthetic_profile_version: str
    metrics_analyzed: list[str]
    metrics_with_anomalies: list[str]
    metrics_with_missing_data: list[str]
    skipped_metrics: list[str]
    processing_time_ms: float

class AnomalyReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_version: str = Field(default="anomaly_report_v1", alias="$schema")
    company_id: str
    sector_id: str
    analysis_timestamp: datetime
    reporting_period: ReportingPeriod
    company_profile_summary: CompanyProfileSummary
    overall_health_score: Optional[float] = None
    anomalies: list[Anomaly]
    non_anomalous_highlights: list[HealthyHighlight]
    refusal: Optional[RefusalDetail] = None
    metadata: ReportMetadata


class Adjustment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    target_metric_id: str
    target_display_name: str
    action: Literal["INCREASE", "DECREASE"]
    direction_symbol: Literal["+", "-"]
    current_value: Optional[float] = None
    current_value_source: Literal["submitted", "not_available"]
    target_value: float
    target_basis: str
    delta: Optional[float] = None
    priority: Literal["HIGH", "MEDIUM", "LOW"]
    rationale: str

class Prescription(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    anomaly_id: str
    prescribed_adjustments: list[Adjustment]
    prescription_summary: str

class MatchedCase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    case_id: str
    cluster_index: int
    similarity_score: float
    problem_description: str
    root_causes: list[str]
    recommended_actions: list[str]

class ActionItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    title: str
    description: str
    priority: Literal["HIGH", "MEDIUM", "LOW"]
    rationale: Optional[str] = None

class Narrative(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    situation_summary: str
    likely_root_causes: list[str]
    prioritized_actions: list[ActionItem]
    positives: list[str]

class EnrichmentMetadata(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    llm_model: Optional[str] = None
    llm_tokens_used: Optional[int] = None
    processing_time_ms: float
    cases_searched: int
    cases_matched: int
    unmatched_anomaly_ids: list[str]
    degraded: bool

class EnrichedReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_version: str = Field(default="enriched_report_v1", alias="$schema")
    anomaly_report: AnomalyReport
    prescriptions: list[Prescription]
    anomaly_clusters: list[list[str]]
    matched_cases: list[MatchedCase]
    narrative: Optional[Narrative] = None
    metadata: EnrichmentMetadata
