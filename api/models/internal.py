"""C2-internal models — master plan §5.5. Ours alone; no external component
depends on these, so they can change freely without cross-team coordination.
"""

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, model_validator

from api.models.shared import CompanyInput, EnrichedReport, RevenueBand, SectorId


class ParseWarningCode(str, Enum):
    """Warning-code vocabulary, defined now so Phase 2 (parsing) and Phase 3
    (frontend) agree without a second conversation (Phase0-Plan T0.3)."""

    UNKNOWN_METRIC = "UNKNOWN_METRIC"  # column couldn't resolve to a canonical metric_id
    UNIT_SCALE_SUSPECT = "UNIT_SCALE_SUSPECT"  # distributional fraction/percent check tripped
    OUT_OF_RANGE = "OUT_OF_RANGE"  # value outside valid_min/valid_max
    SHORT_SERIES = "SHORT_SERIES"  # below the trend floor but above the hard block
    INTERPOLATED_POINTS = "INTERPOLATED_POINTS"  # C2 gap-filled one or more periods
    SECTOR_MISMATCH = "SECTOR_MISMATCH"  # metric exists but not for the submitted sector
    AMBIGUOUS_MAPPING = "AMBIGUOUS_MAPPING"  # multiple aliases matched; user confirmation needed
    # Generic CompanyInput body-shape failure (Phase1-Plan T1.5) — distinct
    # from the domain-specific codes above, which all come from Phase 2's
    # CSV/form parsing pipeline, not from raw JSON schema validation.
    SCHEMA_VALIDATION_ERROR = "SCHEMA_VALIDATION_ERROR"

    # --- Phase 2 additions (Phase2-Plan T2.1/T2.2/T2.4) ---
    DATE_TRUNCATED = "DATE_TRUNCATED"  # a full date was truncated to its period (e.g. 2026-01-15 -> 2026-01)
    TWO_DIGIT_YEAR_FUTURE = "TWO_DIGIT_YEAR_FUTURE"  # "assume 2000s" landed >1 year in the future
    AMBIGUOUS_NUMBER_FORMAT = "AMBIGUOUS_NUMBER_FORMAT"  # column mixes American/European separators
    MIXED_GRANULARITY = "MIXED_GRANULARITY"  # one metric's periods don't share a single granularity
    AMBIGUOUS_SHAPE = "AMBIGUOUS_SHAPE"  # neither wide nor transposed shape detection heuristic won
    SERIES_TRIMMED = "SERIES_TRIMMED"  # a 4+ period gap caused a trim to the most recent contiguous block
    INTERPOLATION_HEAVY = "INTERPOLATION_HEAVY"  # interpolated_ratio > 0.3 even though no single gap trimmed
    CONSTANT_SERIES = "CONSTANT_SERIES"  # every value in the series is identical
    SPARSE_SERIES = "SPARSE_SERIES"  # more than half the values are null
    DUPLICATE_PERIOD = "DUPLICATE_PERIOD"  # same period appeared twice for one metric; last one kept
    REFUSAL_LIKELY = "REFUSAL_LIKELY"  # every surviving metric is below its trend floor — C1 will refuse


class MappingProposal(BaseModel):
    """One resolved column from an uploaded file."""

    source_label: str  # header as written by the user
    resolved_metric_id: Optional[str] = None  # None if unresolvable
    match_type: Literal["exact", "alias", "normalized", "unresolved"]
    unit_warning: Optional[str] = None  # e.g. fraction/percent suspicion
    # Populated only for an ambiguous match (Phase2-Plan T2.3: "all candidates
    # returned, user decides in /validate"). Empty otherwise.
    candidates: list[str] = []
    sample_values: list[float] = []


class ParseWarning(BaseModel):
    code: ParseWarningCode
    metric_id: Optional[str] = None
    message: str


class ParseResult(BaseModel):
    company_input: Optional[CompanyInput] = None
    proposals: list[MappingProposal] = []
    warnings: list[ParseWarning] = []
    blocking_errors: list[str] = []


class RawCell(BaseModel):
    """One (period, source_label, raw_value) triple — the long-form
    representation both CSV shapes (wide/transposed) and the manual form
    converge into, so everything downstream works on one structure
    (Phase2-Plan §2, T2.2)."""

    period: str  # not yet parsed/normalized — parsing/primitives.py does that later
    source_label: str  # header/label exactly as the user wrote it
    raw_value: str  # not yet parsed — parsing/primitives.py does that later


class RawTable(BaseModel):
    cells: list[RawCell]
    detected_shape: Literal["wide", "transposed", "form"]
    warnings: list[ParseWarning] = []


class InferredMetadata(BaseModel):
    granularity: Optional[str] = None
    periods: int = 0
    shape: Optional[Literal["wide", "transposed", "form"]] = None
    revenue_band: Optional[str] = None


class ValidateResponse(BaseModel):
    """POST /validate's response shape (Phase2-Plan T2.6). Distinct from
    ParseResult — it never carries a company_input (validate stops before
    building one) and adds `inferred`/`ready`, which ParseResult has no use
    for elsewhere."""

    proposals: list[MappingProposal] = []
    warnings: list[ParseWarning] = []
    blocking_errors: list[str] = []
    inferred: InferredMetadata = InferredMetadata()
    ready: bool = False


class FormMetadata(BaseModel):
    """Company-level metadata accompanying a file upload or manual entry
    (Phase2-Plan T2.5/T2.6). Distinct from CompanyMetadata (models/shared.py):
    this is what the USER supplies; CompanyMetadata is what C2 derives from it
    (e.g. revenue_band overridden from annual_revenue when present)."""

    company_name: str
    sector_id: SectorId
    employee_count: int
    region: str
    founded_year: Optional[int] = None
    annual_revenue: Optional[float] = None
    revenue_band: Optional[RevenueBand] = None  # trusted only if annual_revenue is absent
    raw_text_context: Optional[str] = None

    @model_validator(mode="after")
    def _require_revenue_signal(self) -> "FormMetadata":
        if self.annual_revenue is None and self.revenue_band is None:
            raise ValueError("Either annual_revenue or revenue_band must be provided.")
        return self


class ErrorCode(str, Enum):
    """Error-code vocabulary for ApiResponse.error (Phase1-Plan T1.5). C2-owned
    and always self-assigned — never parsed from an external component's
    output — so unlike EnrichmentMetadata.degraded_reason this is safe to
    type as an enum rather than a bare string.
    """

    VALIDATION_ERROR = "VALIDATION_ERROR"
    C1_TIMEOUT = "C1_TIMEOUT"
    C1_FAILED = "C1_FAILED"
    # Reserved, not currently triggered: get_c1()/get_c3() degrade a missing
    # real module to the mock with a warning log rather than raising, so
    # nothing in Phase 1 surfaces this to the client yet.
    C1_UNAVAILABLE = "C1_UNAVAILABLE"
    C3_TIMEOUT = "C3_TIMEOUT"
    C3_FAILED = "C3_FAILED"
    C3_CONTRACT_VIOLATION = "C3_CONTRACT_VIOLATION"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class Timings(BaseModel):
    """Wall-clock time C2's orchestrator spent per stage — distinct from each
    stage's own self-reported processing_time_ms (ReportMetadata /
    EnrichmentMetadata), which measures only that component's internal
    computation, not thread-pool or dispatch overhead."""

    c1_ms: Optional[int] = None
    c3_ms: Optional[int] = None  # null when C3 was never called (refusal short-circuit)
    total_ms: int


class ApiResponse(BaseModel):
    """Envelope. Identical shape whether sync or polled — so we can switch
    without touching the frontend."""

    job_id: str
    status: Literal["complete", "running", "failed", "refused"]
    result: Optional[EnrichedReport] = None
    warnings: list[ParseWarning] = []
    error: Optional[ErrorCode] = None
    timings: Optional[Timings] = None
