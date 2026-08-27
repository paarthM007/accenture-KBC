"""T1.5 / T1.7 — POST /analyze over the real FastAPI app, and exit criterion 6:
no code path anywhere returns HTTP 500."""

import pytest
from fastapi.testclient import TestClient

from api.config.settings import settings
from api.main import app
from api.tests.fixtures.builders import FIXTURE_BUILDERS

client = TestClient(app)


@pytest.fixture(autouse=True)
def fast_and_clean_mocks(monkeypatch):
    monkeypatch.setattr(settings, "MOCK_C1_SLEEP_S", 0.0)
    monkeypatch.setattr(settings, "MOCK_C3_SLEEP_S", 0.0)
    monkeypatch.setattr(settings, "MOCK_C1_RAISE_ON_CALL", False)
    monkeypatch.setattr(settings, "MOCK_C3_RAISE_ON_CALL", False)
    monkeypatch.setattr(settings, "MOCK_C3_FAIL_LLM", False)
    monkeypatch.setattr(settings, "MOCK_SCENARIO", "critical")
    monkeypatch.setattr(settings, "C1_TIMEOUT_S", 10.0)
    monkeypatch.setattr(settings, "C3_TIMEOUT_S", 30.0)


def _valid_body() -> dict:
    company_input, _ = FIXTURE_BUILDERS["critical"]()
    return company_input.model_dump(mode="json", by_alias=True)


def test_valid_body_returns_200_complete():
    response = client.post("/analyze", json=_valid_body())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert body["result"]["narrative"] is not None


def test_malformed_body_returns_422_in_our_envelope():
    response = client.post("/analyze", json={"company_id": "only-this-field"})
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"] == "VALIDATION_ERROR"
    assert len(body["warnings"]) > 0
    assert body["warnings"][0]["code"] == "SCHEMA_VALIDATION_ERROR"


def test_unknown_sector_id_returns_clean_validation_error():
    payload = _valid_body()
    payload["sector_id"] = "NOT_A_REAL_SECTOR"
    response = client.post("/analyze", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"MOCK_SCENARIO": "refusal"},
        {"MOCK_C1_RAISE_ON_CALL": True},
        {"MOCK_C3_RAISE_ON_CALL": True},
        {"MOCK_C3_FAIL_LLM": True},
    ],
)
def test_no_failure_injection_ever_returns_http_500(monkeypatch, overrides):
    for key, value in overrides.items():
        monkeypatch.setattr(settings, key, value)

    if overrides.get("MOCK_SCENARIO") == "refusal":
        company_input, _ = FIXTURE_BUILDERS["refusal"]()
        body = company_input.model_dump(mode="json", by_alias=True)
    else:
        body = _valid_body()

    response = client.post("/analyze", json=body)
    assert response.status_code != 500


def test_malformed_json_body_also_never_returns_500():
    response = client.post("/analyze", json={"garbage": True})
    assert response.status_code != 500
