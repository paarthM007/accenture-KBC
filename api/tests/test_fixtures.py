"""T0.9 — all four fixtures build, round-trip byte-identical through
model_dump(by_alias=True) -> model_validate(), and satisfy their specific
regression tests (Phase0-Plan T0.6)."""

import pytest

from api.config.loader import metrics
from api.models.shared import AnomalyReport, CompanyInput
from api.tests.fixtures.builders import FIXTURE_BUILDERS


@pytest.mark.parametrize("name", list(FIXTURE_BUILDERS.keys()))
def test_fixture_builds_without_validation_error(name):
    company_input, anomaly_report = FIXTURE_BUILDERS[name]()
    assert isinstance(company_input, CompanyInput)
    assert isinstance(anomaly_report, AnomalyReport)


@pytest.mark.parametrize("name", list(FIXTURE_BUILDERS.keys()))
def test_fixture_round_trips_through_dump_and_validate(name):
    company_input, anomaly_report = FIXTURE_BUILDERS[name]()

    ci_dumped = company_input.model_dump(by_alias=True)
    ci_restored = CompanyInput.model_validate(ci_dumped)
    assert ci_restored == company_input

    ar_dumped = anomaly_report.model_dump(by_alias=True)
    ar_restored = AnomalyReport.model_validate(ar_dumped)
    assert ar_restored == anomaly_report


def test_refusal_fixture_has_null_health_score_and_no_anomalies():
    # Regression test for exit criterion 6 and bug #1.
    _, anomaly_report = FIXTURE_BUILDERS["refusal"]()
    assert anomaly_report.overall_health_score is None
    assert anomaly_report.anomalies == []
    assert anomaly_report.non_anomalous_highlights == []
    assert anomaly_report.refusal is not None


def test_healthy_fixture_has_highlight_absent_from_metric_config():
    # Regression test: Phase 3's UI must not KeyError on a computed highlight
    # (e.g. ltv_cac_ratio) whose metric_id isn't in metric_config.yaml.
    _, anomaly_report = FIXTURE_BUILDERS["healthy"]()
    known_metric_ids = set(metrics().keys())
    highlight_ids = {h.metric_id for h in anomaly_report.non_anomalous_highlights}
    assert highlight_ids - known_metric_ids, "expected at least one highlight absent from metric_config.yaml"


def test_critical_fixture_has_mutually_correlated_anomalies():
    _, anomaly_report = FIXTURE_BUILDERS["critical"]()
    assert len(anomaly_report.anomalies) == 2
    by_metric = {a.metric_id: a for a in anomaly_report.anomalies}
    churn = by_metric["churn_rate"]
    nrr = by_metric["net_revenue_retention"]
    assert nrr.anomaly_id in churn.correlated_anomalies
    assert churn.anomaly_id in nrr.correlated_anomalies


def test_degraded_fixture_reuses_critical_input_and_report():
    critical_input, critical_report = FIXTURE_BUILDERS["critical"]()
    degraded_input, degraded_report = FIXTURE_BUILDERS["degraded"]()
    assert degraded_input == critical_input
    assert degraded_report == critical_report
