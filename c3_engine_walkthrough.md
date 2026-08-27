# C3 Engine Implementation Walkthrough (Phase 2)

This document provides a walkthrough of the complete **C3 (Prescription, Case Matching & Narrative Engine)** implementation under `c3_engine/`. 

## 1. Engine Directory Structure

The engine is structured as a modular Python package:

```text
c3_engine/
├── __init__.py         # Package entry point exposing enrich_report()
├── schemas.py          # Pydantic v2 schemas for AnomalyReport and EnrichedReport
├── gatekeeper.py       # Gate 0 refusal check implementation
├── clustering.py       # Graph connected components for correlated_anomalies
├── prescriptions.py    # Rule lookup & current_value guardrails (§6.4, §6.5)
├── case_matcher.py     # Jaccard tag similarity matcher
├── narrative.py        # LLM call with structured output & degraded try-except (§6.7)
├── orchestrator.py     # Main entry point: enrich_report()
└── data/
    └── case_studies.json  # Sector-gated case database using exact vocabulary
```

Unit tests are implemented under:
* `tests/test_c3.py` — Verifies refusal handling, connected components, missing-metric fallback, unmatched anomaly fallback, Jaccard matching, and LLM degradation mode.

---

## 2. Core Modules & Code Implementation

### A. Schemas (`schemas.py`)
Defined strict Pydantic v2 schemas mirroring the contract specifications in §5.1 and §6.2.
* Enabled `$schema` serialization with `schema_version` and `alias="$schema"`.
* Configured `ConfigDict(populate_by_name=True)` to allow parsing from either snake_case or `$schema`.
* Set `current_value` and `delta` in `Adjustment` to be optional/nullable.
* Updated `ActionItem` to use the Phase 2 fields: `title`, `description`, `impact`, and `effort`.

### B. Refusal Handler (`gatekeeper.py`)
Implements Gate 0 refusal checks. If `anomaly_report.refusal is not None`, it immediately returns an `EnrichedReport` bypass, returning in `< 1ms` with empty lists for prescriptions and clusters, and `narrative=None`.

### C. Graph Clustering (`clustering.py`)
Builds an undirected graph where nodes are `anomaly_id`s and edges represent mutual correlation pointers.
* **Mutual Correlation Check:** An edge between `u` and `v` only exists if `v` is listed in `u.correlated_anomalies` AND `u` is listed in `v.correlated_anomalies`.
* Finds connected components using a deterministic traversal (nodes sorted prior to traversal) and sorts the output.

### D. Prescription Engine (`prescriptions.py`)
Uses a deterministic `RULE_TABLE` mapping `(sector_id, metric_id)` to prescription adjustments.
* **Sector Gating:** Rules are gated by sector (`TECH_SAAS` vs `RETAIL`).
* **All 8 Retail Metrics Supported:** Implements detailed corrective actions and rationales for `gross_margin`, `inventory_turnover`, `average_order_value`, `revenue_per_sqft`, `same_store_sales_growth`, `sell_through_rate`, `customer_acquisition_cost`, and `return_rate`.
* **Guardrails (§6.4):** Checks if the target metric exists in anomalies or highlights. If not submitted, it enforces `current_value=None`, `delta=None`, and `current_value_source="not_available"`.
* **Priority Derivation:** Maps `CRITICAL` or `SEVERE` to `HIGH`, `WARNING` to `MEDIUM`, and `INFO` to `LOW`.
* **Unmatched Fallback:** Anomalies matching no rule are skipped from the prescriptions list, and their `anomaly_id` is appended to `metadata.unmatched_anomaly_ids`.

### E. Case Matcher (`case_matcher.py`)
Matches historical business cases from `c3_engine/data/case_studies.json` to anomaly clusters.
* Filter database cases matching the company's `sector_id`.
* Compute Jaccard Similarity index:
  $$\text{Similarity Score} = \frac{\vert{}\text{Cluster Tags} \cap \text{Case Tags}\vert{}}{\vert{}\text{Cluster Tags} \cup \text{Case Tags}\vert{}}$$
* Requires a similarity score $\ge 0.50$ threshold.
* Returns the top 1–2 highest-scoring cases per cluster, attaching `cluster_index` to trace which cluster triggered it.

### F. Narrative LLM Engine (`narrative.py`)
Performs a single LLM call to Gemini (`gemini-3.1-flash-lite`) enforcing strict JSON output conforming to the `Narrative` schema.
* Loads API key from `.env` via `python-dotenv`.
* Utilizes the new Google GenAI client (`from google import genai`) and standard `generate_content` models.
* Sends company metadata, severity breakdowns, highlights, prescriptions, and matched cases.
* Wrapped inside a strict try-except block to gracefully catch timeouts, rate limits, or missing API keys, falling back to `degraded = True` and `narrative = None` instead of raising an unhandled exception.

### G. Orchestration (`orchestrator.py`)
Unifies the modules under the main `enrich_report()` function. It accepts:
1. `AnomalyReport` Pydantic objects.
2. Raw JSON strings.
3. Raw dictionaries.
It measures execution time, runs gatekeeping, clustering, prescription, case matching, and narrative generation, and returns a fully packaged `EnrichedReport`.

---

## 3. Test Coverage

The suite in `tests/test_c3.py` contains 9 tests:
1. `test_refusal_path`: Confirms that a refusal is bypassed and returns under `5ms` with zero exceptions.
2. `test_cluster_generation`: Verifies mutual correlation undirected graph connected component extraction.
3. `test_missing_metric_fallback`: Confirms the `not_available` source guardrail for unsubmitted metrics.
4. `test_unmatched_anomaly_fallback`: Confirms that unknown metrics are correctly added to `metadata.unmatched_anomaly_ids`.
5. `test_happy_path_prescription`: Confirms action/rationale/priority mapping matches expectations.
6. `test_case_matcher_exact_tag_overlap`: Verifies that an anomaly cluster with tags `["churn_related", "retention_leak"]` correctly matches the SaaS onboarding case study and attaches `cluster_index = 0`.
7. `test_case_matcher_threshold_fallback`: Passes dummy tags with zero overlap to confirm `matched_cases == []`.
8. `test_narrative_degraded_mode_on_llm_failure`: Mocks an LLM exception and asserts `narrative is None` and `degraded is True`, while keeping prescriptions and cases populated.
9. `test_untouched_anomaly_report_pass_through`: Verifies that the upstream `AnomalyReport` survives entirely unmodified and verbatim.
