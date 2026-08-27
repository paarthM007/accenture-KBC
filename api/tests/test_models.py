"""T0.9 — models/shared.py and models/internal.py construct correctly under
all the traps called out in Phase0-Plan T0.2 (bare Optional, min_length,
populate_by_name, overall_health_score nullability, str-Enum serialization).
"""

from datetime import date, datetime

import pytest

from api.models.internal import ApiResponse, MappingProposal, ParseResult, ParseWarning, ParseWarningCode
from api.models.shared import (
    Anomaly,
    AnomalyReport,
    CompanyInput,
    CompanyMetadata,
    CompanyProfileSummary,
    DataPoint,
    DeviationDetail,
    DeviationDirection,
    EnrichedReport,
    EnrichmentMetadata,
    Granularity,
    MetricEntry,
    RefusalDetail,
    RefusalReason,
    ReportingPeriod,
    ReportMetadata,
    RevenueBand,
    SectorId,
    SeverityLabel,
    TrendDetail,
    TrendDirection,
)


def _minimal_company_input() -> CompanyInput:
    return CompanyInput(
        company_id="c1",
        sector_id=SectorId.TECH_SAAS,
        company_metadata=CompanyMetadata(
            name="Acme",
            employee_count=10,
            revenue_band=RevenueBand.UNDER_1M,
            region="US",
        ),
        reporting_period=ReportingPeriod(
            type=Granularity.MONTHLY, start=date(2024, 1, 1), end=date(2024, 1, 31)
        ),
        metrics=[
            MetricEntry(
                metric_id="churn_rate",
                granularity=Granularity.MONTHLY,
                values=[DataPoint(period="2024-01", value=2.0)],
            )
        ],
    )


def _minimal_report_metadata() -> ReportMetadata:
    return ReportMetadata(
        model_version="v1",
        metrics_analyzed=1,
        metrics_with_anomalies=0,
        metrics_with_missing_data=0,
        processing_time_ms=1,
    )


def _minimal_anomaly_report(refusal: RefusalDetail | None = None, overall_health_score=None) -> AnomalyReport:
    return AnomalyReport(
        company_id="c1",
        sector_id=SectorId.TECH_SAAS,
        analysis_timestamp=datetime(2024, 1, 31, 0, 0, 0),
        reporting_period=ReportingPeriod(
            type=Granularity.MONTHLY, start=date(2024, 1, 1), end=date(2024, 1, 31)
        ),
        company_profile_summary=CompanyProfileSummary(
            revenue_band=RevenueBand.UNDER_1M, employee_count=10, region="US"
        ),
        overall_health_score=overall_health_score,
        refusal=refusal,
        metadata=_minimal_report_metadata(),
    )


class TestCompanyInput:
    def test_constructs_from_minimal_payload(self):
        company_input = _minimal_company_input()
        assert company_input.company_id == "c1"
        assert company_input.raw_text_context is None  # Optional, omissible

    def test_metric_entry_requires_at_least_one_value(self):
        with pytest.raises(Exception):
            MetricEntry(metric_id="churn_rate", granularity=Granularity.MONTHLY, values=[])


class TestAnomalyReport:
    def test_constructs_with_empty_anomalies_and_null_refusal(self):
        report = _minimal_anomaly_report()
        assert report.anomalies == []
        assert report.non_anomalous_highlights == []
        assert report.refusal is None

    def test_overall_health_score_none_is_accepted(self):
        # Highest-value single line in the file (Phase0-Plan T0.2) — must not
        # raise a ValidationError on the refusal demo.
        report = _minimal_anomaly_report(overall_health_score=None)
        assert report.overall_health_score is None

    def test_overall_health_score_float_is_accepted(self):
        report = _minimal_anomaly_report(overall_health_score=78.5)
        assert report.overall_health_score == 78.5

    def test_report_metadata_has_exact_contract_field_set(self):
        # Regression test: pydantic's default extra="ignore" silently drops
        # unrecognized constructor kwargs instead of raising, which let
        # `processing_time_ms` go missing from the model entirely while
        # fixture builders kept "setting" it with no error. Pin the full
        # field set from Contract §5.1 so a dropped field fails loudly here.
        expected_fields = {
            "model_version",
            "synthetic_profile_version",
            "metrics_analyzed",
            "metrics_with_anomalies",
            "metrics_with_missing_data",
            "skipped_metrics",
            "processing_time_ms",
        }
        assert set(ReportMetadata.model_fields.keys()) == expected_fields

    def test_refusal_detail_only_requires_reason(self):
        detail = RefusalDetail(reason=RefusalReason.INSUFFICIENT_PERIODS)
        assert detail.message is None
        assert detail.suggested_resolution is None

    def test_refusal_detail_allows_extra_fields(self):
        # Contract §5.1: extra="allow" so unpredicted real fields from C1
        # survive instead of being silently dropped.
        detail = RefusalDetail(reason=RefusalReason.NO_METRICS_SUBMITTED, an_unpredicted_field=42)
        assert detail.model_dump()["an_unpredicted_field"] == 42

    def test_schema_alias_round_trips_both_directions(self):
        report = _minimal_anomaly_report()

        by_alias = report.model_dump(by_alias=True)
        assert "$schema" in by_alias
        assert AnomalyReport.model_validate(by_alias).schema_version == "anomaly_report_v1"

        by_field_name = report.model_dump(by_alias=False)
        assert "schema_version" in by_field_name
        assert AnomalyReport.model_validate(by_field_name).schema_version == "anomaly_report_v1"

    def test_full_anomaly_constructs(self):
        anomaly = Anomaly(
            anomaly_id="a1",
            metric_id="churn_rate",
            metric_display_name="Churn Rate (%)",
            category="retention",
            severity_score=80.0,
            severity_label=SeverityLabel.SEVERE,
            deviation=DeviationDetail(
                observed_current=5.0,
                expected_value=2.0,
                expected_std=0.8,
                z_score=3.75,
                percentile=99.9,
                direction=DeviationDirection.ABOVE_EXPECTED,
            ),
            trend=TrendDetail(direction=TrendDirection.DETERIORATING),
            correlated_anomalies=[],
            noise_confidence=0.9,
            context_tags=["churn_related"],
            natural_language_summary="Churn rose sharply.",
        )
        assert anomaly.trend.slope is None  # Optional, omissible


class TestEnrichedReport:
    def test_constructs_nesting_anomaly_report_verbatim(self):
        report = _minimal_anomaly_report()
        enriched = EnrichedReport(
            anomaly_report=report,
            metadata=EnrichmentMetadata(processing_time_ms=1, cases_searched=0, cases_matched=0),
        )
        assert enriched.anomaly_report == report
        assert enriched.narrative is None
        assert enriched.prescriptions == []


class TestInternalModels:
    def test_api_response_constructs_in_all_four_statuses(self):
        for status in ("complete", "running", "failed", "refused"):
            response = ApiResponse(job_id="job1", status=status, result=None)
            assert response.status == status
            assert response.result is None

    def test_parse_result_constructs_minimal(self):
        result = ParseResult()
        assert result.company_input is None
        assert result.blocking_errors == []

    def test_mapping_proposal_unresolved(self):
        proposal = MappingProposal(source_label="Weird Header", resolved_metric_id=None, match_type="unresolved")
        assert proposal.resolved_metric_id is None

    def test_parse_warning_every_code_constructible(self):
        for code in ParseWarningCode:
            warning = ParseWarning(code=code, message="test")
            assert warning.code == code


@pytest.mark.parametrize(
    "enum_cls",
    [SectorId, RevenueBand, Granularity, SeverityLabel, DeviationDirection, TrendDirection, RefusalReason],
)
def test_every_enum_value_is_constructible_and_str(enum_cls):
    for member in enum_cls:
        assert enum_cls(member.value) is member
        assert isinstance(member.value, str)
