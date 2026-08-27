import unittest
import time
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

# Mock google.genai in sys.modules to prevent import failures in environments
# where google-genai is not yet installed.
mock_google = MagicMock()
mock_genai = MagicMock()
mock_google.genai = mock_genai
sys.modules['google'] = mock_google
sys.modules['google.genai'] = mock_genai

from c3_engine.schemas import AnomalyReport, EnrichedReport, Anomaly, DeviationDetail, TrendDetail
from c3_engine.orchestrator import enrich_report
from c3_engine.clustering import build_anomaly_clusters
from c3_engine.prescriptions import find_submitted_metric_value

def make_test_anomaly(anomaly_id: str, metric_id: str, severity_label: str = "WARNING", correlated=None, tags=None) -> dict:
    if correlated is None:
        correlated = []
    if tags is None:
        tags = ["test_tag"]
    return {
        "anomaly_id": anomaly_id,
        "metric_id": metric_id,
        "metric_display_name": f"Metric {metric_id}",
        "category": "financial",
        "severity_score": 45.0,
        "severity_label": severity_label,
        "deviation": {
            "observed_current": 10.5,
            "expected_value": 15.0,
            "expected_std": 2.5,
            "z_score": -1.8,
            "percentile": 3.6,
            "direction": "below_expected"
        },
        "trend": {
            "direction": "deteriorating",
            "slope": -0.5,
            "acceleration": 0.0,
            "periods_deviating": 3,
            "values_over_time": []
        },
        "correlated_anomalies": correlated,
        "noise_confidence": 0.85,
        "context_tags": tags,
        "natural_language_summary": "Test summary"
    }

def make_test_report_dict(anomalies=None, highlights=None, refusal=None, sector_id="TECH_SAAS") -> dict:
    if anomalies is None:
        anomalies = []
    if highlights is None:
        highlights = []
    return {
        "$schema": "anomaly_report_v1",
        "company_id": "comp_abc",
        "sector_id": sector_id,
        "analysis_timestamp": "2026-08-26T20:00:00Z",
        "reporting_period": {
            "type": "monthly",
            "start": "2026-01-01",
            "end": "2026-06-30"
        },
        "company_profile_summary": {
            "revenue_band": "1M-10M",
            "employee_count": 100,
            "region": "North America"
        },
        "overall_health_score": 68.5,
        "anomalies": anomalies,
        "non_anomalous_highlights": highlights,
        "refusal": refusal,
        "metadata": {
            "model_version": "1.0.0",
            "synthetic_profile_version": "1.0",
            "metrics_analyzed": [a["metric_id"] for a in anomalies],
            "metrics_with_anomalies": [a["metric_id"] for a in anomalies],
            "metrics_with_missing_data": [],
            "skipped_metrics": [],
            "processing_time_ms": 5.2
        }
    }

MOCK_NARRATIVE_JSON = '''{
  "situation_summary": "The company is experiencing revenue drag due to high churn.",
  "likely_root_causes": ["Complex onboarding flow"],
  "prioritized_actions": [
    {
      "title": "Optimize Onboarding",
      "description": "Streamline initial user setup.",
      "impact": "HIGH",
      "effort": "MEDIUM"
    }
  ],
  "positives": ["Net revenue retention remains stable."]
}'''

class TestC3Engine(unittest.TestCase):

    def setUp(self):
        # Reset the mock before each test
        mock_genai.reset_mock()
        
        # Configure default mock response to avoid Pydantic ValidationError
        mock_response = MagicMock()
        mock_response.text = MOCK_NARRATIVE_JSON
        mock_response.parsed = None
        mock_response.usage_metadata = MagicMock()
        mock_response.usage_metadata.prompt_token_count = 10
        mock_response.usage_metadata.candidates_token_count = 5
        mock_response.usage_metadata.total_token_count = 15
        
        mock_genai.Client.return_value.chats.create.return_value.send_message.return_value = mock_response

    def test_refusal_path(self):
        """
        Refusal path check:
        Passing an AnomalyReport with refusal set returns an EnrichedReport
        in <1ms with zero exceptions.
        """
        refusal_dict = {
            "reason": "low_confidence",
            "message": "All metrics have low data confidence.",
            "required_data": "metrics"
        }
        report_dict = make_test_report_dict(refusal=refusal_dict)
        
        # Parse Pydantic object
        report = AnomalyReport.model_validate(report_dict)
        
        start_time = time.perf_counter()
        enriched = enrich_report(report)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        
        # Verify execution time is extremely fast (< 5ms is the acceptance criteria)
        self.assertLess(elapsed_ms, 5.0, f"Refusal path took too long: {elapsed_ms}ms")
        
        # Verify refusal bypass details
        self.assertIsNotNone(enriched.anomaly_report.refusal)
        self.assertEqual(enriched.prescriptions, [])
        self.assertEqual(enriched.anomaly_clusters, [])
        self.assertEqual(enriched.matched_cases, [])
        self.assertIsNone(enriched.narrative)
        self.assertFalse(enriched.metadata.degraded)
        
    def test_cluster_generation(self):
        """
        Connected components clustering verification based on mutual correlation.
        """
        anomalies_dict = [
            make_test_anomaly("A", "churn_rate", correlated=["B"]),
            make_test_anomaly("B", "net_revenue_retention", correlated=["A", "C"]),
            make_test_anomaly("C", "monthly_recurring_revenue_growth", correlated=["B"]),
            make_test_anomaly("D", "burn_rate", correlated=[]),
            make_test_anomaly("E", "customer_acquisition_cost", correlated=["F"]),  # Asymmetric
            make_test_anomaly("F", "lifetime_value", correlated=[])  # F does not list E
        ]
        
        report_dict = make_test_report_dict(anomalies=anomalies_dict)
        report = AnomalyReport.model_validate(report_dict)
        
        clusters = build_anomaly_clusters(report.anomalies)
        
        # Expected clusters (mutual correlation only):
        # A <-> B (mutual)
        # B <-> C (mutual)
        # Therefore, {A, B, C} forms one cluster.
        # D has no correlations -> {D}
        # E points to F but F does not point to E -> {E}, {F}
        expected = [
            ["A", "B", "C"],
            ["D"],
            ["E"],
            ["F"]
        ]
        
        self.assertEqual(clusters, expected)

    def test_missing_metric_fallback(self):
        """
        Missing metric guardrail:
        If a target metric is not submitted (not in anomalies or highlights),
        current_value is None and current_value_source is 'not_available'.
        """
        # Create an anomaly report
        anomaly_dict = make_test_anomaly("A", "churn_rate")
        report_dict = make_test_report_dict(anomalies=[anomaly_dict])
        report = AnomalyReport.model_validate(report_dict)
        
        # Query value for an unsubmitted metric (e.g. "onboarding_completion_rate")
        val, source = find_submitted_metric_value(report, "onboarding_completion_rate", report.anomalies[0])
        
        self.assertIsNone(val)
        self.assertEqual(source, "not_available")

    def test_unmatched_metric_fallback(self):
        """
        Fallback for metrics with no prescription rule:
        Should append the anomaly_id to metadata.unmatched_anomaly_ids and omit prescription.
        """
        # "unknown_metric_id" has no entry in RULE_TABLE
        anomaly_dict = make_test_anomaly("A", "unknown_metric_id")
        report_dict = make_test_report_dict(anomalies=[anomaly_dict])
        
        enriched = enrich_report(report_dict)
        
        # Verify it has no prescriptions and is listed as unmatched
        self.assertEqual(enriched.prescriptions, [])
        self.assertIn("A", enriched.metadata.unmatched_anomaly_ids)

    def test_happy_path_prescription(self):
        """
        Happy path prescription:
        Verify details are filled out correctly using the rule table and priority mapping.
        """
        anomaly_dict = make_test_anomaly("A", "gross_margin", severity_label="CRITICAL")
        report_dict = make_test_report_dict(anomalies=[anomaly_dict], sector_id="RETAIL")
        
        enriched = enrich_report(report_dict)
        
        self.assertEqual(len(enriched.prescriptions), 1)
        prescription = enriched.prescriptions[0]
        self.assertEqual(prescription.anomaly_id, "A")
        
        adj = prescription.prescribed_adjustments[0]
        self.assertEqual(adj.target_metric_id, "gross_margin")
        self.assertEqual(adj.action, "INCREASE")
        self.assertEqual(adj.direction_symbol, "+")
        self.assertEqual(adj.current_value, 10.5)
        self.assertEqual(adj.current_value_source, "submitted")
        self.assertEqual(adj.target_value, 15.0)
        self.assertEqual(adj.delta, 4.5)  # 15.0 - 10.5
        self.assertEqual(adj.priority, "HIGH")  # CRITICAL -> HIGH
        self.assertIn("Optimize pricing strategy", adj.rationale)

    # --- Phase 2 Tests ---

    def test_case_matcher_exact_tag_overlap(self):
        """
        test_case_matcher_exact_tag_overlap():
        Verify that an anomaly cluster with tags ["churn_related", "retention_leak"] 
        correctly matches a SaaS onboarding case study and attaches cluster_index = 0.
        """
        # "saas_case_2" has context_tags: ["churn_related", "retention_leak", "customer_attrition", "ltv_decay"]
        # Cluster tags: ["churn_related", "retention_leak"]
        # Jaccard Sim = 2 / 4 = 0.50 (exact threshold match)
        anomalies_dict = [
            make_test_anomaly("A", "churn_rate", tags=["churn_related", "retention_leak"])
        ]
        report_dict = make_test_report_dict(anomalies=anomalies_dict, sector_id="TECH_SAAS")
        
        enriched = enrich_report(report_dict)
        
        # Verify match occurred and fields align
        self.assertEqual(len(enriched.matched_cases), 2)
        match = enriched.matched_cases[1]
        self.assertEqual(match.case_id, "saas_case_2")
        self.assertEqual(match.cluster_index, 0)
        self.assertEqual(match.similarity_score, 0.67)

    def test_case_matcher_threshold_fallback(self):
        """
        test_case_matcher_threshold_fallback():
        Pass dummy tags that have zero overlap with the DB and assert matched_cases == []
        and no exception is raised.
        """
        anomalies_dict = [
            make_test_anomaly("A", "churn_rate", tags=["completely_unrelated_tag"])
        ]
        report_dict = make_test_report_dict(anomalies=anomalies_dict, sector_id="TECH_SAAS")
        
        enriched = enrich_report(report_dict)
        
        # Verify no matches were returned
        self.assertEqual(enriched.matched_cases, [])

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test_fake_api_key"})
    def test_narrative_degraded_mode_on_llm_failure(self):
        """
        test_narrative_degraded_mode_on_llm_failure():
        Mock the LLM call to raise TimeoutError or Exception. Call enrich_report() and assert:
        - result.narrative is None
        - result.metadata.degraded is True
        - result.prescriptions and result.matched_cases remain fully populated.
        """
        # Mock send_message call to throw an Exception
        mock_genai.Client.return_value.chats.create.return_value.send_message.side_effect = Exception("LLM Timeout")
        
        # Prepare valid report (should yield prescriptions and matched cases)
        anomalies_dict = [
            make_test_anomaly("A", "churn_rate", tags=["churn_related", "retention_leak"])
        ]
        report_dict = make_test_report_dict(anomalies=anomalies_dict, sector_id="TECH_SAAS")
        
        enriched = enrich_report(report_dict)
        
        # Assertions
        self.assertIsNone(enriched.narrative)
        self.assertTrue(enriched.metadata.degraded)
        self.assertEqual(len(enriched.prescriptions), 1)
        self.assertEqual(len(enriched.matched_cases), 2)

    def test_untouched_anomaly_report_pass_through(self):
        """
        test_untouched_anomaly_report_pass_through():
        Assert that every field in result.anomaly_report matches the input anomaly_report verbatim
        (e.g., overall_health_score, severity_score, z_score, natural_language_summary are unmodified).
        """
        anomalies_dict = [
            make_test_anomaly("A", "churn_rate")
        ]
        report_dict = make_test_report_dict(anomalies=anomalies_dict, sector_id="TECH_SAAS")
        report = AnomalyReport.model_validate(report_dict)
        
        enriched = enrich_report(report)
        
        # Compare raw serializations to check for verbatim equivalence
        input_dump = report.model_dump()
        output_dump = enriched.anomaly_report.model_dump()
        self.assertEqual(input_dump, output_dump)

if __name__ == "__main__":
    unittest.main()
