"""Validation layer (Phase2-Plan T2.4). The most important task in this phase.

Runs in order, accumulating warnings. A blocking check excludes that metric;
it does not abort the whole submission (that's what ParseResult.blocking_errors
is for — a whole-file failure, handled in ingest.py, not here).

Pipeline order within one metric's validation, per T2.4: parse -> dedupe ->
granularity check -> number-format check -> unit-scale check -> range check
-> trim -> interpolate -> count -> classify. Ordering matters: counting
periods happens on the POST-trim, POST-interpolation series, never on raw
uploaded rows — otherwise trimming can silently produce an unexplained refusal.
"""

from datetime import date
from typing import Optional

from api.config.loader import metrics as load_metrics
from api.config.loader import thresholds as load_thresholds
from api.models.internal import ParseWarning, ParseWarningCode
from api.models.shared import DataPoint, Granularity, MetricEntry
from api.parsing.primitives import (
    apply_gap_policy,
    detect_ambiguous_number_format,
    is_mixed_granularity,
    parse_number,
    parse_period,
)


def validate_and_build_metric(
    metric_id: str,
    raw_periods_and_values: list[tuple[str, str]],  # [(raw_period, raw_value), ...]
    confidence: float,
    *,
    as_of: Optional[date] = None,
) -> tuple[Optional[MetricEntry], list[ParseWarning]]:
    """One metric's worth of raw (period, value) cells, already resolved to
    metric_id by the resolver. Returns (entry_or_None, warnings) — None means
    excluded from the submission entirely."""
    cfg = load_metrics()[metric_id]
    warnings: list[ParseWarning] = []

    # 1. Parse periods, collecting any per-period warnings (DATE_TRUNCATED etc).
    parsed: list[tuple[str, Granularity, str]] = []
    for raw_period, raw_value in raw_periods_and_values:
        result = parse_period(raw_period, as_of=as_of)
        if result is None:
            warnings.append(
                ParseWarning(
                    code=ParseWarningCode.SCHEMA_VALIDATION_ERROR,
                    metric_id=metric_id,
                    message=f"Could not parse period '{raw_period}' for {metric_id}; that point was skipped.",
                )
            )
            continue
        period, granularity, period_warning_codes = result
        for code in period_warning_codes:
            warnings.append(
                ParseWarning(
                    code=code,
                    metric_id=metric_id,
                    message=f"{metric_id}, period '{raw_period}': {code.value.replace('_', ' ').lower()}.",
                )
            )
        parsed.append((period, granularity, raw_value))

    if not parsed:
        return None, warnings + [
            ParseWarning(
                code=ParseWarningCode.SHORT_SERIES,
                metric_id=metric_id,
                message=f"{metric_id} has no parseable periods; excluded.",
            )
        ]

    # 2. De-duplicate periods — keep the last occurrence. One summary warning
    # per metric, not one per occurrence: a file with several redundant
    # columns for the same metric can otherwise produce a dozen near-
    # identical lines, defeating the point of a specific, readable warning.
    deduped: dict[str, tuple[str, Granularity, str]] = {}
    duplicate_periods: list[str] = []
    for period, granularity, raw_value in parsed:
        if period in deduped:
            duplicate_periods.append(period)
        deduped[period] = (period, granularity, raw_value)
    parsed = list(deduped.values())
    if duplicate_periods:
        warnings.append(
            ParseWarning(
                code=ParseWarningCode.DUPLICATE_PERIOD,
                metric_id=metric_id,
                message=(
                    f"{metric_id} had {len(duplicate_periods)} duplicate period(s) "
                    f"(e.g. '{duplicate_periods[0]}'); the later value was kept each time."
                ),
            )
        )

    # 3. Granularity — majority within THIS metric must be unanimous; mixed excludes it.
    granularities = [g for _, g, _ in parsed]
    if is_mixed_granularity(granularities):
        found = sorted({g.value for g in granularities})
        return None, warnings + [
            ParseWarning(
                code=ParseWarningCode.MIXED_GRANULARITY,
                metric_id=metric_id,
                message=f"{metric_id} mixes granularities ({', '.join(found)}) across its periods; excluded.",
            )
        ]
    granularity = granularities[0]

    # 4. Number parsing + column-level ambiguous-format detection.
    raw_values = [rv for _, _, rv in parsed]
    non_blank_raw_values = [rv for rv in raw_values if rv.strip()]
    ambiguous_format = (
        len(non_blank_raw_values) >= 2 and detect_ambiguous_number_format(non_blank_raw_values)
    )
    if ambiguous_format:
        warnings.append(
            ParseWarning(
                code=ParseWarningCode.AMBIGUOUS_NUMBER_FORMAT,
                metric_id=metric_id,
                message=(
                    f"{metric_id}'s values mix American and European number formats "
                    "(e.g. 1,234.56 vs 1.234,56) — none of them were trusted; all discarded."
                ),
            )
        )

    original_count = len(parsed)
    parsed_points: list[tuple[str, float]] = []
    if not ambiguous_format:
        for period, _granularity, raw_value in parsed:
            value = parse_number(raw_value)
            if value is not None:
                parsed_points.append((period, value))

    # 5. Distributional unit check — §6.1. Excludes the metric outright: "not
    # silently submitted" (exit criterion 7). No auto-conversion, ever.
    unit = cfg["unit"]
    non_null_values = [v for _, v in parsed_points]
    if unit == "percentage" and len(non_null_values) >= 3 and all(0.0 <= v <= 1.0 for v in non_null_values):
        return None, warnings + [
            ParseWarning(
                code=ParseWarningCode.UNIT_SCALE_SUSPECT,
                metric_id=metric_id,
                message=(
                    f"Every value for {metric_id} falls within 0.0-1.0 — this looks like a "
                    "fraction/percent encoding error, not genuine sub-1% data. Not submitted; "
                    "confirm via /validate before resubmitting."
                ),
            )
        ]

    # 6. Range validation — absurdity bounds, not plausibility bounds. Nulls
    # the point (treated as a gap downstream), doesn't exclude the metric outright.
    valid_min, valid_max = cfg["valid_min"], cfg["valid_max"]
    ranged_points: list[tuple[str, float]] = []
    out_of_range = 0
    for period, value in parsed_points:
        if valid_min <= value <= valid_max:
            ranged_points.append((period, value))
        else:
            out_of_range += 1
    if out_of_range:
        warnings.append(
            ParseWarning(
                code=ParseWarningCode.OUT_OF_RANGE,
                metric_id=metric_id,
                message=(
                    f"{out_of_range} value(s) for {metric_id} fell outside the plausible range "
                    f"[{valid_min}, {valid_max}] and were dropped."
                ),
            )
        )

    sparse_ratio = 1 - (len(ranged_points) / original_count) if original_count else 1.0
    if sparse_ratio > 0.5:
        warnings.append(
            ParseWarning(
                code=ParseWarningCode.SPARSE_SERIES,
                metric_id=metric_id,
                message=f"More than half of {metric_id}'s submitted values were missing or invalid.",
            )
        )

    if not ranged_points:
        return None, warnings + [
            ParseWarning(
                code=ParseWarningCode.SHORT_SERIES,
                metric_id=metric_id,
                message=f"{metric_id} has no valid values after range filtering; excluded.",
            )
        ]

    data_points = [DataPoint(period=p, value=v) for p, v in ranged_points]

    # 7. Gap policy: trim to the most recent contiguous block, then
    # interpolate any small (1-3 period) gaps within what remains.
    filled_points, gap_codes, gap_details = apply_gap_policy(data_points, granularity)
    for code in gap_codes:
        if code == ParseWarningCode.SERIES_TRIMMED:
            message = (
                f"Discarded {gap_details['discarded']} point(s) of {metric_id} before a "
                f"structural break; kept the most recent {gap_details['surviving']}."
            )
        elif code == ParseWarningCode.INTERPOLATION_HEAVY:
            message = (
                f"{gap_details['interpolated_ratio']:.0%} of {metric_id}'s series is "
                "interpolated across several small gaps."
            )
        else:  # INTERPOLATED_POINTS
            message = f"{metric_id} had one or more small gaps filled by linear interpolation."
        warnings.append(ParseWarning(code=code, metric_id=metric_id, message=message))

    # 8. Sanity checks on the final series.
    final_values = [p.value for p in filled_points]
    if len(final_values) > 1 and len(set(final_values)) == 1:
        warnings.append(
            ParseWarning(
                code=ParseWarningCode.CONSTANT_SERIES,
                metric_id=metric_id,
                message=f"Every value for {metric_id} is identical ({final_values[0]}) — check for a copy-paste error.",
            )
        )

    # 9. Minimum periods — counted on the POST-trim, POST-interpolation series.
    n = len(filled_points)
    band = load_thresholds()["min_periods"][granularity.value]
    if n < band["hard_block"]:
        return None, warnings + [
            ParseWarning(
                code=ParseWarningCode.SHORT_SERIES,
                metric_id=metric_id,
                message=(
                    f"{metric_id} has {n} period(s) after trimming, below the hard-block floor "
                    f"of {band['hard_block']} for {granularity.value} data; excluded."
                ),
            )
        ]
    if n <= band["soft_warn"]:
        warnings.append(
            ParseWarning(
                code=ParseWarningCode.SHORT_SERIES,
                metric_id=metric_id,
                message=(
                    f"{metric_id} has only {n} period(s) — below the {band['full_trend']} needed "
                    "for full trend analysis. Submitted anyway, with limited trend detail."
                ),
            )
        )

    entry = MetricEntry(
        metric_id=metric_id,
        granularity=granularity,
        values=filled_points,
        confidence=confidence,
    )
    return entry, warnings


def check_refusal_likely(entries: list[MetricEntry]) -> Optional[ParseWarning]:
    """Cross-cutting pre-submission warning: if EVERY surviving metric is
    below its trend floor, C1 will refuse rather than analyse. Catching this
    before submission turns a confusing refusal into an informed choice."""
    if not entries:
        return None
    thresholds_cfg = load_thresholds()["min_periods"]
    all_below_trend = all(
        len(entry.values) < thresholds_cfg[entry.granularity.value]["full_trend"] for entry in entries
    )
    if not all_below_trend:
        return None
    return ParseWarning(
        code=ParseWarningCode.REFUSAL_LIKELY,
        message=(
            "All your metrics have fewer periods than needed for full trend analysis "
            "(monthly: 6, quarterly: 4, annual: 3), even after accounting for any trimming "
            "across structural breaks. We'll tell you the data is insufficient rather than guess."
        ),
    )
