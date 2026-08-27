"""T2.5 — CompanyInput builder."""

from datetime import date

from api.models.internal import FormMetadata, ParseWarningCode
from api.models.shared import RevenueBand, SectorId
from api.parsing.builder import build_company_input
from api.parsing.ingest import ingest_csv

_AS_OF = date(2026, 8, 26)

WIDE_CLEAN_CSV = b"""Month,Churn,GM
2024-01,2.0,75.0
2024-02,2.1,74.5
2024-03,1.9,74.8
2024-04,2.2,75.1
2024-05,2.0,74.9
2024-06,1.8,75.3
"""


def _form(**overrides) -> FormMetadata:
    defaults = dict(
        company_name="Acme Co",
        sector_id=SectorId.TECH_SAAS,
        employee_count=40,
        region="US",
        annual_revenue=4_000_000,
    )
    defaults.update(overrides)
    return FormMetadata(**defaults)


class TestCleanBuild:
    def test_builds_company_input_with_clean_csv_confidence(self):
        table = ingest_csv(WIDE_CLEAN_CSV, "clean.csv")
        result = build_company_input(table, _form(), as_of=_AS_OF)
        assert result.company_input is not None
        assert {m.metric_id for m in result.company_input.metrics} == {"churn_rate", "gross_margin"}
        assert all(m.confidence == 0.9 for m in result.company_input.metrics)
        assert result.blocking_errors == []

    def test_revenue_band_derived_from_annual_revenue_overrides_user_band(self):
        table = ingest_csv(WIDE_CLEAN_CSV, "clean.csv")
        result = build_company_input(
            table, _form(annual_revenue=15_000_000, revenue_band=RevenueBand.UNDER_1M), as_of=_AS_OF
        )
        assert result.company_input.company_metadata.revenue_band == RevenueBand.TEN_TO_100M

    def test_revenue_band_trusted_when_annual_revenue_absent(self):
        table = ingest_csv(WIDE_CLEAN_CSV, "clean.csv")
        result = build_company_input(
            table, _form(annual_revenue=None, revenue_band=RevenueBand.OVER_100M), as_of=_AS_OF
        )
        assert result.company_input.company_metadata.revenue_band == RevenueBand.OVER_100M

    def test_company_id_is_deterministic(self):
        table = ingest_csv(WIDE_CLEAN_CSV, "clean.csv")
        r1 = build_company_input(table, _form(), as_of=_AS_OF)
        r2 = build_company_input(table, _form(), as_of=_AS_OF)
        assert r1.company_input.company_id == r2.company_input.company_id


class TestUnknownColumn:
    def test_unknown_column_excluded_and_warned(self):
        csv_bytes = b"""Month,Churn Rate,Total Widgets Frobnicated\n2024-01,2.0,99\n2024-02,2.1,98\n2024-03,1.9,97\n"""
        table = ingest_csv(csv_bytes, "unknown.csv")
        result = build_company_input(table, _form(), as_of=_AS_OF)
        metric_ids = {m.metric_id for m in result.company_input.metrics}
        assert "total_widgets_frobnicated" not in str(metric_ids)
        codes = {w.code for w in result.warnings}
        assert ParseWarningCode.UNKNOWN_METRIC in codes


class TestFractionPercentages:
    def test_fraction_encoded_percentage_excluded(self):
        csv_bytes = b"""Month,Gross Margin\n2024-01,0.74\n2024-02,0.72\n2024-03,0.75\n2024-04,0.73\n"""
        table = ingest_csv(csv_bytes, "fraction.csv")
        result = build_company_input(table, _form(), as_of=_AS_OF)
        assert result.company_input.metrics == []
        codes = {w.code for w in result.warnings}
        assert ParseWarningCode.UNIT_SCALE_SUSPECT in codes


class TestMappingOverrides:
    def test_override_forces_resolution_and_raises_confidence_band(self):
        csv_bytes = b"""Month,Weird Custom Header\n2024-01,2.0\n2024-02,2.1\n2024-03,1.9\n2024-04,2.2\n2024-05,2.0\n2024-06,1.8\n"""
        table = ingest_csv(csv_bytes, "override.csv")
        result = build_company_input(
            table, _form(), mapping_overrides={"Weird Custom Header": "churn_rate"}, as_of=_AS_OF
        )
        assert result.company_input.metrics[0].metric_id == "churn_rate"
        assert result.company_input.metrics[0].confidence == 0.75

    def test_override_naming_unknown_metric_id_is_ignored_not_a_crash(self):
        # Regression test: a bad override used to reach load_metrics()[metric_id]
        # inside validate_and_build_metric and raise an unhandled KeyError —
        # a forceable 500 (Phase 1 exit criterion 6). Must degrade to a
        # warning instead, falling back to normal resolution.
        csv_bytes = b"""Month,Weird Custom Header\n2024-01,2.0\n2024-02,2.1\n2024-03,1.9\n2024-04,2.2\n2024-05,2.0\n2024-06,1.8\n"""
        table = ingest_csv(csv_bytes, "override.csv")
        result = build_company_input(
            table, _form(), mapping_overrides={"Weird Custom Header": "not_a_real_metric_id"}, as_of=_AS_OF
        )
        assert result.company_input.metrics == []  # falls back to normal resolution -> unresolved -> excluded
        codes = {w.code for w in result.warnings}
        assert ParseWarningCode.UNKNOWN_METRIC in codes


class TestManualFormConfidence:
    def test_form_shape_confidence_is_always_1(self):
        from api.parsing.ingest import ManualMetricEntry, ingest_form

        entries = [ManualMetricEntry("churn_rate", {"2024-01": "2.0", "2024-02": "2.1", "2024-03": "1.9"})]
        table = ingest_form(entries)
        result = build_company_input(table, _form(), as_of=_AS_OF)
        assert result.company_input.metrics[0].confidence == 1.0
