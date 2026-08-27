"""T2.6 — POST /validate. Exit criterion 12: returns proposals/warnings
without running the pipeline."""

import json

from fastapi.testclient import TestClient

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
FRACTION_CSV = b"Month,GM\n2024-01,0.74\n2024-02,0.72\n2024-03,0.75\n2024-04,0.73\n"
GARBAGE = b"not a spreadsheet\njust some prose\nnothing tabular\n"


def _post_validate(csv_bytes: bytes, metadata: str = VALID_METADATA, filename: str = "data.csv"):
    return client.post(
        "/validate",
        files={"file": (filename, csv_bytes, "text/csv")},
        data={"metadata": metadata},
    )


def test_clean_csv_returns_ready_true_with_proposals():
    response = _post_validate(CLEAN_CSV)
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert len(body["proposals"]) == 2
    assert body["inferred"]["periods"] == 6
    assert body["inferred"]["shape"] == "wide"


def test_fraction_percentage_makes_it_not_ready():
    response = _post_validate(FRACTION_CSV)
    body = response.json()
    assert body["ready"] is False
    assert any(w["code"] == "UNIT_SCALE_SUSPECT" for w in body["warnings"])


def test_garbage_csv_returns_200_with_blocking_errors_not_a_500():
    response = _post_validate(GARBAGE)
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is False
    assert len(body["blocking_errors"]) > 0


def test_missing_file_returns_422_in_validate_response_shape():
    response = client.post("/validate", data={"metadata": VALID_METADATA})
    assert response.status_code == 422
    body = response.json()
    # ValidateResponse shape, not ApiResponse — no "job_id"/"status" fields.
    assert "job_id" not in body
    assert "ready" in body
    assert body["ready"] is False


def test_never_calls_the_pipeline(monkeypatch):
    from api.orchestration import pipeline as pipeline_module
    from unittest.mock import MagicMock

    spy = MagicMock(side_effect=AssertionError("run_pipeline must never be called by /validate"))
    monkeypatch.setattr(pipeline_module, "run_pipeline", spy)

    _post_validate(CLEAN_CSV)
    spy.assert_not_called()
