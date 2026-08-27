"""T0.7 acceptance criteria: both mocks are importable, honour their failure
flags, and MockC3 short-circuits correctly on the refusal fixture. Not one of
the four files T0.9 names explicitly, but exit criterion 5 ("MockMLEngine and
MockC3 are switchable by config") and T0.7's own "Accepted when" line aren't
covered by test_models/test_fixtures/test_config/test_health, so this file
closes that gap.

sleep_s is overridden to 0 everywhere except the one test that checks the
realism sleep actually happens — Phase0-Plan calls for ~200ms/~1.5s sleeps in
the mocks themselves, but the rest of this suite should stay fast.
"""

import time

import pytest

from api.mocks.mock_c3 import MockC3
from api.mocks.mock_ml import MockMLEngine
from api.tests.fixtures.builders import FIXTURE_BUILDERS


class TestMockMLEngine:
    def test_returns_scenario_fixture_report(self):
        engine = MockMLEngine(scenario="critical", sleep_s=0)
        company_input, _ = FIXTURE_BUILDERS["healthy"]()  # deliberately different company
        report = engine.analyze_company(company_input)
        assert len(report.anomalies) == 2  # shape of the "critical" fixture, not "healthy"

    def test_overrides_company_id_and_sector_id_from_payload(self):
        engine = MockMLEngine(scenario="healthy", sleep_s=0)
        company_input, _ = FIXTURE_BUILDERS["critical"]()
        report = engine.analyze_company(company_input)
        assert report.company_id == company_input.company_id
        assert report.sector_id == company_input.sector_id

    def test_raise_on_call(self):
        engine = MockMLEngine(scenario="critical", raise_on_call=True, sleep_s=0)
        company_input, _ = FIXTURE_BUILDERS["critical"]()
        with pytest.raises(RuntimeError):
            engine.analyze_company(company_input)

    def test_unknown_scenario_rejected_at_construction(self):
        with pytest.raises(ValueError):
            MockMLEngine(scenario="not_a_real_scenario")

    def test_sleeps_to_mimic_cpu_bound_work(self):
        engine = MockMLEngine(scenario="critical", sleep_s=0.05)
        company_input, _ = FIXTURE_BUILDERS["critical"]()
        start = time.monotonic()
        engine.analyze_company(company_input)
        assert time.monotonic() - start >= 0.05


class TestMockC3:
    def test_short_circuits_on_refusal_with_no_sleep(self):
        _, refusal_report = FIXTURE_BUILDERS["refusal"]()
        c3 = MockC3(sleep_s=5)  # would fail the test if the guard didn't skip it
        start = time.monotonic()
        enriched = c3.enrich_report(refusal_report)
        elapsed = time.monotonic() - start

        assert elapsed < 1.0
        assert enriched.anomaly_report == refusal_report
        assert enriched.prescriptions == []
        assert enriched.anomaly_clusters == []
        assert enriched.matched_cases == []
        assert enriched.narrative is None
        assert enriched.metadata.degraded is False

    def test_nests_anomaly_report_verbatim_on_normal_path(self):
        _, critical_report = FIXTURE_BUILDERS["critical"]()
        c3 = MockC3(sleep_s=0)
        enriched = c3.enrich_report(critical_report)
        assert enriched.anomaly_report == critical_report

    def test_fail_llm_produces_degraded_with_everything_else_populated(self):
        _, critical_report = FIXTURE_BUILDERS["critical"]()
        c3 = MockC3(fail_llm=True, sleep_s=0)
        enriched = c3.enrich_report(critical_report)
        assert enriched.narrative is None
        assert enriched.metadata.degraded is True
        assert len(enriched.prescriptions) == len(critical_report.anomalies)
        assert len(enriched.matched_cases) == len(critical_report.anomalies)

    def test_raise_on_call(self):
        _, critical_report = FIXTURE_BUILDERS["critical"]()
        c3 = MockC3(raise_on_call=True, sleep_s=0)
        with pytest.raises(RuntimeError):
            c3.enrich_report(critical_report)

    def test_raise_on_call_takes_precedence_over_refusal_guard(self):
        _, refusal_report = FIXTURE_BUILDERS["refusal"]()
        c3 = MockC3(raise_on_call=True, sleep_s=0)
        with pytest.raises(RuntimeError):
            c3.enrich_report(refusal_report)
