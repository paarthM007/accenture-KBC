"""Shared schema — the three cross-component contracts.

Canonical source: pipeline-Contract-V1.md (overrides C2-MasterPlan.md §5 wherever
they disagree). C1's repo (`ml_engine/models/`) is canonical over both once repo
access lands (O10) — re-sync this file and update the decision log if it drifts.

    CompanyInput   — produced by C2, consumed by C1. Schema owned by C1.
    AnomalyReport  — produced by C1, consumed by C2 + C3. Schema owned by C1.
    EnrichedReport — produced by C3, consumed by C2. PROPOSED, C3 has not signed off (§11).
"""

from datetime import date, datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enums (Contract §4.1, §5.1)
# ---------------------------------------------------------------------------


class SectorId(str, Enum):
    TECH_SAAS = "TECH_SAAS"
    RETAIL = "RETAIL"
    # MFG is OUT OF SCOPE for MVP (Contract §10)


class RevenueBand(str, Enum):
    UNDER_1M = "<1M"
    ONE_TO_10M = "1M-10M"
    TEN_TO_100M = "10M-100M"
    OVER_100M = ">100M"


class Granularity(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class SeverityLabel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    SEVERE = "SEVERE"


class DeviationDirection(str, Enum):
    ABOVE_EXPECTED = "above_expected"
    BELOW_EXPECTED = "below_expected"
    # UNVERIFIED — confirm against C1 repo. Semantics open (Contract O13): a
    # HealthyHighlight has no deviation block, so this can only appear on an
    # Anomaly — but an anomaly deviated by definition. Do not build UI logic
    # that assumes this value is unreachable.
    AS_EXPECTED = "as_expected"


class TrendDirection(str, Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    DETERIORATING = "deteriorating"


class RefusalReason(str, Enum):
    NO_METRICS_SUBMITTED = "no_metrics_submitted"
    LOW_DATA_CONFIDENCE = "low_data_confidence"
    INSUFFICIENT_PERIODS = "insufficient_periods"
    # Reserved, never triggered by any current code path (Contract §5.3).
    # Do NOT write a two-branch switch on this enum — handle all four values
    # or use a default branch, so nothing breaks when this trigger lands.
    CONTRADICTORY_EVIDENCE = "contradictory_evidence"


# ---------------------------------------------------------------------------
# Contract 1 — CompanyInput (Contract §4)
# produced by C2, consumed by C1. Schema owned by C1.
# ---------------------------------------------------------------------------


class DataPoint(BaseModel):
    period: str  # "YYYY-MM" | "YYYY-QN" | "YYYY"
    value: float
    interpolated: bool = False  # True if C2 gap-filled this point


class MetricEntry(BaseModel):
    metric_id: str  # MUST be canonical — C1 rejects unknown IDs
    granularity: Granularity  # AUTHORITATIVE over reporting_period.type
    values: list[DataPoint] = Field(min_length=1)
    confidence: float = 1.0  # 0-1


class ReportingPeriod(BaseModel):
    type: Granularity  # envelope metadata only
    start: date
    end: date


class CompanyMetadata(BaseModel):
    name: str
    founded_year: Optional[int] = None
    employee_count: int
    annual_revenue: Optional[float] = None
    revenue_band: RevenueBand  # DERIVED by C2 from annual_revenue when present
    region: str


class CompanyInput(BaseModel):
    company_id: str
    sector_id: SectorId
    company_metadata: CompanyMetadata
    reporting_period: ReportingPeriod
    metrics: list[MetricEntry]
    raw_text_context: Optional[str] = None


# ---------------------------------------------------------------------------
# Contract 2 — AnomalyReport (Contract §5)
# produced by C1, consumed by C2 + C3. Schema owned by C1.
# ---------------------------------------------------------------------------


class TrendPoint(BaseModel):
    period: str
    value: float
    z_score: float


class DeviationDetail(BaseModel):
    observed_current: float
    expected_value: float  # BAND-ADJUSTED — not a universal sector median
    expected_std: float  # BAND-ADJUSTED
    z_score: float
    percentile: float
    direction: DeviationDirection


class TrendDetail(BaseModel):
    direction: TrendDirection
    slope: Optional[float] = None
    acceleration: Optional[float] = None
    periods_deviating: Optional[int] = None
    values_over_time: Optional[list[TrendPoint]] = None
    # All Optionals are null when the metric has fewer than the trend-analysis
    # floor for its granularity (Contract §4.3 / master plan §7.2).


class Anomaly(BaseModel):
    anomaly_id: str
    metric_id: str
    metric_display_name: str
    category: str  # e.g. "revenue", "retention"
    severity_score: float  # 0-100
    severity_label: SeverityLabel
    deviation: DeviationDetail
    trend: TrendDetail
    correlated_anomalies: list[str]  # anomaly_ids — cluster seed, not a full graph (§5.3)
    noise_confidence: float  # 0-1; P(signal), not P(noise)
    context_tags: list[str]  # fixed vocabulary — master plan §8.7 / Contract §5.3
    natural_language_summary: str  # template-generated by C1, NOT an LLM


class HealthyHighlight(BaseModel):
    metric_id: str  # may be a COMPUTED id absent from metric config (e.g. ltv_cac_ratio)
    status: str  # e.g. "healthy"
    percentile: float
    note: str


class RefusalDetail(BaseModel):
    """UNVERIFIED — confirm against C1 repo. Only `reason` is confirmed against
    C1's source; `message` and `suggested_resolution` are C2's provisional
    additions (Contract §5.1, O13). `extra="allow"` is mandatory per the
    contract so real fields we failed to predict aren't silently dropped.

    C2's rendering logic must not depend on `message` being present — it
    generates fallback text from `reason` plus the original CompanyInput.
    Both provisional fields are therefore Optional even though the contract's
    prose shows `message` as a bare `str`.
    """

    model_config = ConfigDict(extra="allow")

    reason: RefusalReason  # CONFIRMED
    message: Optional[str] = None  # PROVISIONAL — see O13
    suggested_resolution: Optional[str] = None  # PROVISIONAL — see O13


class ReportMetadata(BaseModel):
    model_version: str
    synthetic_profile_version: Optional[str] = None
    metrics_analyzed: int
    metrics_with_anomalies: int
    metrics_with_missing_data: int
    skipped_metrics: list[str] = []  # unrecognised metric_ids only — NOT the same as
    # silently-excluded noise-filtered metrics (Contract O11, still open).
    processing_time_ms: int


class CompanyProfileSummary(BaseModel):
    revenue_band: RevenueBand
    employee_count: int
    region: str


class AnomalyReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: str = Field(default="anomaly_report_v1", alias="$schema")
    company_id: str
    sector_id: SectorId
    analysis_timestamp: datetime
    reporting_period: ReportingPeriod
    company_profile_summary: CompanyProfileSummary
    overall_health_score: Optional[float] = None  # NULL ON REFUSAL — bug #1, do not regress
    anomalies: list[Anomaly] = []
    non_anomalous_highlights: list[HealthyHighlight] = []
    refusal: Optional[RefusalDetail] = None
    metadata: ReportMetadata


# ---------------------------------------------------------------------------
# Contract 3 — EnrichedReport (Contract §6)
# produced by C3, consumed by C2. PROPOSED, C3 has not signed off (§11).
#
# Governing rule: C3 returns the AnomalyReport it received VERBATIM as a
# nested field. Enrichment is additive, never replacement (Contract §6.1).
# ---------------------------------------------------------------------------


class Adjustment(BaseModel):
    target_metric_id: str
    target_display_name: str
    action: Literal["INCREASE", "DECREASE"]
    direction_symbol: Literal["+", "-"]
    current_value: Optional[float] = None  # NULL if not submitted — never invented (§6.4)
    current_value_source: Literal["submitted", "not_available"]
    target_value: float
    target_basis: str  # "profile_baseline" | "top_quartile" | ...
    delta: Optional[float] = None  # NULL when current_value is null
    priority: Literal["HIGH", "MEDIUM", "LOW"]
    rationale: str


class Prescription(BaseModel):
    anomaly_id: str  # FK into anomaly_report.anomalies
    prescribed_adjustments: list[Adjustment]
    prescription_summary: str  # NOT "natural_language_summary" — name collision (§6.6)


class MatchedCase(BaseModel):
    case_id: str
    cluster_index: int
    similarity_score: float
    problem_description: str
    root_causes: list[str]
    recommended_actions: list[str]


class ActionItem(BaseModel):
    action: str
    priority: str
    rationale: str


class Narrative(BaseModel):
    situation_summary: str
    likely_root_causes: list[str]
    prioritized_actions: list[ActionItem]
    positives: list[str]


class EnrichmentMetadata(BaseModel):
    """degraded_reason — C2-PROPOSED v1.2, additive and optional. Not in the
    signed contract shape (Contract §6.2); flagged for announcement to C3
    alongside O7 (EnrichedReport sign-off still pending).

    Deliberately Optional[str], not an enum: this field can be set by either
    side (C2 when it wraps a bare AnomalyReport after a C1/C3 failure; C3
    itself per Contract §6.7, e.g. an LLM failure it handles internally with
    no exception ever reaching C2). An enum would turn an unrecognised value
    from the other component into a ValidationError — a hard failure exactly
    where degradation was supposed to be graceful.

    Conventional vocabulary (not enforced):
        C2 sets: c3_timeout | c3_failed | c3_contract_violation
        C3 sets: llm_failed | llm_timeout | case_match_failed
    Unknown values are logged and rendered generically, never rejected.
    """

    llm_model: Optional[str] = None
    llm_tokens_used: Optional[int] = None
    processing_time_ms: int
    cases_searched: int
    cases_matched: int
    unmatched_anomaly_ids: list[str] = []
    degraded: bool = False
    degraded_reason: Optional[str] = None


class EnrichedReport(BaseModel):
    # UNVERIFIED — the entire block is PROPOSED; C3 has not signed off (Contract §11).
    model_config = ConfigDict(populate_by_name=True)

    schema_version: str = Field(default="enriched_report_v1", alias="$schema")
    anomaly_report: AnomalyReport  # VERBATIM, UNTOUCHED
    prescriptions: list[Prescription] = []
    anomaly_clusters: list[list[str]] = []
    matched_cases: list[MatchedCase] = []
    narrative: Optional[Narrative] = None
    metadata: EnrichmentMetadata
