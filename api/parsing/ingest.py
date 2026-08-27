"""Shape detection & ingestion (Phase2-Plan T2.2 / §2).

Users produce two shapes — wide (periods as rows) and transposed (metrics as
rows). Both are auto-detected and normalized into one internal long form,
(period, source_label, raw_value), immediately. Everything downstream works
on that, so shape handling exists in exactly one function.
"""

import csv
import io

import pandas as pd

from api.config.settings import settings
from api.models.internal import ParseWarning, ParseWarningCode, RawCell, RawTable
from api.parsing.primitives import parse_period

MAX_COLUMNS = 200
MAX_ROWS = 10_000
_SHAPE_DETECTION_THRESHOLD = 0.6


class IngestError(Exception):
    """A whole-file failure that blocks parsing entirely — size/shape limits,
    an unreadable file, or AMBIGUOUS_SHAPE. Caller puts str(exc) straight
    into ParseResult.blocking_errors; the pipeline never starts."""


def _decode(file_bytes: bytes) -> tuple[str, list[ParseWarning]]:
    try:
        return file_bytes.decode("utf-8-sig"), []
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1"), [
            ParseWarning(
                code=ParseWarningCode.SCHEMA_VALIDATION_ERROR,
                message="File was not valid UTF-8; decoded as Latin-1 instead. Re-export as UTF-8 if values look wrong.",
            )
        ]


def _sniff_delimiter(text: str) -> str:
    sample = text[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        return ","


def _is_blank(value: object) -> bool:
    return str(value).strip() == ""


def _drop_empty_rows_and_columns(df: pd.DataFrame) -> pd.DataFrame:
    row_mask = ~df.apply(lambda row: all(_is_blank(v) for v in row), axis=1)
    df = df.loc[row_mask]
    col_mask = ~df.apply(lambda col: all(_is_blank(v) for v in col), axis=0)
    return df.loc[:, col_mask]


def _detect_shape(df: pd.DataFrame) -> str:
    """Detection heuristic, in order (Phase2-Plan §2):
    1. >=60% of header cells (excluding the first) parse as periods -> transposed
    2. else >=60% of first-column values parse as periods -> wide
    3. else -> AMBIGUOUS_SHAPE, raise with the first three rows shown
    """
    headers = [str(h) for h in df.columns[1:]]
    header_hits = sum(1 for h in headers if parse_period(h) is not None)
    header_ratio = header_hits / len(headers) if headers else 0.0
    if header_ratio >= _SHAPE_DETECTION_THRESHOLD:
        return "transposed"

    first_col_values = [str(v) for v in df.iloc[:, 0].tolist()]
    first_col_hits = sum(1 for v in first_col_values if parse_period(v) is not None)
    first_col_ratio = first_col_hits / len(first_col_values) if first_col_values else 0.0
    if first_col_ratio >= _SHAPE_DETECTION_THRESHOLD:
        return "wide"

    sample_rows = df.head(3).to_string(index=False)
    raise IngestError(
        "Could not determine whether this file is wide (periods as rows) or transposed "
        f"(metrics as rows). First rows as read:\n{sample_rows}"
    )


def _melt_to_long_form(df: pd.DataFrame, shape: str) -> list[RawCell]:
    cells: list[RawCell] = []
    label_col = df.columns[0]
    other_cols = df.columns[1:]

    if shape == "wide":
        for _, row in df.iterrows():
            period_raw = str(row[label_col])
            for metric_col in other_cols:
                cells.append(
                    RawCell(period=period_raw, source_label=str(metric_col), raw_value=str(row[metric_col]))
                )
    else:  # transposed
        for _, row in df.iterrows():
            source_label = str(row[label_col])
            for period_col in other_cols:
                cells.append(
                    RawCell(period=str(period_col), source_label=source_label, raw_value=str(row[period_col]))
                )
    return cells


def ingest_csv(file_bytes: bytes, filename: str) -> RawTable:
    if not filename.lower().endswith(".csv"):
        raise IngestError(f"Unsupported file type: {filename!r}. Only .csv files are accepted.")

    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_MB:
        raise IngestError(f"File is {size_mb:.1f}MB, exceeding the {settings.MAX_UPLOAD_MB}MB limit.")

    text, decode_warnings = _decode(file_bytes)
    delimiter = _sniff_delimiter(text)

    try:
        df = pd.read_csv(io.StringIO(text), delimiter=delimiter, dtype=str, keep_default_na=False)
    except Exception as exc:
        raise IngestError(f"Could not read file as tabular data: {exc}") from exc

    if df.shape[1] > MAX_COLUMNS:
        raise IngestError(f"File has {df.shape[1]} columns, exceeding the {MAX_COLUMNS}-column limit.")
    if df.shape[0] > MAX_ROWS:
        raise IngestError(f"File has {df.shape[0]} rows, exceeding the {MAX_ROWS}-row limit.")

    df = _drop_empty_rows_and_columns(df)
    if df.empty or df.shape[1] < 2:
        raise IngestError("File has no usable data after removing empty rows and columns.")

    shape = _detect_shape(df)
    cells = _melt_to_long_form(df, shape)

    return RawTable(cells=cells, detected_shape=shape, warnings=decode_warnings)


# ---------------------------------------------------------------------------
# Manual-entry path — same downstream structure, not a special case (T2.2)
# ---------------------------------------------------------------------------


class ManualMetricEntry:
    """One metric's worth of manually-entered values.

    Not a route in this phase (none is specified in T2.1-T2.8) — this exists
    so the manual-form fallback described in the Scheduling Note ("ship the
    form path only, defer CSV") has a concrete shape to converge on, per
    T2.2's "one downstream pipeline for both input modes."
    """

    def __init__(self, source_label: str, values: dict[str, str]):
        self.source_label = source_label
        self.values = values  # raw period string -> raw value string


def ingest_form(entries: list[ManualMetricEntry]) -> RawTable:
    cells = [
        RawCell(period=period, source_label=entry.source_label, raw_value=value)
        for entry in entries
        for period, value in entry.values.items()
    ]
    return RawTable(cells=cells, detected_shape="form", warnings=[])
