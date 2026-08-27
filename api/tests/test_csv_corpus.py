"""T2.8 — the messy-CSV corpus. The most valuable artifact in this phase.
Each fixture asserts the SPECIFIC warning code, not just "it failed" — half
of /validate's value is telling the user which of six possible problems
they have.
"""

from datetime import date
from pathlib import Path

from api.models.internal import FormMetadata, ParseWarningCode
from api.models.shared import SectorId
from api.parsing.builder import build_company_input
from api.parsing.ingest import IngestError, ingest_csv

_CSV_DIR = Path(__file__).parent / "fixtures" / "csv"
_AS_OF = date(2026, 8, 26)


def _load(filename: str) -> bytes:
    return (_CSV_DIR / filename).read_bytes()


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


def _build(filename: str, **form_overrides):
    table = ingest_csv(_load(filename), filename)
    return table, build_company_input(table, _form(**form_overrides), as_of=_AS_OF)


class TestCleanWide:
    def test_parses_correctly(self):
        table, result = _build("clean_wide.csv")
        assert table.detected_shape == "wide"
        assert {m.metric_id for m in result.company_input.metrics} == {"churn_rate", "gross_margin"}
        assert result.warnings == []


class TestCleanTransposed:
    def test_parses_correctly(self):
        table, result = _build("clean_transposed.csv")
        assert table.detected_shape == "transposed"
        assert {m.metric_id for m in result.company_input.metrics} == {"churn_rate", "gross_margin"}


class TestMessyHeaders:
    def test_all_variants_resolve_and_duplicates_are_deduped(self):
        table, result = _build("messy_headers.csv")
        metric_ids = {m.metric_id for m in result.company_input.metrics}
        assert metric_ids == {"monthly_recurring_revenue_growth", "customer_acquisition_cost"}
        mrr_entry = next(m for m in result.company_input.metrics if m.metric_id == "monthly_recurring_revenue_growth")
        assert len(mrr_entry.values) == 6  # 3 redundant columns collapsed to 6 unique periods
        assert all(m.confidence == 0.9 for m in result.company_input.metrics)  # all resolved via alias
        codes = {w.code for w in result.warnings}
        assert ParseWarningCode.DUPLICATE_PERIOD in codes


class TestMessyValues:
    def test_all_value_formats_parse_correctly(self):
        table, result = _build("messy_values.csv")
        cac = next(m for m in result.company_input.metrics if m.metric_id == "customer_acquisition_cost")
        values = {p.period: p.value for p in cac.values}
        assert values["2024-01"] == 4500.0  # "$4,500"
        assert values["2024-05"] == 4450.0
        # "—" and "N/A" became gaps, filled by interpolation (1-2 period gaps)
        assert any(p.interpolated for p in cac.values)

        burn = next(m for m in result.company_input.metrics if m.metric_id == "burn_rate")
        burn_values = {p.period: p.value for p in burn.values}
        assert burn_values["2024-01"] == -500.0  # "(500)" accounting negative
        assert burn_values["2024-02"] == -520.0  # plain negative


class TestFractionPercentages:
    def test_the_money_test(self):
        table, result = _build("fraction_percentages.csv")
        assert result.company_input.metrics == []  # exit criterion 7: not silently submitted
        codes = {w.code for w in result.warnings}
        assert ParseWarningCode.UNIT_SCALE_SUSPECT in codes


class TestShortSeries:
    def test_soft_warn_included_hard_block_excluded(self):
        table, result = _build("short_series.csv")
        metric_ids = {m.metric_id for m in result.company_input.metrics}
        assert metric_ids == {"churn_rate", "gross_margin"}  # 4 periods, soft-warn band
        assert "net_revenue_retention" not in metric_ids  # 2 periods, hard-blocked
        codes_by_metric = {}
        for w in result.warnings:
            codes_by_metric.setdefault(w.metric_id, []).append(w.code)
        assert ParseWarningCode.SHORT_SERIES in codes_by_metric["churn_rate"]
        assert ParseWarningCode.SHORT_SERIES in codes_by_metric["net_revenue_retention"]


class TestAllShort:
    def test_warns_about_incoming_refusal(self):
        table, result = _build("all_short.csv")
        assert len(result.company_input.metrics) == 3  # all survive (soft-warn band)
        codes = {w.code for w in result.warnings}
        assert ParseWarningCode.REFUSAL_LIKELY in codes


class TestUnknownColumns:
    def test_nonsense_columns_excluded(self):
        table, result = _build("unknown_columns.csv")
        metric_ids = {m.metric_id for m in result.company_input.metrics}
        assert metric_ids == {"churn_rate", "gross_margin"}
        unknown_warnings = [w for w in result.warnings if w.code == ParseWarningCode.UNKNOWN_METRIC]
        assert len(unknown_warnings) == 3  # Foo, Bar, Baz


class TestGapsSmall:
    def test_one_and_three_period_gaps_both_interpolated(self):
        table, result = _build("gaps_small.csv")
        churn = next(m for m in result.company_input.metrics if m.metric_id == "churn_rate")
        gm = next(m for m in result.company_input.metrics if m.metric_id == "gross_margin")
        assert sum(p.interpolated for p in churn.values) == 1
        assert sum(p.interpolated for p in gm.values) == 3
        codes = {w.code for w in result.warnings}
        assert ParseWarningCode.INTERPOLATED_POINTS in codes
        assert ParseWarningCode.SERIES_TRIMMED not in codes


class TestStructuralBreak:
    def test_trims_to_recent_block_and_reports_discarded(self):
        table, result = _build("structural_break.csv")
        entry = result.company_input.metrics[0]
        assert len(entry.values) == 4
        assert {p.period for p in entry.values} == {"2024-11", "2024-12", "2025-01", "2025-02"}
        trim_warning = next(w for w in result.warnings if w.code == ParseWarningCode.SERIES_TRIMMED)
        assert "5" in trim_warning.message  # discarded 5


class TestTrimBelowFloor:
    def test_trims_then_hard_blocks(self):
        table, result = _build("trim_below_floor.csv")
        assert result.company_input.metrics == []
        codes = {w.code for w in result.warnings}
        assert ParseWarningCode.SERIES_TRIMMED in codes
        assert ParseWarningCode.SHORT_SERIES in codes


class TestInterpolationHeavy:
    def test_warns_without_any_single_gap_tripping_trim(self):
        table, result = _build("interpolation_heavy.csv")
        entry = result.company_input.metrics[0]
        codes = {w.code for w in result.warnings}
        assert ParseWarningCode.INTERPOLATION_HEAVY in codes
        assert ParseWarningCode.SERIES_TRIMMED not in codes


class TestMixedGranularity:
    def test_metric_excluded(self):
        table, result = _build("mixed_granularity.csv")
        assert result.company_input.metrics == []
        codes = {w.code for w in result.warnings}
        assert ParseWarningCode.MIXED_GRANULARITY in codes


class TestWrongSector:
    def test_retail_metrics_under_tech_saas_excluded(self):
        table, result = _build("wrong_sector.csv", sector_id=SectorId.TECH_SAAS)
        assert result.company_input.metrics == []
        codes = {w.code for w in result.warnings}
        assert ParseWarningCode.SECTOR_MISMATCH in codes

    def test_same_file_resolves_fine_under_retail(self):
        table, result = _build("wrong_sector.csv", sector_id=SectorId.RETAIL)
        metric_ids = {m.metric_id for m in result.company_input.metrics}
        assert metric_ids == {"inventory_turnover", "average_order_value"}


class TestGarbage:
    def test_fails_cleanly_never_a_traceback(self):
        try:
            ingest_csv(_load("garbage.csv"), "garbage.csv")
            raised = False
        except IngestError:
            raised = True
        except Exception as exc:  # pragma: no cover - the failure mode itself
            raise AssertionError(f"garbage.csv raised {type(exc).__name__}, not a clean IngestError") from exc
        assert raised
