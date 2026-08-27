# businessintelligence.ai — Pipeline Contract v1.1

**Status:** READY FOR C3 REVIEW — C1 internals completed. C3 to confirm §6 and sign off in §11.
**Purpose:** Single source of truth for what each component receives, produces, and is responsible for. Once all three of us sign off at the bottom, this document overrides every earlier handout.

### Changelog

**v1.1** — C2 revisions after reviewing C1's completed §5.3:
- §3 — refusal routing added to the pipeline diagram. **C2 short-circuits and does not call C3 on a refusal.** §6.3 restated as a defensive guard rather than the primary path.
- §5.1 — `RefusalDetail` expanded with provisional fields and `extra="allow"`.
- §9 — four new open items (O11–O14) from C2's review of §5.3.
- §12 — new section: implementation notes for C2 and C3 derived from §5.3.

**v1.0** — C1 completed §5.3 internals; items 6, 8, 9 resolved.

---

## How to use this document

**C3 owner — this is yours now.** Your component's contract is §6. It is written as a *specification*, not a suggestion, because three earlier documents disagreed with each other and we lost time to it. If something in §6 is wrong or unbuildable, say so and we'll change it here — but please don't change it unilaterally in your own code, because the two of us build against it.

§5.3 has been filled in from the actual `ml_engine` source. Read it before building the prescription and case-matching logic — it answers what `correlated_anomalies` means, what the full `context_tags` vocabulary is, and where baselines come from. §12 translates it into the things that will actually change your implementation.

**Nobody starts coding against a contract that isn't signed off in §11.** Mocks are fine and encouraged — build against the schemas below immediately.

---

## 1. Why this document exists

We currently have four documents describing this pipeline, and they disagree on:

- whether `ml_engine` is an in-process import or an external service
- whether the anomaly array is called `anomalies` or `detected_anomalies`
- whether there are three pipeline stages or four
- which fields survive to the Case Matcher (currently 8 of the 10 fields the Case Matcher was told to use are dropped by the stage above it)
- who generates `natural_language_summary`
- what happens on a refusal

None of these are hard problems. They're coordination failures, and each one costs us hours at integration. This document fixes them by naming one owner per contract and locking the shape.

---

## 2. Component ownership

| Component | Owns | Owner |
|---|---|---|
| **C1 — Anomaly Detection Engine** | Synthetic sector baselines, statistical detection, severity scoring, refusal decision | *(name)* |
| **C2 — API, Parsing & Orchestration** | Input ingestion, normalization, validation, pipeline orchestration, error handling, frontend | *(name)* |
| **C3 — Prescription, Case Matching & Narrative** | Parameter prescriptions, case retrieval, LLM narrative generation | *(name)* |

---

## 3. Pipeline shape — LOCKED

```
User (form / CSV upload)
        │
        ▼
┌───────────────────────────────────────────────┐
│ C2 — Input Parser                             │
│   normalize → validate → CompanyInput         │
└───────────────────────────────────────────────┘
        │  CompanyInput
        ▼
┌───────────────────────────────────────────────┐
│ C1 — Anomaly Detection Engine                 │
│   in-process Python call, CPU-bound, no I/O   │
│   analyze_company(CompanyInput)               │
└───────────────────────────────────────────────┘
        │  AnomalyReport
        │
        ├──── refusal is not None ─────────────────┐
        │                                          │
        ▼  refusal is None                         │
┌───────────────────────────────────────────────┐  │
│ C3 — Prescription + Case Match + Narrative    │  │
│   in-process Python call                      │  │
│   enrich_report(AnomalyReport) ──► one LLM    │  │
└───────────────────────────────────────────────┘  │
        │  EnrichedReport                          │
        ▼                                          ▼
┌───────────────────────────────────────────────────┐
│ C2 — Response assembly → UI                       │
│   status: "complete"          status: "refused"   │
└───────────────────────────────────────────────────┘
```

**Locked facts:**

- **Three processing stages, not four.** Prescription, case matching and narrative generation all live inside C3 as one module with one entry point. C2 calls C3 at most once.
- **Both C1 and C3 are in-process Python imports**, not HTTP services. Neither is an "external service." C2 wraps both in `asyncio.to_thread()`.
- **Exactly one LLM call in the whole pipeline**, made by C3. C1's `natural_language_summary` is template-generated, not model-generated. *(Confirmed by C1.)*
- **C2 is the only component that talks to the user.** C1 and C3 never raise to the user; they return valid objects or raise exceptions that C2 catches and translates.
- **Refusal short-circuits in C2.** When C1 returns a report with `refusal` populated, C2 renders it directly and **never calls C3**. C3 must still implement the defensive guard in §6.3, but in normal operation it will never receive a refusal report. There is no LLM call and no cost on the refusal path.

---

## 4. Contract 1 — C2 produces `CompanyInput`

**Owner of the schema:** C1 (defined in `ml_engine/models/input_schema.py`).
**Producer:** C2. **Consumer:** C1.

### 4.1 Shape

```python
CompanyInput
├── company_id: str
├── sector_id: Literal["TECH_SAAS", "RETAIL"]
├── company_metadata: CompanyMetadata
│   ├── name: str
│   ├── founded_year: Optional[int]
│   ├── employee_count: int
│   ├── annual_revenue: Optional[float]
│   ├── revenue_band: Literal["<1M", "1M-10M", "10M-100M", ">100M"]
│   └── region: str
├── reporting_period: ReportingPeriod
│   ├── type: Literal["monthly", "quarterly", "annual"]
│   ├── start: date
│   └── end: date
├── metrics: list[MetricEntry]
│   ├── metric_id: str
│   ├── granularity: Literal["monthly", "quarterly", "annual"]
│   ├── values: list[DataPoint]
│   │   ├── period: str
│   │   ├── value: float
│   │   └── interpolated: bool = False
│   └── confidence: float = 1.0
└── raw_text_context: Optional[str]
```

### 4.2 Rules C2 guarantees

| Rule | Detail |
|---|---|
| Metric IDs are canonical | C2 resolves user-facing names to `metric_id` via alias table before sending. Unknown metrics are **not** sent; the user is told. |
| Periods are normalized | `YYYY-MM` for monthly, `YYYY-QN` for quarterly, `YYYY` for annual. |
| No disaggregation | Quarterly stays quarterly. C2 never splits one observation into several. Any gap-filled point carries `interpolated: true`. |
| Units are validated | Every value checked against `valid_min`/`valid_max` from the metric config, **plus** a distributional check: if every value in a `percentage` metric falls within 0.0–1.0, C2 flags a probable fraction/percent error and asks the user to confirm before submitting. |
| Minimum periods enforced | Hard-block below the per-granularity floor (§4.3). Those metrics are never sent to C1. |
| `granularity` is authoritative | Per-metric `granularity` wins over `reporting_period.type`, which is envelope metadata only. |
| `revenue_band` is derived | If `annual_revenue` is present, C2 derives `revenue_band` from it and overrides any user-supplied band. If `annual_revenue` is null, the user-supplied band is trusted. |
| `confidence` is set | `1.0` form entry · `0.9` clean CSV · `0.75` ambiguous formatting · `1.0` default. |

### 4.3 Minimum periods

*(Agreed. C1 applies the same thresholds internally.)*

| Granularity | Hard block (C2 rejects) | Soft warn (C2 submits, C1 returns partial) | Full trend analysis |
|---|---|---|---|
| Monthly | < 3 | 3–5 | ≥ 6 |
| Quarterly | < 2 | 2–3 | ≥ 4 |
| Annual | < 2 | 2 | ≥ 3 |

---

## 5. Contract 2 — C1 produces `AnomalyReport`

**Owner of the schema:** C1 (`ml_engine/models/output_schema.py`).
**Producer:** C1. **Consumers:** C3 and C2.

### 5.1 Shape

```python
AnomalyReport
├── schema_version: str = "anomaly_report_v1"   # alias "$schema"
├── company_id: str
├── sector_id: str
├── analysis_timestamp: datetime
├── reporting_period: ReportingPeriod
├── company_profile_summary: CompanyProfileSummary
│   ├── revenue_band: str
│   ├── employee_count: int
│   └── region: str
├── overall_health_score: Optional[float] = None    # null on refusal
├── anomalies: list[Anomaly]
│   ├── anomaly_id: str
│   ├── metric_id: str
│   ├── metric_display_name: str
│   ├── category: str
│   ├── severity_score: float
│   ├── severity_label: Literal["INFO","WARNING","CRITICAL","SEVERE"]
│   ├── deviation: DeviationDetail
│   │   ├── observed_current: float
│   │   ├── expected_value: float
│   │   ├── expected_std: float
│   │   ├── z_score: float
│   │   ├── percentile: float
│   │   └── direction: Literal["above_expected","below_expected","as_expected"]
│   ├── trend: TrendDetail
│   │   ├── direction: Literal["improving","stable","deteriorating"]
│   │   ├── slope: Optional[float] = None
│   │   ├── acceleration: Optional[float] = None
│   │   ├── periods_deviating: Optional[int] = None
│   │   └── values_over_time: Optional[list[TrendPoint]] = None
│   ├── correlated_anomalies: list[str]
│   ├── noise_confidence: float
│   ├── context_tags: list[str]
│   └── natural_language_summary: str
├── non_anomalous_highlights: list[HealthyHighlight]
├── refusal: Optional[RefusalDetail] = None
│   ├── reason: RefusalReason              # CONFIRMED
│   ├── message: str                       # PROVISIONAL — see O13
│   └── suggested_resolution: Optional[str] = None   # PROVISIONAL — see O13
└── metadata: ReportMetadata
    ├── model_version, synthetic_profile_version
    ├── metrics_analyzed, metrics_with_anomalies, metrics_with_missing_data
    ├── skipped_metrics: list[str]
    └── processing_time_ms
```

**`RefusalReason` enum** — four values. `CONTRADICTORY_EVIDENCE` is reserved but produced by no current code path:

```
NO_METRICS_SUBMITTED · LOW_DATA_CONFIDENCE · INSUFFICIENT_PERIODS · CONTRADICTORY_EVIDENCE
```

> **Both C2 and C3: do not write a two-branch switch on `refusal.reason`.** Handle all four values or use a default branch, so nothing breaks when the fourth trigger is implemented.

> **Consumers should set `extra="allow"` on `RefusalDetail`.** Only `reason` is confirmed against C1's source; the other two are C2's provisional additions. Pydantic v2 defaults to `extra="ignore"`, which would silently drop any real fields we failed to predict. C2 does not depend on `message` being present — it generates fallback text from `reason` plus the original `CompanyInput`.

### 5.2 Agreed behaviours

| Behaviour | Rule |
|---|---|
| Severity bands | Half-open: `≥75 SEVERE`, `≥50 CRITICAL`, `≥25 WARNING`, else `INFO`. Exactly 50 is `CRITICAL`. |
| Refusal precedence | The all-metrics check runs **first**. If *every* submitted metric is below its trend threshold → `refusal` populated, `anomalies: []`, `overall_health_score: null`, do not route downstream. |
| Mixed history | If *at least one* metric meets its threshold, no refusal. Metrics below it get partial analysis: `z_score`/`percentile`/`expected_std` populated, all `trend` sub-fields null. Anomalies still emitted for those metrics. |
| `confidence` effect | `final_severity = raw_severity × (0.75 + 0.25 × confidence)`. No variance inflation, no suppression. |
| Summary wording | `natural_language_summary` says *"expected baseline for a company of this profile"* — never "sector median", since the baseline is synthetic. |
| Unknown metric IDs | Tracked in `metadata.skipped_metrics`, not silently dropped. |
| Computed highlights | `ltv_cac_ratio` may appear in `non_anomalous_highlights` with a `metric_id` not present in the metric config. Consumers must tolerate this. |

### 5.3 C1 internals — how it actually works

*Read this before building the prescription and case-matching logic. These are facts from the live code, not aspirational descriptions.*

---

#### How synthetic baselines are generated

Each sector is defined by a YAML config (`ml_engine/config/sectors/tech_saas.yaml`, `retail.yaml`). Every metric in the config has a **distribution specification** with a family (`normal`, `lognormal`, or `uniform`) and parameters (`mean`, `std`, `lower_bound`, `upper_bound`).

At analysis time, `SyntheticProfileGenerator` reads the sector config and, for each metric, produces a `CalibratedMetricBaseline` — this is the parametric description of what a "healthy ideal company in this sector and size cohort" would look like for that metric. No sampling occurs during analysis; `expected_value = calibrated_mean` and `expected_std = calibrated_std` are used directly.

The `generate_synthetic_cohort()` method (used for testing/validation) samples 100 synthetic companies per revenue band with `seed=42` — but this is not called during live analysis.

---

#### How `expected_value` and `expected_std` are derived — and how `revenue_band` shifts the baseline

The baseline is **not sector-wide**. It is adjusted per revenue band. Each metric definition in the YAML carries a `size_scaling.revenue_bands` block with a `mean_adjustment` and `std_adjustment` per band. The generator applies the matching band's adjustments additively:

```
calibrated_mean = base_mean + band.mean_adjustment
calibrated_std  = max(base_std + band.std_adjustment, 0.01)
```

This means `expected_value` and `expected_std` in the `AnomalyReport` are always specific to the company's `revenue_band`, not a single sector number. **C3's prescriptions must not treat them as universal sector medians.**

Concrete examples of how the band shifts baselines:

**TECH_SAAS — Churn Rate (%)**

| Band | Expected mean | Expected std |
|---|---|---|
| `<1M` | 3.5% | 1.4% |
| `1M-10M` | 2.0% | 0.8% |
| `10M-100M` | 1.5% | 0.6% |
| `>100M` | 1.0% | 0.5% |

**TECH_SAAS — Customer Acquisition Cost ($)**

| Band | Expected mean | Expected std |
|---|---|---|
| `<1M` | \$3,000 | \$800 |
| `1M-10M` | \$4,500 | \$1,200 |
| `10M-100M` | \$6,500 | \$1,800 |
| `>100M` | \$9,500 | \$2,700 |

The `deviation.expected_value` field in the `AnomalyReport` always reflects the **band-adjusted** value above. Use it directly.

---

#### How noise is separated from signal — what `noise_confidence` measures

A four-layer filter (`MultiLayerNoiseFilter`) runs on every metric before it can be classified as an anomaly. All four layers must pass:

| Layer | What it checks | Rejection reason if it fails |
|---|---|---|
| **L1 — Statistical threshold** | `|z_score| ≥ 1.5` (configurable `z_threshold_flag`) | Deviation is within normal variation |
| **L2 — Persistence** | If ≥ 6 periods: `periods_deviating ≥ 2`. If < 6 periods: `|z_score| ≥ 2.5` | Transient spike, not a structural shift |
| **L3 — Correlation consistency** | No strongly correlated metric is moving in the opposite direction (sign conflict with `|z| ≥ 1.5` in the correlated metric) | Deviation contradicted by related metrics |
| **L4 — Seasonality** | If the metric has `seasonality.enabled: true`, the deviation must exceed the seasonal amplitude or meet the alert threshold | Deviation falls within expected seasonal swing |

`noise_confidence` is the filter's estimated probability that the deviation is a true structural signal (0.0–1.0). It is computed only when all four layers pass:

```
base_conf     = min(|z_score| / 5.0, 0.65)
pers_bonus    = +0.20 if periods_deviating ≥ 3
                +0.10 if periods_deviating ≥ 2
                 0.00 otherwise
corr_bonus    = +0.15 if at least one correlated metric is also deviating consistently
interp_penalty = -0.30 × interpolated_ratio

noise_confidence = clip(base_conf + pers_bonus + corr_bonus − interp_penalty, 0.30, 0.99)
```

Metrics that fail any filter layer are **not emitted as anomalies** — they may appear as healthy highlights if their direction is favourable, or be silently excluded otherwise.

---

#### How `severity_score` is computed

Five components, each capped at a maximum, sum to a raw score which is then scaled by `data_confidence`:

| Component | Max pts | Formula |
|---|---|---|
| **Magnitude** | 30 | `min(|z_score| / 4.0, 1.0) × 30` |
| **Persistence** | 20 | `min(periods_deviating / 6.0, 1.0) × 20` *(if no trend support: 2 periods assumed if |z| ≥ 2.5, else 1)* |
| **Trajectory** | 20 | `min((|slope| / std) / 0.5, 1.0) × 20` *(0 if no trend support)* |
| **Importance** | 15 | `min(metric_weight, 1.0) × 15` *(metric weight from YAML config)* |
| **Correlation support** | 15 | `15` if at least one correlated anomaly confirmed, `0` otherwise |

```
raw_total         = sum of above components   (max: 100)
confidence_factor = 0.75 + (0.25 × data_confidence)
severity_score    = clip(raw_total × confidence_factor, 0.0, 100.0)
```

`data_confidence` is the per-metric `confidence` field from `CompanyInput` (set by C2). At full confidence (1.0) the factor is 1.0; at minimum trackable confidence (≈0.4) it is 0.85.

---

#### How `overall_health_score` is aggregated

The score (0–100) is a **weighted average of per-metric health contributions**, using each metric's `weight` from the sector YAML:

```
For HIGHER_IS_BETTER metrics:  metric_health = percentile
For LOWER_IS_BETTER metrics:   metric_health = 100 − percentile
For TARGET_BAND metrics:       metric_health = max(0, 100 − |percentile − 50| × 2)

overall_health_score = Σ(metric_health × weight) / Σ(weight)
```

Percentiles are computed against the band-adjusted normal distribution using `scipy.stats.norm.cdf`. The score is rounded to 1 decimal place and clipped to [0.0, 100.0]. On refusal, the field is `null`.

---

#### How `correlated_anomalies` is determined — **important for C3 clustering**

`correlated_anomalies` is **a lookup against a hardcoded correlation matrix defined in the sector YAML**, not a computed or co-occurrence-based correlation.

The correlation matrix is defined per sector under `correlation_matrix:` in the YAML. The `CorrelationEngine` reads it at analysis time. For a given anomaly's metric, it calls `get_correlated_metrics(metric_id, threshold=0.5)` — returning all metrics with `|correlation_coefficient| ≥ 0.5`.

After all anomalies are detected, a post-pass links them: for each anomaly, it looks up which of its correlated metrics *also* became anomalies, and sets `correlated_anomalies` to their `anomaly_id` values.

**Full correlation matrices (both sectors):**

**TECH_SAAS:**

| Metric A | Metric B | Coefficient |
|---|---|---|
| `monthly_recurring_revenue_growth` | `churn_rate` | −0.65 |
| `monthly_recurring_revenue_growth` | `net_revenue_retention` | +0.78 |
| `churn_rate` | `net_revenue_retention` | −0.80 |
| `net_revenue_retention` | `lifetime_value` | +0.55 |
| `customer_acquisition_cost` | `burn_rate` | +0.60 |

**RETAIL:**

| Metric A | Metric B | Coefficient |
|---|---|---|
| `gross_margin` | `inventory_turnover` | +0.52 |
| `gross_margin` | `same_store_sales_growth` | +0.45 *(below 0.5 threshold — not linked)* |
| `gross_margin` | `return_rate` | −0.50 *(borderline — at threshold, included)* |
| `inventory_turnover` | `sell_through_rate` | +0.65 |
| `average_order_value` | `revenue_per_sqft` | +0.60 |
| `average_order_value` | `customer_acquisition_cost` | −0.40 *(below 0.5 threshold — not linked)* |
| `revenue_per_sqft` | `same_store_sales_growth` | +0.55 |

> **C3 note:** `correlated_anomalies` only lists anomaly IDs for metrics that *also* tripped as anomalies. A metric can be correlated in the matrix but absent from `correlated_anomalies` simply because it didn't deviate enough. Use `correlated_anomalies` as a cluster seed, not as a complete correlation map.

---

#### How `context_tags` are assigned — full vocabulary

`context_tags` are a **fixed vocabulary assigned statically per metric in the sector YAML**. They are not generated at runtime. The full set across both sectors is:

**TECH_SAAS context tags:**

| metric_id | context_tags |
|---|---|
| `monthly_recurring_revenue_growth` | `growth_decline`, `topline`, `saas_velocity` |
| `churn_rate` | `churn_related`, `retention_leak`, `customer_attrition` |
| `customer_acquisition_cost` | `cac_inflation`, `acquisition_efficiency`, `sales_burn` |
| `lifetime_value` | `ltv_decay`, `monetization`, `customer_worth` |
| `net_revenue_retention` | `nrr_drop`, `expansion_revenue`, `account_health` |
| `burn_rate` | `runway_crisis`, `burn_spike`, `capital_efficiency` |
| `gross_margin` | `margin_compression`, `cogs_inflation`, `gross_profit` |

**RETAIL context tags:**

| metric_id | context_tags |
|---|---|
| `gross_margin` | `retail_margin`, `pricing_pressure`, `margin_erosion` |
| `inventory_turnover` | `dead_stock`, `inventory_velocity`, `working_capital` |
| `average_order_value` | `basket_size`, `pricing_elasticity`, `aov_drop` |
| `revenue_per_sqft` | `store_productivity`, `footfall_efficiency`, `retail_yield` |
| `same_store_sales_growth` | `comp_sales`, `store_growth`, `retail_velocity` |
| `sell_through_rate` | `inventory_clearance`, `sell_through`, `stock_efficiency` |
| `customer_acquisition_cost` | `cac_inflation`, `customer_acquisition`, `ad_spend_efficiency` |
| `return_rate` | `product_returns`, `refund_rate`, `return_leakage` |

> **C3 note:** If you embed against `context_tags` for case matching, this is the complete vocabulary. No tags will appear at runtime that aren't in this list.

---

#### What triggers a refusal — complete list

Three and only three conditions trigger a refusal (checked in this order):

1. **No metrics submitted** — `CompanyInput.metrics` is empty.
2. **All metrics have low data confidence** — every metric's `confidence < 0.35`.
3. **All metrics are below the minimum periods for their granularity** — every single metric has fewer data points than the trend floor (`monthly < 6`, `quarterly < 4`, `annual < 3`). If *at least one* metric clears its floor, no refusal is issued; the short metrics receive partial analysis.

There are no other active refusal triggers — no sector-based refusals, no score-threshold refusals, no missing-field refusals. Everything else produces a valid (possibly partial) `AnomalyReport`.

> **C3 note — third `RefusalReason` value:** The enum in `output_schema.py` defines a third value `CONTRADICTORY_EVIDENCE = "contradictory_evidence"` which is reserved but **not triggered by any code path in the current `refusal.py`**. Do not hardcode a two-value switch on `refusal.reason`; handle all three values (or use a default/pass-through) so this doesn't break when the trigger is added.

---

## 6. Contract 3 — C3 produces `EnrichedReport`

**Producer:** C3. **Consumer:** C2.

### 6.1 The governing rule — additive enrichment, never replacement

> **C3 must return the `AnomalyReport` it received, unmodified, as a nested field.** Everything C3 adds sits alongside it.

This is non-negotiable and it's the reason this document exists. The previously circulated `prescriptive_report_v1` dropped `category`, `deviation`, `trend`, `severity_score`, `correlated_anomalies`, `noise_confidence`, `company_profile_summary`, and `non_anomalous_highlights` — **eight of the ten fields the Case Matcher handout instructs C3 to use for matching**, and everything the UI needs to render. It also renamed `anomalies` → `detected_anomalies` and `metric_id` → `source_metric`.

C3 needs those fields for its own matching logic; C2 needs them for the UI. Nothing is gained by dropping them.

### 6.2 Shape `[PROPOSED — C3 to confirm or amend]`

```python
EnrichedReport
├── schema_version: str = "enriched_report_v1"
├── anomaly_report: AnomalyReport          # verbatim, untouched
├── prescriptions: list[Prescription]
│   ├── anomaly_id: str                    # FK into anomaly_report.anomalies
│   ├── prescribed_adjustments: list[Adjustment]
│   │   ├── target_metric_id: str
│   │   ├── target_display_name: str
│   │   ├── action: Literal["INCREASE","DECREASE"]
│   │   ├── direction_symbol: Literal["+","-"]
│   │   ├── current_value: Optional[float] = None   # null if not submitted — see 6.4
│   │   ├── current_value_source: Literal["submitted","not_available"]
│   │   ├── target_value: float
│   │   ├── target_basis: str              # e.g. "profile_baseline", "top_quartile"
│   │   ├── delta: Optional[float] = None  # null when current_value is null
│   │   ├── priority: Literal["HIGH","MEDIUM","LOW"]
│   │   └── rationale: str
│   └── prescription_summary: str          # C3's own text — distinct field name
├── anomaly_clusters: list[list[str]]      # anomaly_ids grouped by correlation
├── matched_cases: list[MatchedCase]
│   ├── case_id, cluster_index
│   ├── similarity_score: float
│   ├── problem_description, root_causes, recommended_actions
├── narrative: Optional[Narrative] = None
│   ├── situation_summary: str
│   ├── likely_root_causes: list[str]
│   ├── prioritized_actions: list[ActionItem]
│   └── positives: list[str]
└── metadata: EnrichmentMetadata
    ├── llm_model, llm_tokens_used, processing_time_ms
    ├── cases_searched, cases_matched
    ├── unmatched_anomaly_ids: list[str]
    └── degraded: bool
```

### 6.3 Refusal handling — MANDATORY defensive guard

**Primary behaviour lives in C2.** When C1 returns a report with `refusal` populated, C2 short-circuits and does not call C3 at all (§3). In normal operation C3 will never receive a refusal report.

**C3 must still implement the guard.** It costs three lines and protects against any future call path that forgets the check. First statement in `enrich_report()`:

```
if anomaly_report.refusal is not None:
    return EnrichedReport(
        anomaly_report = <passed through unchanged>,
        prescriptions  = [],
        anomaly_clusters = [],
        matched_cases  = [],
        narrative      = None,
        metadata       = EnrichmentMetadata(degraded=False, ...)
    )
```

**No LLM call. No prescriptions. No invented explanation.** A refusal means the evidence was insufficient; generating a narrative anyway is precisely the failure mode the refusal exists to prevent.

The refusal path is a flagship demo scenario, not an edge case. It must be explicitly tested on both sides.

### 6.4 `current_value` must never be invented

The circulated example prescribed `onboarding_completion_rate` with `current_value: 63.0` and `customer_acquisition_cost` with `current_value: 470.0` — **neither metric appeared in the input**, and `onboarding_completion_rate` isn't in the metric config at all.

Rule: `current_value` may only be populated from a metric the user actually submitted. Otherwise `current_value: null`, `current_value_source: "not_available"`, `delta: null`, and the rationale phrases the target as a benchmark rather than a change.

Recommending a lever the company doesn't currently measure is fine and useful. **Asserting its present value is not.** If a judge asks "how do you know their onboarding completion is 63%?" there is no acceptable answer.

### 6.5 Prescription rules

- **Rule table must be sector-gated.** A SaaS target (e.g. `churn_rate`) is never prescribed for a RETAIL anomaly.
- **Coverage:** the circulated matrix has 4 rules (3 SaaS, 1 RETAIL). RETAIL now has 8 metrics. `[C3: what happens to an anomaly with no matching rule?]` Proposed default: emit the anomaly with `prescriptions: []` and list its ID in `metadata.unmatched_anomaly_ids`. Never fabricate a generic prescription.
- **`target_value` and `target_basis` must use C1's band-adjusted baselines.** The `deviation.expected_value` in the `AnomalyReport` is already band-adjusted (see §5.3). Use it directly as your "Profile Baseline" target. Do not re-derive it. For "Top Quartile" targets, apply the appropriate percentile shift to the band-adjusted distribution parameters also provided in the report.
- **`priority` derivation must be stated.** `[C3: from severity_label, from the rule table, or both?]`
- **Do not recompute anything from C1.** Never modify `severity_score`, `severity_label`, or `z_score`.

### 6.6 Field naming

- No renaming of C1 fields anywhere. `anomalies` stays `anomalies`; `metric_id` stays `metric_id`.
- C3's own summary text is `prescription_summary`, **not** `natural_language_summary`. Two components generating a field with the same name at different levels is how the earlier drafts lost C1's statistical detail. C1's `natural_language_summary` stays on the anomaly, untouched.
- Schema fields use `schema_version` with `alias="$schema"` and `populate_by_name=True`, matching C1's convention.

### 6.7 Degradation

C3 must return a valid `EnrichedReport` even when parts fail:

| Failure | Behaviour |
|---|---|
| No case matches above threshold | `matched_cases: []`, continue to narrative |
| LLM call fails or times out | `narrative: None`, `metadata.degraded: true`, everything else populated |
| No prescription rule matches | `prescriptions: []` for that anomaly, ID in `unmatched_anomaly_ids` |

C2 renders partial results. A demo that shows anomalies without a narrative survives; a 500 doesn't.

---

## 7. Contract 4 — C2 produces the API response

**Producer:** C2. **Consumer:** frontend.

```
POST /analyze          run pipeline
GET  /metrics/{sector} canonical metric list for the sector
POST /validate         dry-run the parser, return proposed metric mapping for user confirmation
POST /feedback         record user verdict on a report
GET  /health           liveness + component import check
```

Response envelope is identical whether returned synchronously or polled, so we can switch without changing the frontend:

```json
{ "job_id": "...", "status": "complete|running|failed|refused",
  "result": { <EnrichedReport> },
  "warnings": [ { "code": "...", "message": "..." } ],
  "error": null }
```

### 7.1 What C2 renders

| Case | UI |
|---|---|
| Normal | Health score, severity-coloured anomaly cards, prescriptions, matched cases, narrative, highlights |
| Refusal | Health score as **"N/A"** (never "50/100"), refusal reason, what data would resolve it. No prescriptions, no narrative. |
| Degraded | Everything available, plus a banner noting the narrative is unavailable |
| Skipped metrics | Warning listing unrecognised `metric_id`s from `metadata.skipped_metrics` |

---

## 8. Cross-cutting rules

| Rule | Applies to |
|---|---|
| Never invent a number that isn't computed or submitted | All |
| Never modify a value produced by an upstream component | C3 |
| Never raise to the user; return a valid object or raise for C2 to catch | C1, C3 |
| One LLM call total, in C3 | All |
| Repo code is canonical; handouts are commentary | All |
| Serialize with `model_dump(by_alias=True)` at every component boundary | All |

**Note on the last one:** Pydantic v2's `model_dump()` defaults to `by_alias=False`, so it emits `schema_version`, not `$schema`. An earlier note had this backwards. If we want `$schema` on the wire, `by_alias=True` must be passed explicitly. Simplest resolution: **nobody validates on the schema field for MVP.**

---

## 9. Open items requiring sign-off

| # | Item | Owner | Status |
|---|---|---|---|
| 1 | Is C3 one module or several? | C3 | One module, one entry point `enrich_report()` |
| 2 | Does the `AnomalyReport` survive C3 intact? | C3 | Yes — §6.1 |
| 3 | `current_value` for unsubmitted metrics | C3 | Null + `not_available` — §6.4 |
| 4 | Refusal path through C3 | C3 | Pass through, no LLM — §6.3 |
| 5 | Prescription rule coverage for 8 RETAIL metrics | C3 | **Open — C3 to state coverage or confirm `unmatched_anomaly_ids` fallback** |
| 6 | Numeric source for the four `target_basis` strategies | C1 + C3 | **Resolved by C1:** use `deviation.expected_value` (band-adjusted) from the report directly. Top-quartile = apply percentile shift to the same distribution parameters. |
| 7 | `priority` derivation | C3 | **Open — C3 to state rule** |
| 8 | What `correlated_anomalies` actually means | C1 | **Resolved — §5.3.** It is a lookup against the hardcoded sector correlation matrix (threshold ≥ 0.5), not computed co-occurrence. |
| 9 | Full `context_tags` vocabulary | C1 | **Resolved — §5.3.** Complete fixed vocabulary listed. |
| 10 | Repo access for C2 and C3 | C1 | Push `ml_engine` now, even with a stubbed `analyze_company()` |

### New in v1.1 — from C2's review of §5.3

| # | Item | Owner | Detail |
|---|---|---|---|
| **11** | **Silently excluded metrics have no explanation** | C1 | §5.3 states that metrics failing any noise-filter layer "may appear as healthy highlights if their direction is favourable, or be silently excluded otherwise." They are invisible in `skipped_metrics` (that field is only for unrecognised IDs). A user submits 8 metrics, sees 5, and C2 cannot say what happened to the other 3. **Request:** expose `metadata.filtered_metrics: [{metric_id, rejected_at, reason}]`. The filter already computes the rejection reason per layer — it just isn't surfaced. This turns a confusing hole into the system's best noise-vs-signal demo moment: *"we looked at burn rate and concluded the movement was noise."* |
| **12** | **`revenue_band` boundary convention undefined** | C1 | Baselines are band-adjusted (§5.3), so the band determines every `expected_value` downstream. C2 derives the band from `annual_revenue`. Is `10_000_000` in `1M-10M` or `10M-100M`? C2 is proceeding on **lower bound inclusive, upper exclusive** (→ `10M-100M`). Confirm or correct. |
| **13** | **`direction: "as_expected"` semantics** | C1 | A third value was added to `DeviationDirection`. `HealthyHighlight` carries no `deviation` block, so it can only appear on an `Anomaly` — but an anomaly deviated by definition. When is it emitted? C2's UI switches on this field. Also: `RefusalDetail`'s field list beyond `reason` is unverified (§5.1). |
| **14** | **Percentiles use `norm.cdf` for non-normal distributions** | C1 | §5.3 says distribution families include `lognormal` (likely CAC, burn rate, LTV), but percentile is computed via `scipy.stats.norm.cdf`. Since `overall_health_score` is percentile-derived, this skews the number we display most prominently. Low priority, but worth a sanity check. |

---

## 10. MVP scope — locked, do not expand

**In:** manual form + CSV input · `TECH_SAAS` + `RETAIL` · alias-table metric matching · in-memory storage · `POST /feedback` logging to file · one LLM call · refusal path · degraded-mode rendering.

**Out:** PDF/OCR · Excel · `MFG` sector · auth · rate limiting · database persistence · fuzzy scoring beyond the alias table · multi-company comparison · historical trend across submissions.

**Deferred but designed:** the "Living Knowledge Base" feedback loop (endpoint exists, storage is a file), entity masking, dynamic user profiling. We present these as roadmap, not as built. **Please keep deck claims consistent with this list** — a judge comparing the deck to the demo is the most likely way we lose points.

---

## 11. Sign-off

Nobody codes against a contested contract. Please add your name and date once your section is accurate.

| Component | Owner | Reviewed | Notes / objections |
|---|---|---|---|
| C1 — Detection | | | |
| C2 — API | | | |
| C3 — Prescription / Case / LLM | | | |

**Changes after sign-off** go in this document first, announced in the group, and only then in code. If something here is wrong or unbuildable, say so — it will be changed. What we can't absorb before Sunday is three components silently building against three different shapes.

---

## 12. Implementation consequences of §5.3

C1's internals are documented above. These are the four places where they will actually change what C2 and C3 build. New in v1.1.

### 12.1 Expected values are band-specific — C3 must not re-derive them

`deviation.expected_value` and `expected_std` are already adjusted for the company's `revenue_band` (churn expects 3.5% at `<1M` but 1.0% at `>100M`). They are **not** sector medians.

- **C3:** use `deviation.expected_value` directly as the "profile baseline" target. For a top-quartile target, apply the percentile shift to `expected_value` / `expected_std` from the same report. Never hardcode a sector constant.
- **C2:** the `revenue_band` we derive changes every baseline downstream — hence O12.

### 12.2 `correlated_anomalies` is a filtered view, not a correlation map

It is a lookup against the hardcoded sector correlation matrix (threshold `|r| ≥ 0.5`), then filtered to metrics that **also** tripped as anomalies.

**C3:** a metric can be strongly correlated yet absent from `correlated_anomalies` simply because it didn't deviate. Use the field as a **cluster seed**, not as a complete relationship graph. If you need the full graph for reasoning, read the matrix in §5.3 directly.

### 12.3 `context_tags` are a closed vocabulary

Statically assigned per metric in the sector YAML — never generated at runtime. The complete set is listed in §5.3 (21 unique tags across 13 metrics).

**C3:** you can pre-compute embeddings for the entire vocabulary at build time. No tag will ever appear that isn't on that list, so unknown-tag handling is unnecessary — but a warning log is cheap insurance if C1 extends the list later.

### 12.4 Severity depends on breadth of submission — matters for fixtures and demos

From the §5.3 formula: **correlation support is worth 15 points and requires a second correlated metric to also trip**, and **trajectory is worth 20 and is zero without trend support** (below 6 monthly / 4 quarterly / 3 annual periods).

Consequence: a single metric with a short series caps near **52** — barely `CRITICAL`. **A `SEVERE` anomaly is only reachable with at least two correlated metrics, both above their trend floor.**

The strongest pairs available:

| Sector | Pair | Coefficient |
|---|---|---|
| TECH_SAAS | `churn_rate` ↔ `net_revenue_retention` | −0.80 |
| TECH_SAAS | `monthly_recurring_revenue_growth` ↔ `net_revenue_retention` | +0.78 |
| RETAIL | `inventory_turnover` ↔ `sell_through_rate` | +0.65 |

**All three of us should build demo fixtures around these pairs.** A demo built on a single metric will render as a mild warning and undersell the system.

One caution: noise-filter layer L3 **suppresses** an anomaly when a strongly correlated metric moves in the opposite direction. Don't construct a fixture where that happens by accident — the metric will vanish from the report with no explanation (O11).