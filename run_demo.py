from datetime import datetime, timezone
from c3_engine import enrich_report

# 1. Define a realistic sample AnomalyReport matching the C1 specifications
sample_anomaly_report = {
    "$schema": "anomaly_report_v1",
    "company_id": "comp_saas_global_100",
    "sector_id": "TECH_SAAS",
    "analysis_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "reporting_period": {
        "type": "monthly",
        "start": "2026-01-01",
        "end": "2026-06-30"
    },
    "company_profile_summary": {
        "revenue_band": "10M-50M",
        "employee_count": 150,
        "region": "US"
    },
    "overall_health_score": 62.8,
    "anomalies": [
        {
            "anomaly_id": "A1",
            "metric_id": "churn_rate",
            "metric_display_name": "Churn Rate",
            "category": "retention",
            "severity_score": 92.5,
            "severity_label": "SEVERE",
            "deviation": {
                "observed_current": 14.8,
                "expected_value": 4.5,
                "expected_std": 1.2,
                "z_score": 8.58,
                "percentile": 99.9,
                "direction": "above_expected"
            },
            "trend": {
                "direction": "deteriorating",
                "slope": 1.5,
                "acceleration": 0.2,
                "periods_deviating": 4,
                "values_over_time": []
            },
            "correlated_anomalies": ["A2"],
            "noise_confidence": 0.98,
            "context_tags": ["churn_related", "retention_leak", "customer_attrition"],
            "natural_language_summary": "Churn rate has spiked to 14.8% (expected 4.5%), indicating high retention leakage."
        },
        {
            "anomaly_id": "A2",
            "metric_id": "net_revenue_retention",
            "metric_display_name": "Net Revenue Retention (NRR)",
            "category": "retention",
            "severity_score": 88.0,
            "severity_label": "CRITICAL",
            "deviation": {
                "observed_current": 82.5,
                "expected_value": 108.0,
                "expected_std": 3.5,
                "z_score": -7.28,
                "percentile": 0.1,
                "direction": "below_expected"
            },
            "trend": {
                "direction": "deteriorating",
                "slope": -3.2,
                "acceleration": -0.5,
                "periods_deviating": 3,
                "values_over_time": []
            },
            "correlated_anomalies": ["A1"],
            "noise_confidence": 0.95,
            "context_tags": ["nrr_drop", "expansion_revenue", "account_health"],
            "natural_language_summary": "Net Revenue Retention has dropped to 82.5%, well below the historical base of 108%."
        }
    ],
    "non_anomalous_highlights": [
        {
            "metric_id": "monthly_recurring_revenue_growth",
            "metric_display_name": "MRR Growth Rate",
            "observed_value": 11.2,
            "expected_value": 10.0,
            "percentile": 65.0,
            "context_tags": ["growth_decline", "topline", "saas_velocity"],
            "natural_language_summary": "Monthly Recurring Revenue Growth remains healthy at 11.2%."
        }
    ],
    "refusal": None,
    "metadata": {
        "model_version": "c1_detector_v1.2",
        "synthetic_profile_version": "profile_saas_v1.0",
        "metrics_analyzed": ["churn_rate", "net_revenue_retention", "monthly_recurring_revenue_growth"],
        "metrics_with_anomalies": ["churn_rate", "net_revenue_retention"],
        "metrics_with_missing_data": [],
        "skipped_metrics": [],
        "processing_time_ms": 14.5
    }
}

print("Loading and analyzing sample report using C3 Engine...")
enriched = enrich_report(sample_anomaly_report)

# Serialize utilizing by_alias=True to guarantee "$schema" field output on serialization
output_json = enriched.model_dump_json(indent=2, by_alias=True)

# Write to output file
output_filepath = "enriched_report_output.json"
with open(output_filepath, "w") as f:
    f.write(output_json)

print(f"\nAnalysis completed successfully. Output saved to {output_filepath}")
print("\n--- SAMPLE ENRICHED REPORT OUTPUT ---")
print(output_json)
