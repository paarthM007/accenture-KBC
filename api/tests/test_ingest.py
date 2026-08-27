"""T2.2 — shape detection & ingestion. Exit criteria 1, 2."""

import pytest

from api.parsing.ingest import IngestError, ManualMetricEntry, ingest_csv, ingest_form

WIDE_CSV = b"""Month,MRR Growth %,Churn Rate,Gross Margin
2026-01,7.2,2.1,74.5
2026-02,6.8,2.4,74.1
"""

TRANSPOSED_CSV = b"""Metric,Jan 2026,Feb 2026,Mar 2026
MRR Growth %,7.2,6.8,4.1
Churn Rate,2.1,2.4,3.2
"""

SEMICOLON_CSV = b"""Month;MRR Growth %;Churn Rate
2026-01;7.2;2.1
2026-02;6.8;2.4
"""

GARBAGE = b"""This is not a spreadsheet at all.
Just some prose someone pasted in by mistake.
No columns, no structure, nothing tabular here.
"""


class TestIngestCsv:
    def test_wide_shape_detected_and_melted(self):
        table = ingest_csv(WIDE_CSV, "clean_wide.csv")
        assert table.detected_shape == "wide"
        periods = {c.period for c in table.cells}
        labels = {c.source_label for c in table.cells}
        assert periods == {"2026-01", "2026-02"}
        assert labels == {"MRR Growth %", "Churn Rate", "Gross Margin"}
        assert len(table.cells) == 6  # 2 periods x 3 metrics

    def test_transposed_shape_auto_detected(self):
        table = ingest_csv(TRANSPOSED_CSV, "clean_transposed.csv")
        assert table.detected_shape == "transposed"
        periods = {c.period for c in table.cells}
        labels = {c.source_label for c in table.cells}
        assert periods == {"Jan 2026", "Feb 2026", "Mar 2026"}
        assert labels == {"MRR Growth %", "Churn Rate"}
        assert len(table.cells) == 6  # 2 metrics x 3 periods

    def test_semicolon_delimiter_sniffed(self):
        table = ingest_csv(SEMICOLON_CSV, "semicolon.csv")
        assert table.detected_shape == "wide"
        assert len(table.cells) == 4

    def test_non_csv_extension_rejected(self):
        with pytest.raises(IngestError, match="Only .csv"):
            ingest_csv(WIDE_CSV, "clean_wide.xlsx")

    def test_garbage_file_fails_cleanly(self):
        with pytest.raises(IngestError):
            ingest_csv(GARBAGE, "garbage.csv")

    def test_oversized_file_rejected(self, monkeypatch):
        from api.config.settings import settings

        monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 0.0000001)
        with pytest.raises(IngestError, match="exceeding"):
            ingest_csv(WIDE_CSV, "clean_wide.csv")

    def test_empty_rows_and_columns_dropped(self):
        csv_with_blanks = b"""Month,MRR Growth %,Blank Col\n2026-01,7.2,\n,,\n2026-02,6.8,\n"""
        table = ingest_csv(csv_with_blanks, "blanks.csv")
        labels = {c.source_label for c in table.cells}
        assert "Blank Col" not in labels  # entirely-empty column dropped
        periods = {c.period for c in table.cells}
        assert periods == {"2026-01", "2026-02"}  # entirely-empty row dropped


class TestIngestForm:
    def test_form_produces_identical_cell_structure(self):
        entries = [
            ManualMetricEntry("churn_rate", {"2026-01": "2.1", "2026-02": "2.4"}),
        ]
        table = ingest_form(entries)
        assert table.detected_shape == "form"
        assert len(table.cells) == 2
        assert {c.period for c in table.cells} == {"2026-01", "2026-02"}
        assert all(c.source_label == "churn_rate" for c in table.cells)
