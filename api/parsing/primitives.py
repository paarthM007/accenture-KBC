"""Parsing primitives (Phase2-Plan T2.1). Pure functions, no I/O, exhaustively
unit-tested — everything downstream depends on these.
"""

import re
from collections import Counter
from datetime import date
from typing import Optional

from api.models.internal import ParseWarningCode
from api.models.shared import DataPoint, Granularity

_MISSING_TOKENS = {"", "-", "—", "–", "n/a", "na", "null", "none"}
_MAGNITUDE = {"k": 1_000.0, "m": 1_000_000.0, "b": 1_000_000_000.0}
_MAGNITUDE_SUFFIX_RE = re.compile(r"^([+-]?[\d.,\s]+)\s*([KkMmBb])$")
_CURRENCY_RE = re.compile(r"[$€£¥]")

_MONTH_NAMES = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


# ---------------------------------------------------------------------------
# parse_number
# ---------------------------------------------------------------------------


def parse_number(raw: Optional[str]) -> Optional[float]:
    """"72%" -> 72.0 (strip the sign, never divide — C1's baselines are
    whole-number percentages; dividing here recreates the exact bug the
    distributional unit check exists to catch)."""
    if raw is None:
        return None
    s = raw.strip()
    if s.lower() in _MISSING_TOKENS:
        return None

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()

    s = s.replace("%", "").strip()
    s = _CURRENCY_RE.sub("", s).strip()

    magnitude = 1.0
    m = _MAGNITUDE_SUFFIX_RE.match(s)
    if m:
        s = m.group(1).strip()
        magnitude = _MAGNITUDE[m.group(2).lower()]

    s = s.replace(" ", "")  # space as a European thousands separator
    if not s:
        return None
    if s[0] in "+-":
        sign, s = s[0], s[1:]
    else:
        sign = ""

    s = _normalize_separators(s)

    try:
        value = float(sign + s)
    except ValueError:
        return None

    value *= magnitude
    if negative:
        value = -abs(value)
    return value


def _normalize_separators(s: str) -> str:
    """Best-effort per-cell American/European separator resolution. Column-
    level ambiguity detection is a separate concern — see
    detect_ambiguous_number_format() — because a single cell like "1,234"
    can't be judged correctly in isolation."""
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            return s.replace(".", "").replace(",", ".")  # European: . thousands, , decimal
        return s.replace(",", "")  # American: , thousands, . decimal
    if "," in s:
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            return s.replace(",", ".")  # bare European decimal, e.g. "1234,56"
        return s.replace(",", "")  # thousands separator, e.g. "1,234"
    return s


def detect_ambiguous_number_format(raw_values: list[str]) -> bool:
    """True when a column mixes American- and European-style separators
    (Phase2-Plan T2.1: "detect mixed usage across the column and warn rather
    than guessing per cell")."""
    saw_american = False
    saw_european = False
    for raw in raw_values:
        s = raw.strip().replace(" ", "")
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                saw_european = True
            else:
                saw_american = True
        elif re.search(r",\d{1,2}$", s):
            saw_european = True
        elif re.search(r"\.\d{3}$", s) and "," not in s:
            # "1.234" with exactly 3 trailing digits and no comma anywhere is
            # itself ambiguous (European thousands-dot vs a 3dp decimal), but
            # on its own doesn't prove mixed usage — only co-occurrence with a
            # clearer signal elsewhere in the column does.
            pass
    return saw_american and saw_european


# ---------------------------------------------------------------------------
# parse_period
# ---------------------------------------------------------------------------

# Returns (normalized_period, granularity, warning_codes). Extended beyond the
# plan's illustrative `tuple[str, Granularity] | None` signature with a
# warning-code list, since DATE_TRUNCATED / TWO_DIGIT_YEAR_FUTURE need a way
# out and parse_period is the only place with the raw string in hand.
ParsedPeriod = tuple[str, Granularity, list[ParseWarningCode]]

_FULL_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_YYYY_MM_RE = re.compile(r"^(\d{4})-(\d{1,2})$")
_YYYY_SLASH_MM_RE = re.compile(r"^(\d{4})/(\d{1,2})$")
_MM_SLASH_YYYY_RE = re.compile(r"^(\d{1,2})/(\d{4})$")
_MONTH_NAME_YEAR_RE = re.compile(r"^([A-Za-z]+)\.?[\s,]+(\d{4})$")
_MONTH_DASH_YY_RE = re.compile(r"^([A-Za-z]+)-(\d{2,4})$")

_Q_YEAR_RE = re.compile(r"^Q([1-4])[\s,]+(\d{4})$", re.IGNORECASE)
_YEAR_Q_RE = re.compile(r"^(\d{4})[\s-]?Q([1-4])$", re.IGNORECASE)
_FY_Q_RE = re.compile(r"^FY\s*(\d{2,4})\s*Q([1-4])$", re.IGNORECASE)

_YEAR_RE = re.compile(r"^(\d{4})$")
_FY_RE = re.compile(r"^FY\s*(\d{2,4})$", re.IGNORECASE)


def _expand_two_digit_year(yy: int, *, as_of: date) -> tuple[int, list[ParseWarningCode]]:
    year = 2000 + yy
    warnings = []
    if year > as_of.year + 1:
        warnings.append(ParseWarningCode.TWO_DIGIT_YEAR_FUTURE)
    return year, warnings


def parse_period(raw: str, *, as_of: Optional[date] = None) -> Optional[ParsedPeriod]:
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    as_of = as_of or date.today()

    m = _FULL_DATE_RE.match(s)
    if m:
        year, month, _day = (int(g) for g in m.groups())
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}", Granularity.MONTHLY, [ParseWarningCode.DATE_TRUNCATED]

    m = _YYYY_MM_RE.match(s)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}", Granularity.MONTHLY, []

    m = _YYYY_SLASH_MM_RE.match(s)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}", Granularity.MONTHLY, []

    m = _MM_SLASH_YYYY_RE.match(s)
    if m:
        month, year = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}", Granularity.MONTHLY, []

    m = _MONTH_NAME_YEAR_RE.match(s)
    if m and m.group(1).lower() in _MONTH_NAMES:
        month = _MONTH_NAMES[m.group(1).lower()]
        year = int(m.group(2))
        return f"{year:04d}-{month:02d}", Granularity.MONTHLY, []

    m = _MONTH_DASH_YY_RE.match(s)
    if m and m.group(1).lower() in _MONTH_NAMES:
        month = _MONTH_NAMES[m.group(1).lower()]
        year_raw = m.group(2)
        warnings: list[ParseWarningCode] = []
        if len(year_raw) == 4:
            year = int(year_raw)
        else:
            year, warnings = _expand_two_digit_year(int(year_raw), as_of=as_of)
        return f"{year:04d}-{month:02d}", Granularity.MONTHLY, warnings

    m = _Q_YEAR_RE.match(s)
    if m:
        quarter, year = int(m.group(1)), int(m.group(2))
        return f"{year:04d}-Q{quarter}", Granularity.QUARTERLY, []

    m = _YEAR_Q_RE.match(s)
    if m:
        year, quarter = int(m.group(1)), int(m.group(2))
        return f"{year:04d}-Q{quarter}", Granularity.QUARTERLY, []

    m = _FY_Q_RE.match(s)
    if m:
        year_raw, quarter = m.group(1), int(m.group(2))
        warnings = []
        if len(year_raw) == 4:
            year = int(year_raw)
        else:
            year, warnings = _expand_two_digit_year(int(year_raw), as_of=as_of)
        return f"{year:04d}-Q{quarter}", Granularity.QUARTERLY, warnings

    m = _FY_RE.match(s)
    if m:
        year_raw = m.group(1)
        warnings = []
        if len(year_raw) == 4:
            year = int(year_raw)
        else:
            year, warnings = _expand_two_digit_year(int(year_raw), as_of=as_of)
        return f"{year:04d}", Granularity.ANNUAL, warnings

    m = _YEAR_RE.match(s)
    if m:
        return f"{int(m.group(1)):04d}", Granularity.ANNUAL, []

    return None


# ---------------------------------------------------------------------------
# infer_granularity
# ---------------------------------------------------------------------------


def infer_granularity(granularities: list[Granularity]) -> Optional[Granularity]:
    """Majority vote. Returns None if the input is empty; callers check for
    a MIXED_GRANULARITY condition separately via is_mixed_granularity()."""
    if not granularities:
        return None
    return Counter(granularities).most_common(1)[0][0]


def is_mixed_granularity(granularities: list[Granularity]) -> bool:
    return len(set(granularities)) > 1


# ---------------------------------------------------------------------------
# detect_gaps
# ---------------------------------------------------------------------------


def _period_sort_key(period: str, granularity: Granularity) -> tuple[int, int]:
    if granularity == Granularity.MONTHLY:
        year, month = period.split("-")
        return int(year), int(month)
    if granularity == Granularity.QUARTERLY:
        year, q = period.split("-Q")
        return int(year), int(q)
    return int(period), 0  # ANNUAL


def _next_period(period: str, granularity: Granularity) -> str:
    if granularity == Granularity.MONTHLY:
        year, month = (int(x) for x in period.split("-"))
        month += 1
        if month > 12:
            month = 1
            year += 1
        return f"{year:04d}-{month:02d}"
    if granularity == Granularity.QUARTERLY:
        year, q = period.split("-Q")
        year, q = int(year), int(q) + 1
        if q > 4:
            q = 1
            year += 1
        return f"{year:04d}-Q{q}"
    return f"{int(period) + 1:04d}"  # ANNUAL


def detect_gaps(periods: list[str], granularity: Granularity) -> list[str]:
    """Return every missing period in the span between the earliest and
    latest submitted period, in chronological order."""
    if len(periods) < 2:
        return []
    ordered = sorted(set(periods), key=lambda p: _period_sort_key(p, granularity))
    gaps: list[str] = []
    cursor = ordered[0]
    present = set(ordered)
    while cursor != ordered[-1]:
        cursor = _next_period(cursor, granularity)
        if cursor not in present:
            gaps.append(cursor)
    return gaps


# ---------------------------------------------------------------------------
# trim_to_contiguous_block
# ---------------------------------------------------------------------------


def trim_to_contiguous_block(
    points: list[DataPoint], granularity: Granularity, *, break_threshold: int = 4
) -> tuple[list[DataPoint], int]:
    """Find the most recent run of periods with no gap of `break_threshold`
    or more consecutive missing periods; return it plus the count of
    discarded points. The most recent block wins even when it's smaller —
    a structural break means the earlier regime isn't comparable."""
    if not points:
        return [], 0

    ordered = sorted(points, key=lambda p: _period_sort_key(p.period, granularity))

    # Walk backward from the most recent point, cutting the first time the
    # gap to the previous point is >= break_threshold.
    block_start = len(ordered) - 1
    for i in range(len(ordered) - 1, 0, -1):
        prev_period, curr_period = ordered[i - 1].period, ordered[i].period
        gap = _count_gap(prev_period, curr_period, granularity)
        if gap >= break_threshold:
            block_start = i
            break
        block_start = i - 1

    kept = ordered[block_start:]
    discarded = len(ordered) - len(kept)
    return kept, discarded


def _count_gap(prev_period: str, curr_period: str, granularity: Granularity) -> int:
    """Number of missing periods strictly between prev_period and curr_period."""
    count = 0
    cursor = prev_period
    while cursor != curr_period:
        cursor = _next_period(cursor, granularity)
        if cursor != curr_period:
            count += 1
        if count > 10_000:  # defensive guard against a malformed period pair looping forever
            break
    return count


# ---------------------------------------------------------------------------
# apply_gap_policy
# ---------------------------------------------------------------------------


def apply_gap_policy(
    points: list[DataPoint], granularity: Granularity
) -> tuple[list[DataPoint], list[ParseWarningCode], dict]:
    """Fill & Flag, confirmed by C1: 1-3 period gaps are linearly
    interpolated with interpolated=True; 4+ period gaps trim to the most
    recent contiguous block. Trim first, then interpolate only within what
    remains (Phase2-Plan T2.1).

    Returns (final_points, warning_codes, details) where details carries the
    numbers a caller needs to build the actual ParseWarning messages
    (discarded count, interpolated_ratio, etc).
    """
    if len(points) < 2:
        return points, [], {}

    trimmed, discarded = trim_to_contiguous_block(points, granularity)
    warning_codes: list[ParseWarningCode] = []
    details: dict = {}

    if discarded > 0:
        warning_codes.append(ParseWarningCode.SERIES_TRIMMED)
        details["discarded"] = discarded
        details["surviving"] = len(trimmed)

    filled = _interpolate_small_gaps(trimmed, granularity)
    interpolated_count = sum(1 for p in filled if p.interpolated)
    interpolated_ratio = interpolated_count / len(filled) if filled else 0.0
    details["interpolated_ratio"] = interpolated_ratio

    if interpolated_count > 0:
        warning_codes.append(ParseWarningCode.INTERPOLATED_POINTS)
    if interpolated_ratio > 0.3:
        warning_codes.append(ParseWarningCode.INTERPOLATION_HEAVY)

    return filled, warning_codes, details


def _interpolate_small_gaps(points: list[DataPoint], granularity: Granularity) -> list[DataPoint]:
    if len(points) < 2:
        return points

    ordered = sorted(points, key=lambda p: _period_sort_key(p.period, granularity))
    result: list[DataPoint] = [ordered[0]]

    for prev, curr in zip(ordered, ordered[1:]):
        gap = _count_gap(prev.period, curr.period, granularity)
        if gap == 0:
            result.append(curr)
            continue
        # gap is guaranteed < 4 here — trim_to_contiguous_block already
        # removed any run containing a >=4 gap before this function runs.
        cursor = prev.period
        for step in range(1, gap + 1):
            cursor = _next_period(cursor, granularity)
            fraction = step / (gap + 1)
            value = prev.value + (curr.value - prev.value) * fraction
            result.append(DataPoint(period=cursor, value=value, interpolated=True))
        result.append(curr)

    return result
