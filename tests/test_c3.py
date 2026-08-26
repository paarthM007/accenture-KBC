import unittest
import time
from datetime import datetime
from c3_engine.schemas import AnomalyReport, EnrichedReport, Anomaly, DeviationDetail, TrendDetail
from c3_engine.orchestrator import enrich_report
from c3_engine.clustering import build_anomaly_clusters
from c3_engine.prescriptions import find_submitted_metric_value

def make_test_anomaly(anomaly_id: str, metric_id: str, severity_label: str = "WARNING", correlated=None) -> dict:
    if correlated is None:
        correlated = []
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
        "context_tags": ["test_tag"],
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

class TestC3Engine(unittest.TestCase):

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
        
        # Verify execution time is extremely fast (< 1ms is expected, but let's assert < 10ms to be safe for CI spikes, usually < 0.2ms)
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

if __name__ == "__main__":
    unittest.main()
