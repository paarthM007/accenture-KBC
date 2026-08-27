"""CompanyInput builder (Phase2-Plan T2.5). Ties the resolver (T2.3) and
validation layer (T2.4) together into the one function both /validate (T2.6)
and /analyze/upload (T2.7) call.
"""

import hashlib
from datetime import date, timedelta
from typing import Optional

from api.config.loader import metrics as load_metrics
from api.config.loader import revenue_bands as load_revenue_bands
from api.config.loader import thresholds as load_thresholds
from api.models.internal import (
    FormMetadata,
    MappingProposal,
    ParseResult,
    ParseWarning,
    ParseWarningCode,
    RawCell,
    RawTable,
)
from api.models.shared import (
    CompanyInput,
    CompanyMetadata,
    Granularity,
    MetricEntry,
    ReportingPeriod,
    RevenueBand,
)
from api.parsing.primitives import infer_granularity, parse_number
from api.parsing.resolver import resolve
from api.parsing.validation import check_refusal_likely, validate_and_build_metric


def _sample_values(cells: list[RawCell], limit: int = 3) -> list[float]:
    values: list[float] = []
    for cell in cells:
        value = parse_number(cell.raw_value)
        if value is not None:
            values.append(value)
        if len(values) >= limit:
            break
    return values


def _derive_revenue_band(annual_revenue: Optional[float], user_band: Optional[RevenueBand]) -> RevenueBand:
    """O12, still provisional: lower bound inclusive, upper exclusive.
    Derived from annual_revenue when present, overriding any user-supplied
    band; if annual_revenue is null, the user's band is trusted (FormMetadata
    guarantees at least one of the two is present)."""
    if annual_revenue is None:
        assert user_band is not None  # guaranteed by FormMetadata's validator
        return user_band
    for band in load_revenue_bands():
        lo, hi = band["min"], band["max"]
        if annual_revenue >= lo and (hi is None or annual_revenue < hi):
            return RevenueBand(band["id"])
    # Bands are configured to span [0, inf) with no gaps (test_config.py
    # guards this) — unreachable for any non-negative revenue.
    raise ValueError(f"annual_revenue {annual_revenue} did not match any configured revenue band")


def _derive_company_id(company_name: str, sector_id: str) -> str:
    """Deterministic hash of name + sector for MVP, so repeated uploads of
    the same company group naturally in the feedback log."""
    digest = hashlib.sha256(f"{company_name.strip().lower()}:{sector_id}".encode()).hexdigest()
    return f"company_{digest[:16]}"


def _period_start_date(period: str, granularity: Granularity) -> date:
    if granularity == Granularity.MONTHLY:
        year, month = (int(x) for x in period.split("-"))
        return date(year, month, 1)
    if granularity == Granularity.QUARTERLY:
        year, q = period.split("-Q")
        return date(int(year), (int(q) - 1) * 3 + 1, 1)
    return date(int(period), 1, 1)


def _period_end_date(period: str, granularity: Granularity) -> date:
    """Envelope metadata only (Contract §4.1) — approximate end-of-period is
    fine; granularity is authoritative for analysis, not this field."""
    if granularity == Granularity.MONTHLY:
        year, month = (int(x) for x in period.split("-"))
        next_month, next_year = (1, year + 1) if month == 12 else (month + 1, year)
        return date(next_year, next_month, 1) - timedelta(days=1)
    if granularity == Granularity.QUARTERLY:
        year, q = period.split("-Q")
        end_month = int(q) * 3
        next_month, next_year = (1, int(year) + 1) if end_month == 12 else (end_month + 1, int(year))
        return date(next_year, next_month, 1) - timedelta(days=1)
    return date(int(period), 12, 31)


def build_company_input(
    raw_table: RawTable,
    form_metadata: FormMetadata,
    mapping_overrides: Optional[dict[str, str]] = None,
    *,
    as_of: Optional[date] = None,
) -> ParseResult:
    mapping_overrides = mapping_overrides or {}
    warnings = list(raw_table.warnings)
    proposals: list[MappingProposal] = []
    resolved_cells: dict[str, list[RawCell]] = {}

    cells_by_label: dict[str, list[RawCell]] = {}
    for cell in raw_table.cells:
        cells_by_label.setdefault(cell.source_label, []).append(cell)

    non_exact_or_alias_resolution = False

    for source_label, cells in cells_by_label.items():
        sample_values = _sample_values(cells)

        override_metric_id = mapping_overrides.get(source_label)
        if override_metric_id is not None and override_metric_id not in load_metrics():
            # An override naming a metric_id outside the real catalog must
            # never reach validate_and_build_metric() — it does a bare
            # load_metrics()[metric_id] lookup and would raise an unhandled
            # KeyError (a forceable 500, violating Phase 1 exit criterion 6).
            # Ignore the bad override and fall through to normal resolution.
            warnings.append(
                ParseWarning(
                    code=ParseWarningCode.UNKNOWN_METRIC,
                    message=(
                        f"mapping_overrides named '{override_metric_id}' for column "
                        f"'{source_label}', which isn't a known metric_id; ignored."
                    ),
                )
            )
            override_metric_id = None

        if override_metric_id is not None:
            # A confirmed mapping from /validate always wins over the
            # resolver's guess (T2.5) — no re-resolution, no new warnings.
            # Sector membership is deliberately NOT re-checked here: an
            # explicit user override is trusted over the sector guess.
            metric_id = override_metric_id
            proposal = MappingProposal(
                source_label=source_label,
                resolved_metric_id=metric_id,
                match_type="exact",
                sample_values=sample_values,
            )
        else:
            proposal, proposal_warnings = resolve(source_label, form_metadata.sector_id, sample_values)
            warnings.extend(proposal_warnings)
            metric_id = proposal.resolved_metric_id
            if proposal.match_type not in ("exact", "alias"):
                non_exact_or_alias_resolution = True

        proposals.append(proposal)
        if metric_id:
            resolved_cells.setdefault(metric_id, []).extend(cells)

    if raw_table.detected_shape == "form":
        confidence = 1.0
    elif mapping_overrides or non_exact_or_alias_resolution:
        confidence = load_thresholds()["confidence"]["ambiguous_csv"]
    else:
        confidence = load_thresholds()["confidence"]["clean_csv"]

    entries: list[MetricEntry] = []
    for metric_id, cells in resolved_cells.items():
        raw_periods_and_values = [(c.period, c.raw_value) for c in cells]
        entry, entry_warnings = validate_and_build_metric(metric_id, raw_periods_and_values, confidence, as_of=as_of)
        warnings.extend(entry_warnings)
        if entry is not None:
            entries.append(entry)

    refusal_warning = check_refusal_likely(entries)
    if refusal_warning:
        warnings.append(refusal_warning)

    revenue_band = _derive_revenue_band(form_metadata.annual_revenue, form_metadata.revenue_band)
    company_id = _derive_company_id(form_metadata.company_name, form_metadata.sector_id.value)

    all_periods = [(dp.period, entry.granularity) for entry in entries for dp in entry.values]
    if all_periods:
        overall_granularity = infer_granularity([g for _, g in all_periods]) or Granularity.MONTHLY
        start = min(_period_start_date(p, g) for p, g in all_periods)
        end = max(_period_end_date(p, g) for p, g in all_periods)
    else:
        overall_granularity = Granularity.MONTHLY
        start = end = as_of or date.today()

    company_input = CompanyInput(
        company_id=company_id,
        sector_id=form_metadata.sector_id,
        company_metadata=CompanyMetadata(
            name=form_metadata.company_name,
            founded_year=form_metadata.founded_year,
            employee_count=form_metadata.employee_count,
            annual_revenue=form_metadata.annual_revenue,
            revenue_band=revenue_band,
            region=form_metadata.region,
        ),
        reporting_period=ReportingPeriod(type=overall_granularity, start=start, end=end),
        metrics=entries,
        raw_text_context=form_metadata.raw_text_context,
    )

    return ParseResult(
        company_input=company_input,
        proposals=proposals,
        warnings=warnings,
        blocking_errors=[],
    )
