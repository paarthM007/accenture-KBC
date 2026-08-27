"""T2.1 — parsing primitives, exhaustively unit-tested per Phase2-Plan tables
and exit criteria 4, 5, 10, 11."""

from datetime import date

import pytest

from api.models.internal import ParseWarningCode
from api.models.shared import DataPoint, Granularity
from api.parsing.primitives import (
    apply_gap_policy,
    detect_ambiguous_number_format,
    detect_gaps,
    infer_granularity,
    is_mixed_granularity,
    parse_number,
    parse_period,
    trim_to_contiguous_block,
)


class TestParseNumber:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("4500", 4500.0),
            ("$4,500.00", 4500.0),
            ("72%", 72.0),
            ("(500)", -500.0),
            ("1.2M", 1_200_000.0),
            ("1.2K", 1_200.0),
            ("1,234.5", 1234.5),
            ("1 234,56", 1234.56),
        ],
    )
    def test_known_values(self, raw, expected):
        assert parse_number(raw) == pytest.approx(expected)

    @pytest.mark.parametrize("raw", ["—", "N/A", "-", "", "null", "n/a", None])
    def test_missing_tokens_return_none(self, raw):
        assert parse_number(raw) is None

    def test_percent_never_divided(self):
        # The exact bug §6.1 exists to catch: dividing "72%" by 100 would
        # produce 0.72, indistinguishable from a genuine fraction encoding error.
        assert parse_number("72%") == 72.0
        assert parse_number("0.72") == 0.72  # untouched — this IS the ambiguous case

    def test_negative_currency(self):
        assert parse_number("-$500") == -500.0

    def test_billion_suffix(self):
        assert parse_number("2.5B") == pytest.approx(2_500_000_000.0)


class TestDetectAmbiguousNumberFormat:
    def test_pure_american_column_not_flagged(self):
        assert detect_ambiguous_number_format(["1,234.56", "2,000.00", "999.99"]) is False

    def test_pure_european_column_not_flagged(self):
        assert detect_ambiguous_number_format(["1.234,56", "2.000,00", "999,99"]) is False

    def test_mixed_column_flagged(self):
        assert detect_ambiguous_number_format(["1,234.56", "1.234,56"]) is True


class TestParsePeriod:
    _AS_OF = date(2026, 8, 26)

    @pytest.mark.parametrize(
        "raw,expected_period,expected_granularity",
        [
            ("2026-01", "2026-01", Granularity.MONTHLY),
            ("Jan 2026", "2026-01", Granularity.MONTHLY),
            ("January 2026", "2026-01", Granularity.MONTHLY),
            ("01/2026", "2026-01", Granularity.MONTHLY),
            ("Jan-26", "2026-01", Granularity.MONTHLY),
            ("2026/01", "2026-01", Granularity.MONTHLY),
            ("Q1 2026", "2026-Q1", Granularity.QUARTERLY),
            ("2026-Q1", "2026-Q1", Granularity.QUARTERLY),
            ("2026Q1", "2026-Q1", Granularity.QUARTERLY),
            ("FY26 Q1", "2026-Q1", Granularity.QUARTERLY),
            ("2026", "2026", Granularity.ANNUAL),
            ("FY2026", "2026", Granularity.ANNUAL),
            ("FY26", "2026", Granularity.ANNUAL),
        ],
    )
    def test_normalizes_correctly(self, raw, expected_period, expected_granularity):
        result = parse_period(raw, as_of=self._AS_OF)
        assert result is not None
        period, granularity, _warnings = result
        assert period == expected_period
        assert granularity == expected_granularity

    def test_full_date_truncates_with_warning(self):
        period, granularity, warnings = parse_period("2026-01-15", as_of=self._AS_OF)
        assert period == "2026-01"
        assert granularity == Granularity.MONTHLY
        assert ParseWarningCode.DATE_TRUNCATED in warnings

    def test_two_digit_year_far_future_warns(self):
        # as_of is 2026; "Jan-40" -> 2040, more than a year out.
        period, granularity, warnings = parse_period("Jan-40", as_of=self._AS_OF)
        assert period == "2040-01"
        assert ParseWarningCode.TWO_DIGIT_YEAR_FUTURE in warnings

    def test_two_digit_year_near_term_no_warning(self):
        period, granularity, warnings = parse_period("Jan-26", as_of=self._AS_OF)
        assert period == "2026-01"
        assert warnings == []

    def test_unparseable_returns_none(self):
        assert parse_period("not a period", as_of=self._AS_OF) is None
        assert parse_period("", as_of=self._AS_OF) is None


class TestGranularityInference:
    def test_majority_wins(self):
        g = [Granularity.MONTHLY, Granularity.MONTHLY, Granularity.QUARTERLY]
        assert infer_granularity(g) == Granularity.MONTHLY

    def test_empty_returns_none(self):
        assert infer_granularity([]) is None

    def test_mixed_detected(self):
        assert is_mixed_granularity([Granularity.MONTHLY, Granularity.QUARTERLY]) is True
        assert is_mixed_granularity([Granularity.MONTHLY, Granularity.MONTHLY]) is False


class TestDetectGaps:
    def test_no_gap(self):
        assert detect_gaps(["2024-01", "2024-02", "2024-03"], Granularity.MONTHLY) == []

    def test_single_gap(self):
        assert detect_gaps(["2024-01", "2024-03"], Granularity.MONTHLY) == ["2024-02"]

    def test_multi_month_gap(self):
        gaps = detect_gaps(["2024-01", "2024-05"], Granularity.MONTHLY)
        assert gaps == ["2024-02", "2024-03", "2024-04"]

    def test_quarterly_gap(self):
        assert detect_gaps(["2024-Q1", "2024-Q3"], Granularity.QUARTERLY) == ["2024-Q2"]


class TestTrimToContiguousBlock:
    def test_no_break_keeps_everything(self):
        points = [DataPoint(period=p, value=1.0) for p in ["2024-01", "2024-02", "2024-03"]]
        kept, discarded = trim_to_contiguous_block(points, Granularity.MONTHLY)
        assert discarded == 0
        assert len(kept) == 3

    def test_structural_break_keeps_recent_block(self):
        # Jan-May (5), 5-month gap (Jun-Oct missing), Nov-Feb next year (4) — the
        # exact structural_break.csv fixture shape: discard 5, keep 4.
        early = [DataPoint(period=p, value=1.0) for p in ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05"]]
        recent = [DataPoint(period=p, value=2.0) for p in ["2024-11", "2024-12", "2025-01", "2025-02"]]
        kept, discarded = trim_to_contiguous_block(early + recent, Granularity.MONTHLY)
        assert discarded == 5
        assert [p.period for p in kept] == ["2024-11", "2024-12", "2025-01", "2025-02"]

    def test_small_gap_does_not_trigger_trim(self):
        points = [DataPoint(period=p, value=1.0) for p in ["2024-01", "2024-02", "2024-05"]]  # 2-period gap
        kept, discarded = trim_to_contiguous_block(points, Granularity.MONTHLY)
        assert discarded == 0
        assert len(kept) == 3


class TestApplyGapPolicy:
    def test_small_gap_interpolates(self):
        points = [
            DataPoint(period="2024-01", value=10.0),
            DataPoint(period="2024-04", value=40.0),  # 2-period gap: Feb, Mar
        ]
        filled, codes, details = apply_gap_policy(points, Granularity.MONTHLY)
        assert len(filled) == 4
        by_period = {p.period: p for p in filled}
        assert by_period["2024-02"].interpolated is True
        assert by_period["2024-02"].value == pytest.approx(20.0)
        assert by_period["2024-03"].interpolated is True
        assert by_period["2024-03"].value == pytest.approx(30.0)
        assert ParseWarningCode.INTERPOLATED_POINTS in codes
        assert ParseWarningCode.SERIES_TRIMMED not in codes

    def test_large_gap_trims_not_interpolates(self):
        early = [DataPoint(period=p, value=1.0) for p in ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05"]]
        recent = [DataPoint(period=p, value=2.0) for p in ["2024-11", "2024-12", "2025-01", "2025-02"]]
        filled, codes, details = apply_gap_policy(early + recent, Granularity.MONTHLY)
        assert len(filled) == 4  # trimmed, not bridged
        assert ParseWarningCode.SERIES_TRIMMED in codes
        assert details["discarded"] == 5

    def test_interpolation_heavy_flagged(self):
        # Three separate two-period gaps in a twelve-point series (Phase2-Plan
        # T2.1's own example): 6 real points + 6 interpolated = 0.5 ratio > 0.3.
        real_periods = ["2024-01", "2024-04", "2024-07", "2024-10", "2025-01", "2025-04"]
        points = [DataPoint(period=p, value=float(i)) for i, p in enumerate(real_periods)]
        filled, codes, details = apply_gap_policy(points, Granularity.MONTHLY)
        assert details["interpolated_ratio"] > 0.3
        assert ParseWarningCode.INTERPOLATION_HEAVY in codes
        assert ParseWarningCode.SERIES_TRIMMED not in codes  # no single gap hit 4+

    def test_no_gap_no_warnings(self):
        points = [DataPoint(period=p, value=1.0) for p in ["2024-01", "2024-02", "2024-03"]]
        filled, codes, details = apply_gap_policy(points, Granularity.MONTHLY)
        assert filled == points
        assert codes == []
