"""T2.4 — validation layer. Exit criteria 7, 8, 9, 10, 11."""

from datetime import date

from api.models.internal import ParseWarningCode
from api.models.shared import Granularity
from api.parsing.validation import check_refusal_likely, validate_and_build_metric

_AS_OF = date(2026, 8, 26)


def _monthly_cells(start_year: int, start_month: int, values: list[str]) -> list[tuple[str, str]]:
    cells = []
    y, m = start_year, start_month
    for v in values:
        cells.append((f"{y:04d}-{m:02d}", v))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return cells


class TestCleanSeries:
    def test_clean_monthly_series_builds_with_no_warnings(self):
        cells = _monthly_cells(2024, 1, ["2.0", "2.1", "1.9", "2.2", "2.0", "1.8"])
        entry, warnings = validate_and_build_metric("churn_rate", cells, 1.0, as_of=_AS_OF)
        assert entry is not None
        assert len(entry.values) == 6
        assert entry.confidence == 1.0
        assert warnings == []


class TestUnitScaleSuspect:
    def test_all_fraction_values_excluded(self):
        cells = _monthly_cells(2024, 1, ["0.72", "0.71", "0.74", "0.73"])
        entry, warnings = validate_and_build_metric("gross_margin", cells, 1.0, as_of=_AS_OF)
        assert entry is None  # exit criterion 7: not silently submitted
        assert any(w.code == ParseWarningCode.UNIT_SCALE_SUSPECT for w in warnings)

    def test_two_point_series_not_flagged(self):
        # "a two-point churn series of [0.8, 0.9] is plausibly real sub-1% churn"
        cells = _monthly_cells(2024, 1, ["0.8", "0.9"])
        entry, warnings = validate_and_build_metric("churn_rate", cells, 1.0, as_of=_AS_OF)
        assert not any(w.code == ParseWarningCode.UNIT_SCALE_SUSPECT for w in warnings)


class TestRangeValidation:
    def test_out_of_range_value_nulled_metric_retained(self):
        cells = _monthly_cells(2024, 1, ["2.0", "2.1", "999999.0", "1.9", "2.2", "2.0"])
        entry, warnings = validate_and_build_metric("churn_rate", cells, 1.0, as_of=_AS_OF)
        assert entry is not None
        assert any(w.code == ParseWarningCode.OUT_OF_RANGE for w in warnings)


class TestMinimumPeriods:
    def test_below_hard_block_excluded(self):
        cells = _monthly_cells(2024, 1, ["2.0", "2.1"])  # 2 < hard_block(3)
        entry, warnings = validate_and_build_metric("churn_rate", cells, 1.0, as_of=_AS_OF)
        assert entry is None
        assert any(w.code == ParseWarningCode.SHORT_SERIES for w in warnings)

    def test_soft_warn_band_submitted_with_warning(self):
        cells = _monthly_cells(2024, 1, ["2.0", "2.1", "1.9"])  # 3: hard_block<=3<=soft_warn(5)
        entry, warnings = validate_and_build_metric("churn_rate", cells, 1.0, as_of=_AS_OF)
        assert entry is not None
        assert any(w.code == ParseWarningCode.SHORT_SERIES for w in warnings)

    def test_full_trend_no_short_series_warning(self):
        cells = _monthly_cells(2024, 1, ["2.0"] * 6)
        entry, warnings = validate_and_build_metric("churn_rate", cells, 1.0, as_of=_AS_OF)
        assert entry is not None
        assert not any(w.code == ParseWarningCode.SHORT_SERIES for w in warnings)


class TestGapHandling:
    def test_small_gap_interpolated(self):
        cells = _monthly_cells(2024, 1, ["2.0", "2.1", "1.9", "2.0"])
        cells[2] = (cells[2][0], "")  # blank out one point -> a 1-period gap
        entry, warnings = validate_and_build_metric("churn_rate", cells, 1.0, as_of=_AS_OF)
        assert entry is not None
        assert any(p.interpolated for p in entry.values)
        assert any(w.code == ParseWarningCode.INTERPOLATED_POINTS for w in warnings)

    def test_large_gap_trims_and_counts_post_trim(self):
        # 12 monthly points with a break leaving only 2 recent (trim_below_floor.csv shape):
        # exit criterion 11 — period counting happens AFTER trimming.
        early = [(p, "2.0") for p, _ in _monthly_cells(2023, 1, ["x"] * 10)]
        recent = [(p, "2.0") for p, _ in _monthly_cells(2024, 6, ["x"] * 2)]
        entry, warnings = validate_and_build_metric("churn_rate", early + recent, 1.0, as_of=_AS_OF)
        assert entry is None  # 2 surviving points < hard_block(3)
        codes = {w.code for w in warnings}
        assert ParseWarningCode.SERIES_TRIMMED in codes
        assert ParseWarningCode.SHORT_SERIES in codes


class TestMixedGranularity:
    def test_mixed_granularity_excludes_metric(self):
        cells = [("2024-01", "2.0"), ("2024-Q2", "2.1")]
        entry, warnings = validate_and_build_metric("churn_rate", cells, 1.0, as_of=_AS_OF)
        assert entry is None
        assert any(w.code == ParseWarningCode.MIXED_GRANULARITY for w in warnings)


class TestDuplicatePeriod:
    def test_duplicate_period_keeps_last_and_warns(self):
        cells = _monthly_cells(2024, 1, ["2.0", "2.1", "1.9", "2.0", "1.8", "2.2"])
        cells.append(("2024-01", "9.9"))  # duplicate of the first period
        entry, warnings = validate_and_build_metric("churn_rate", cells, 1.0, as_of=_AS_OF)
        assert entry is not None
        jan_point = next(p for p in entry.values if p.period == "2024-01")
        assert jan_point.value == 9.9
        assert any(w.code == ParseWarningCode.DUPLICATE_PERIOD for w in warnings)


class TestConstantSeries:
    def test_constant_series_warns_but_does_not_exclude(self):
        cells = _monthly_cells(2024, 1, ["2.0"] * 6)
        entry, warnings = validate_and_build_metric("churn_rate", cells, 1.0, as_of=_AS_OF)
        assert entry is not None
        assert any(w.code == ParseWarningCode.CONSTANT_SERIES for w in warnings)


class TestAmbiguousNumberFormat:
    def test_mixed_separator_column_discards_all_values(self):
        cells = _monthly_cells(2024, 1, ["1,234.56", "1.234,56", "1,235.00", "1.236,00"])
        entry, warnings = validate_and_build_metric("burn_rate", cells, 1.0, as_of=_AS_OF)
        assert entry is None  # all values discarded -> nothing survives
        assert any(w.code == ParseWarningCode.AMBIGUOUS_NUMBER_FORMAT for w in warnings)


class TestRefusalLikely:
    def test_all_metrics_below_trend_floor_warns(self):
        cells = _monthly_cells(2024, 1, ["2.0", "2.1", "1.9", "2.0"])  # 4 < full_trend(6)
        entry, _ = validate_and_build_metric("churn_rate", cells, 1.0, as_of=_AS_OF)
        warning = check_refusal_likely([entry])
        assert warning is not None
        assert warning.code == ParseWarningCode.REFUSAL_LIKELY

    def test_one_metric_above_trend_floor_no_warning(self):
        cells = _monthly_cells(2024, 1, ["2.0"] * 6)
        entry, _ = validate_and_build_metric("churn_rate", cells, 1.0, as_of=_AS_OF)
        assert check_refusal_likely([entry]) is None

    def test_no_entries_no_warning(self):
        assert check_refusal_likely([]) is None
