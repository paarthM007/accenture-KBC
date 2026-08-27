"""T1.7 — one test per row of the degradation matrix (master plan §15 /
pipeline-Contract-V1.md §6.7). No pytest-asyncio dependency added — async
run_pipeline() calls are driven with asyncio.run() from plain sync tests.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from api.config.settings import settings
from api.models.internal import ErrorCode
from api.models.shared import EnrichedReport, EnrichmentMetadata
from api.orchestration import pipeline as pipeline_module
from api.orchestration.pipeline import run_pipeline
from api.tests.fixtures.builders import FIXTURE_BUILDERS


@pytest.fixture(autouse=True)
def fast_mocks(monkeypatch):
    """Every mock call near-instant unless a test deliberately overrides
    sleep to force a timeout."""
    monkeypatch.setattr(settings, "MOCK_C1_SLEEP_S", 0.0)
    monkeypatch.setattr(settings, "MOCK_C3_SLEEP_S", 0.0)
    monkeypatch.setattr(settings, "MOCK_C1_RAISE_ON_CALL", False)
    monkeypatch.setattr(settings, "MOCK_C3_RAISE_ON_CALL", False)
    monkeypatch.setattr(settings, "MOCK_C3_FAIL_LLM", False)
    monkeypatch.setattr(settings, "C1_TIMEOUT_S", 10.0)
    monkeypatch.setattr(settings, "C3_TIMEOUT_S", 30.0)


def test_happy_path(monkeypatch):
    monkeypatch.setattr(settings, "MOCK_SCENARIO", "critical")
    company_input, _ = FIXTURE_BUILDERS["critical"]()

    response = asyncio.run(run_pipeline(company_input))

    assert response.status == "complete"
    assert response.result.narrative is not None
    assert len(response.result.anomaly_report.anomalies) == 2
    assert response.result.metadata.degraded is False
    assert response.timings is not None
    assert response.timings.c1_ms is not None
    assert response.timings.c3_ms is not None


def test_refusal_short_circuits_and_never_calls_c3(monkeypatch):
    monkeypatch.setattr(settings, "MOCK_SCENARIO", "refusal")
    company_input, _ = FIXTURE_BUILDERS["refusal"]()

    spy = MagicMock(side_effect=AssertionError("C3 must not be called on a refusal (Contract §3)"))
    monkeypatch.setattr(pipeline_module, "get_c3", spy)

    response = asyncio.run(run_pipeline(company_input))

    spy.assert_not_called()
    assert response.status == "refused"
    assert response.result.narrative is None
    assert response.result.anomaly_report.overall_health_score is None
    assert response.timings.c3_ms is None


def test_c3_llm_failure_degrades(monkeypatch):
    monkeypatch.setattr(settings, "MOCK_SCENARIO", "critical")
    monkeypatch.setattr(settings, "MOCK_C3_FAIL_LLM", True)
    company_input, _ = FIXTURE_BUILDERS["critical"]()

    response = asyncio.run(run_pipeline(company_input))

    assert response.status == "complete"
    assert response.result.metadata.degraded is True
    assert response.result.narrative is None
    assert len(response.result.prescriptions) == 2


def test_c3_raises_still_returns_anomalies(monkeypatch):
    monkeypatch.setattr(settings, "MOCK_SCENARIO", "critical")
    monkeypatch.setattr(settings, "MOCK_C3_RAISE_ON_CALL", True)
    company_input, _ = FIXTURE_BUILDERS["critical"]()

    response = asyncio.run(run_pipeline(company_input))

    assert response.status == "complete"
    assert response.result.metadata.degraded is True
    assert response.result.metadata.degraded_reason == "c3_failed"
    assert len(response.result.anomaly_report.anomalies) == 2


def test_c3_timeout_degrades(monkeypatch):
    monkeypatch.setattr(settings, "MOCK_SCENARIO", "critical")
    monkeypatch.setattr(settings, "C3_TIMEOUT_S", 0.05)
    monkeypatch.setattr(settings, "MOCK_C3_SLEEP_S", 0.3)
    company_input, _ = FIXTURE_BUILDERS["critical"]()

    response = asyncio.run(run_pipeline(company_input))

    assert response.status == "complete"
    assert response.result.metadata.degraded is True
    assert response.result.metadata.degraded_reason == "c3_timeout"


def test_c1_raises_returns_failed(monkeypatch):
    monkeypatch.setattr(settings, "MOCK_SCENARIO", "critical")
    monkeypatch.setattr(settings, "MOCK_C1_RAISE_ON_CALL", True)
    company_input, _ = FIXTURE_BUILDERS["critical"]()

    response = asyncio.run(run_pipeline(company_input))

    assert response.status == "failed"
    assert response.error == ErrorCode.C1_FAILED
    assert response.result is None


def test_c1_timeout_returns_failed(monkeypatch):
    monkeypatch.setattr(settings, "MOCK_SCENARIO", "critical")
    monkeypatch.setattr(settings, "C1_TIMEOUT_S", 0.05)
    monkeypatch.setattr(settings, "MOCK_C1_SLEEP_S", 0.3)
    company_input, _ = FIXTURE_BUILDERS["critical"]()

    response = asyncio.run(run_pipeline(company_input))

    assert response.status == "failed"
    assert response.error == ErrorCode.C1_TIMEOUT
    assert response.result is None


def test_contract_violation_caught_and_degraded(monkeypatch):
    """Point 3 of T1.4: raw output that doesn't parse into an EnrichedReport
    at all -> C3ContractViolation -> caught by the orchestrator -> degraded."""
    monkeypatch.setattr(settings, "MOCK_SCENARIO", "critical")
    company_input, _ = FIXTURE_BUILDERS["critical"]()

    def _mangled_get_c3():
        return lambda report: {"detected_anomalies": [], "source_metric": "oops"}

    monkeypatch.setattr(pipeline_module, "get_c3", _mangled_get_c3)

    response = asyncio.run(run_pipeline(company_input))

    assert response.status == "complete"
    assert response.result.metadata.degraded is True
    assert response.result.metadata.degraded_reason == "c3_contract_violation"
    assert len(response.result.anomaly_report.anomalies) == 2  # original report preserved


def test_c3_output_with_mismatched_anomaly_report_is_silently_corrected(monkeypatch):
    """Point 2 of T1.4: EnrichedReport is otherwise valid, but anomaly_report
    doesn't match the original -> substituted back in, loud in logs only,
    NOT marked degraded (C2 successfully repaired it)."""
    monkeypatch.setattr(settings, "MOCK_SCENARIO", "critical")
    company_input, _ = FIXTURE_BUILDERS["critical"]()
    _, drifted_report = FIXTURE_BUILDERS["healthy"]()

    def _drifted_get_c3():
        def _enrich(report):
            return EnrichedReport(
                anomaly_report=drifted_report,  # NOT verbatim — Contract §6.1 violation
                metadata=EnrichmentMetadata(processing_time_ms=1, cases_searched=0, cases_matched=0),
            )

        return _enrich

    monkeypatch.setattr(pipeline_module, "get_c3", _drifted_get_c3)

    response = asyncio.run(run_pipeline(company_input))

    assert response.status == "complete"
    assert response.result.metadata.degraded is False
    assert response.result.anomaly_report.company_id == company_input.company_id
    assert len(response.result.anomaly_report.anomalies) == 2


@pytest.mark.parametrize(
    "configure",
    [
        lambda m: m.setattr(settings, "MOCK_SCENARIO", "critical"),
        lambda m: m.setattr(settings, "MOCK_SCENARIO", "refusal"),
        lambda m: (m.setattr(settings, "MOCK_SCENARIO", "critical"), m.setattr(settings, "MOCK_C1_RAISE_ON_CALL", True)),
        lambda m: (m.setattr(settings, "MOCK_SCENARIO", "critical"), m.setattr(settings, "MOCK_C3_RAISE_ON_CALL", True)),
        lambda m: (m.setattr(settings, "MOCK_SCENARIO", "critical"), m.setattr(settings, "MOCK_C3_FAIL_LLM", True)),
    ],
)
def test_no_path_ever_raises_out_of_run_pipeline(monkeypatch, configure):
    configure(monkeypatch)
    # MockMLEngine only reads MOCK_SCENARIO to pick the fixture, ignoring the
    # input's own metrics — any well-formed CompanyInput works as the request body.
    company_input, _ = FIXTURE_BUILDERS["critical"]()
    response = asyncio.run(run_pipeline(company_input))
    assert response.status in ("complete", "refused", "failed")
