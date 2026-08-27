"""T2.7 — POST /analyze/upload. Exit criterion 13."""

import json

import pytest
from fastapi.testclient import TestClient

from api.config.settings import settings
from api.main import app

client = TestClient(app)

VALID_METADATA = json.dumps(
    {
        "company_name": "Acme Co",
        "sector_id": "TECH_SAAS",
        "employee_count": 40,
        "region": "US",
        "annual_revenue": 4_000_000,
    }
)

CLEAN_CSV = b"Month,Churn,GM\n2024-01,2.0,75.0\n2024-02,2.1,74.5\n2024-03,1.9,74.8\n2024-04,2.2,75.1\n2024-05,2.0,74.9\n2024-06,1.8,75.3\n"
UNKNOWN_COL_CSV = b"Month,Churn,Nonsense Column\n2024-01,2.0,1\n2024-02,2.1,2\n2024-03,1.9,3\n2024-04,2.2,4\n2024-05,2.0,5\n2024-06,1.8,6\n"
GARBAGE = b"not a spreadsheet\njust some prose\nnothing tabular\n"


@pytest.fixture(autouse=True)
def fast_mocks(monkeypatch):
    monkeypatch.setattr(settings, "MOCK_C1_SLEEP_S", 0.0)
    monkeypatch.setattr(settings, "MOCK_C3_SLEEP_S", 0.0)
    monkeypatch.setattr(settings, "MOCK_SCENARIO", "critical")


def _post_upload(csv_bytes: bytes, metadata: str = VALID_METADATA, mapping_overrides: str | None = None):
    data = {"metadata": metadata}
    if mapping_overrides is not None:
        data["mapping_overrides"] = mapping_overrides
    return client.post(
        "/analyze/upload",
        files={"file": ("data.csv", csv_bytes, "text/csv")},
        data=data,
    )


def test_clean_csv_runs_full_pipeline():
    response = _post_upload(CLEAN_CSV)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert body["result"]["narrative"] is not None


def test_garbage_never_starts_pipeline():
    response = _post_upload(GARBAGE)
    assert response.status_code != 500
    body = response.json()
    assert body["status"] == "failed"
    assert body["result"] is None


def test_parse_warnings_survive_onto_final_response():
    response = _post_upload(UNKNOWN_COL_CSV)
    body = response.json()
    assert body["status"] == "complete"
    codes = {w["code"] for w in body["warnings"]}
    assert "UNKNOWN_METRIC" in codes


def test_mapping_override_resolves_otherwise_unknown_column():
    overrides = json.dumps({"Nonsense Column": "gross_margin"})
    response = _post_upload(UNKNOWN_COL_CSV, mapping_overrides=overrides)
    body = response.json()
    assert body["status"] == "complete"
    codes = {w["code"] for w in body["warnings"]}
    assert "UNKNOWN_METRIC" not in codes
