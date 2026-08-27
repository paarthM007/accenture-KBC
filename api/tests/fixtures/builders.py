"""Fixture builders — four demo scenarios, as Python functions returning model
instances (Phase0-Plan T0.6). A schema change breaks these loudly at import
time instead of silently producing an invalid fixture.

Every fixture pairs a CompanyInput with the AnomalyReport C1 would plausibly
return for it, so the same fixture serves Phase 1 (orchestration) and
Phase 2 (parsing).
"""

from datetime import date, datetime

from api.models.shared import (
    Anomaly,
    AnomalyReport,
    CompanyInput,
    CompanyMetadata,
    CompanyProfileSummary,
    DataPoint,
    DeviationDetail,
    DeviationDirection,
    Granularity,
    HealthyHighlight,
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
    TrendPoint,
)


def _monthly_periods(start_year: int, start_month: int, n: int) -> list[str]:
    periods = []
    y, m = start_year, start_month
    for _ in range(n):
        periods.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return periods


def _points(periods: list[str], values: list[float]) -> list[DataPoint]:
    assert len(periods) == len(values)
    return [DataPoint(period=p, value=v) for p, v in zip(periods, values)]


def _metric(metric_id: str, periods: list[str], values: list[float], confidence: float = 1.0) -> MetricEntry:
    return MetricEntry(
        metric_id=metric_id,
        granularity=Granularity.MONTHLY,
        values=_points(periods, values),
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# healthy — all metrics near baseline; exercises non_anomalous_highlights and
# a high health score. Includes a COMPUTED highlight (ltv_cac_ratio) whose
# metric_id is absent from metric_config.yaml — the regression test for the
# "consumers must tolerate unknown computed metric_ids" rule (Contract §5.2).
# ---------------------------------------------------------------------------


def build_healthy() -> tuple[CompanyInput, AnomalyReport]:
    periods = _monthly_periods(2024, 1, 12)

    company_input = CompanyInput(
        company_id="company_healthy_001",
        sector_id=SectorId.TECH_SAAS,
        company_metadata=CompanyMetadata(
            name="Acme SaaS Co",
            founded_year=2019,
            employee_count=45,
            annual_revenue=4_500_000,
            revenue_band=RevenueBand.ONE_TO_10M,
            region="US",
        ),
        reporting_period=ReportingPeriod(
            type=Granularity.MONTHLY, start=date(2024, 1, 1), end=date(2024, 12, 31)
        ),
        metrics=[
            _metric("churn_rate", periods, [2.0, 1.9, 2.1, 2.0, 1.8, 2.2, 2.0, 1.9, 2.1, 2.0, 1.9, 2.0]),
            _metric(
                "net_revenue_retention",
                periods,
                [101, 100, 102, 101, 99, 100, 101, 102, 100, 101, 100, 101],
            ),
            _metric("gross_margin", periods, [75, 74, 76, 75, 74, 75, 76, 75, 74, 75, 76, 75]),
            _metric(
                "customer_acquisition_cost",
                periods,
                [4400, 4600, 4500, 4550, 4450, 4500, 4600, 4400, 4500, 4550, 4450, 4500],
            ),
            _metric(
                "monthly_recurring_revenue_growth",
                periods,
                [8.1, 7.9, 8.2, 8.0, 7.8, 8.1, 8.0, 7.9, 8.2, 8.0, 7.9, 8.1],
            ),
        ],
    )

    anomaly_report = AnomalyReport(
        company_id=company_input.company_id,
        sector_id=company_input.sector_id,
        analysis_timestamp=datetime(2024, 12, 31, 12, 0, 0),
        reporting_period=company_input.reporting_period,
        company_profile_summary=CompanyProfileSummary(
            revenue_band=RevenueBand.ONE_TO_10M, employee_count=45, region="US"
        ),
        overall_health_score=78.0,
        anomalies=[],
        non_anomalous_highlights=[
            HealthyHighlight(
                metric_id="churn_rate",
                status="healthy",
                percentile=54.0,
                note="Churn is tracking in line with the expected baseline for a company of this profile.",
            ),
            HealthyHighlight(
                metric_id="net_revenue_retention",
                status="healthy",
                percentile=58.0,
                note="Net revenue retention is comfortably within the expected range.",
            ),
            HealthyHighlight(
                metric_id="ltv_cac_ratio",
                status="healthy",
                percentile=71.0,
                note="LTV:CAC ratio (computed) is above the healthy 3:1 benchmark for this profile.",
            ),
        ],
        refusal=None,
        metadata=ReportMetadata(
            model_version="0.1.0-mock",
            synthetic_profile_version="tech_saas_v1",
            metrics_analyzed=5,
            metrics_with_anomalies=0,
            metrics_with_missing_data=0,
            skipped_metrics=[],
            processing_time_ms=175,
        ),
    )
    return company_input, anomaly_report


# ---------------------------------------------------------------------------
# critical — the flagship demo scenario. churn_rate + net_revenue_retention
# both trip, mutually correlated (-0.80, the strongest pair available), both
# with 8 monthly periods (>= 6, so trend/trajectory scoring applies).
# gross_margin stays flat and healthy alongside the anomalies.
# ---------------------------------------------------------------------------


def build_critical() -> tuple[CompanyInput, AnomalyReport]:
    periods = _monthly_periods(2024, 1, 8)

    churn_values = [2.1, 2.5, 3.0, 3.4, 3.9, 4.3, 4.8, 5.2]
    nrr_values = [106, 103, 101, 98, 96, 93, 91, 88]
    gm_values = [74.2, 73.8, 74.1, 74.0, 73.9, 74.3, 74.0, 73.7]

    company_input = CompanyInput(
        company_id="company_critical_001",
        sector_id=SectorId.TECH_SAAS,
        company_metadata=CompanyMetadata(
            name="Churn Co",
            founded_year=2020,
            employee_count=52,
            annual_revenue=3_200_000,
            revenue_band=RevenueBand.ONE_TO_10M,
            region="US",
        ),
        reporting_period=ReportingPeriod(
            type=Granularity.MONTHLY, start=date(2024, 1, 1), end=date(2024, 8, 31)
        ),
        metrics=[
            _metric("churn_rate", periods, churn_values),
            _metric("net_revenue_retention", periods, nrr_values),
            _metric("gross_margin", periods, gm_values),
        ],
    )

    churn_baseline, churn_std = 2.0, 0.8
    churn_trend_points = [
        TrendPoint(period=p, value=v, z_score=round((v - churn_baseline) / churn_std, 3))
        for p, v in zip(periods, churn_values)
    ]
    nrr_baseline, nrr_std = 100.0, 6.0
    nrr_trend_points = [
        TrendPoint(period=p, value=v, z_score=round((v - nrr_baseline) / nrr_std, 3))
        for p, v in zip(periods, nrr_values)
    ]

    churn_anomaly = Anomaly(
        anomaly_id="anom_critical_churn_rate",
        metric_id="churn_rate",
        metric_display_name="Churn Rate (%)",
        category="retention",
        severity_score=82.0,
        severity_label=SeverityLabel.SEVERE,
        deviation=DeviationDetail(
            observed_current=churn_values[-1],
            expected_value=churn_baseline,
            expected_std=churn_std,
            z_score=round((churn_values[-1] - churn_baseline) / churn_std, 3),
            percentile=99.9,
            direction=DeviationDirection.ABOVE_EXPECTED,
        ),
        trend=TrendDetail(
            direction=TrendDirection.DETERIORATING,
            slope=round((churn_values[-1] - churn_values[0]) / (len(churn_values) - 1), 3),
            acceleration=None,
            periods_deviating=6,
            values_over_time=churn_trend_points,
        ),
        correlated_anomalies=["anom_critical_nrr"],
        noise_confidence=0.93,
        context_tags=["churn_related", "retention_leak", "customer_attrition"],
        natural_language_summary=(
            "Churn rate rose from 2.1% to 5.2% over the past 8 months, consistently exceeding "
            "the expected baseline of 2.0% for a company of this profile."
        ),
    )

    nrr_anomaly = Anomaly(
        anomaly_id="anom_critical_nrr",
        metric_id="net_revenue_retention",
        metric_display_name="Net Revenue Retention (%)",
        category="retention",
        severity_score=68.0,
        severity_label=SeverityLabel.CRITICAL,
        deviation=DeviationDetail(
            observed_current=nrr_values[-1],
            expected_value=nrr_baseline,
            expected_std=nrr_std,
            z_score=round((nrr_values[-1] - nrr_baseline) / nrr_std, 3),
            percentile=2.3,
            direction=DeviationDirection.BELOW_EXPECTED,
        ),
        trend=TrendDetail(
            direction=TrendDirection.DETERIORATING,
            slope=round((nrr_values[-1] - nrr_values[0]) / (len(nrr_values) - 1), 3),
            acceleration=None,
            periods_deviating=6,
            values_over_time=nrr_trend_points,
        ),
        correlated_anomalies=["anom_critical_churn_rate"],
        noise_confidence=0.88,
        context_tags=["nrr_drop", "expansion_revenue", "account_health"],
        natural_language_summary=(
            "Net revenue retention fell from 106% to 88% over the past 8 months, below the "
            "expected baseline of 100% for a company of this profile, alongside a concurrent "
            "rise in churn."
        ),
    )

    anomaly_report = AnomalyReport(
        company_id=company_input.company_id,
        sector_id=company_input.sector_id,
        analysis_timestamp=datetime(2024, 8, 31, 12, 0, 0),
        reporting_period=company_input.reporting_period,
        company_profile_summary=CompanyProfileSummary(
            revenue_band=RevenueBand.ONE_TO_10M, employee_count=52, region="US"
        ),
        overall_health_score=38.0,
        anomalies=[churn_anomaly, nrr_anomaly],
        non_anomalous_highlights=[
            HealthyHighlight(
                metric_id="gross_margin",
                status="healthy",
                percentile=62.0,
                note="Gross margin remains stable near the expected baseline for this profile.",
            ),
        ],
        refusal=None,
        metadata=ReportMetadata(
            model_version="0.1.0-mock",
            synthetic_profile_version="tech_saas_v1",
            metrics_analyzed=3,
            metrics_with_anomalies=2,
            metrics_with_missing_data=0,
            skipped_metrics=[],
            processing_time_ms=210,
        ),
    )
    return company_input, anomaly_report


# ---------------------------------------------------------------------------
# refusal — every metric at 4 monthly periods: above the hard block (3) but
# below the trend floor (6), on every submitted metric. Triggers
# RefusalReason.INSUFFICIENT_PERIODS. Regression test for bug #1
# (overall_health_score must be None, not 0.0 or missing).
# ---------------------------------------------------------------------------


def build_refusal() -> tuple[CompanyInput, AnomalyReport]:
    periods = _monthly_periods(2024, 1, 4)

    company_input = CompanyInput(
        company_id="company_refusal_001",
        sector_id=SectorId.TECH_SAAS,
        company_metadata=CompanyMetadata(
            name="Small Test Co",
            founded_year=2023,
            employee_count=30,
            annual_revenue=2_500_000,
            revenue_band=RevenueBand.ONE_TO_10M,
            region="US",
        ),
        reporting_period=ReportingPeriod(
            type=Granularity.MONTHLY, start=date(2024, 1, 1), end=date(2024, 4, 30)
        ),
        metrics=[
            _metric("churn_rate", periods, [2.0, 2.1, 1.9, 2.0]),
            _metric("net_revenue_retention", periods, [100, 101, 99, 100]),
            _metric("gross_margin", periods, [75, 74, 76, 75]),
        ],
    )

    anomaly_report = AnomalyReport(
        company_id=company_input.company_id,
        sector_id=company_input.sector_id,
        analysis_timestamp=datetime(2024, 4, 30, 12, 0, 0),
        reporting_period=company_input.reporting_period,
        company_profile_summary=CompanyProfileSummary(
            revenue_band=RevenueBand.ONE_TO_10M, employee_count=30, region="US"
        ),
        overall_health_score=None,  # NULL ON REFUSAL — bug #1 regression test
        anomalies=[],
        non_anomalous_highlights=[],
        refusal=RefusalDetail(
            reason=RefusalReason.INSUFFICIENT_PERIODS,
            message=(
                "Every submitted metric has fewer than 6 monthly periods, the floor for full "
                "trend analysis. We can't reliably separate a genuine shift from noise with "
                "this little history."
            ),
            suggested_resolution=(
                "Submit at least 6 consecutive monthly periods for at least one metric to "
                "receive a full analysis."
            ),
        ),
        metadata=ReportMetadata(
            model_version="0.1.0-mock",
            synthetic_profile_version="tech_saas_v1",
            metrics_analyzed=3,
            metrics_with_anomalies=0,
            metrics_with_missing_data=0,
            skipped_metrics=[],
            processing_time_ms=45,
        ),
    )
    return company_input, anomaly_report


# ---------------------------------------------------------------------------
# degraded — same input as critical, same AnomalyReport. The difference lives
# entirely in the C3 mock (narrative=None, metadata.degraded=True), so this
# builder just re-exposes the critical fixture.
# ---------------------------------------------------------------------------


def build_degraded() -> tuple[CompanyInput, AnomalyReport]:
    return build_critical()


FIXTURE_BUILDERS = {
    "healthy": build_healthy,
    "critical": build_critical,
    "refusal": build_refusal,
    "degraded": build_degraded,
}
