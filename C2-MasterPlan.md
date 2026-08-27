# C2 — API, Parsing & Orchestration
## Master Build Plan & Source of Truth

**Owner:** C2 (API component)
**Last updated:** after C1 returned the completed Pipeline Contract v1
**Purpose:** single context document for this component. Drop this into Claude Code / Antigravity as project context. Everything needed to build C2 without re-reading the four handouts is here.

---

# PART I — PROJECT CONTEXT

## 1. What this project is

**businessintelligence.ai** — a submission for the Accenture Innovation Challenge 2026, Problem Statement 3.

**The problem statement asks for:** a KPI storytelling engine — an AI system that explains in natural language what changed in a business metric, identifies likely root causes, and recommends next steps, using both structured and unstructured data. It explicitly asks how the system separates meaningful change from noise, how it moves from correlation to action, and what it does when data is genuinely ambiguous.

**What we are building:** a company submits its recent business metrics. The system compares them against a synthetic baseline for a healthy company of the same sector and size, detects statistically meaningful deviations, prescribes which operational parameters to change and in which direction, retrieves similar historical cases, and produces an executive narrative — or explicitly refuses to guess when the evidence is insufficient.

**Deadline:** MVP by Sunday. Classes in between. Scope is locked in §16 and must not expand.

## 2. Pipeline architecture

```
User (form / CSV upload)
        │
        ▼
┌──────────────────────────────────────────────────┐
│ C2 — Input Parser                                │
│   normalize → validate → CompanyInput            │
└──────────────────────────────────────────────────┘
        │  CompanyInput
        ▼
┌──────────────────────────────────────────────────┐
│ C1 — Anomaly Detection Engine                    │
│   in-process, CPU-bound, no network I/O          │
│   analyze_company(CompanyInput) → AnomalyReport  │
└──────────────────────────────────────────────────┘
        │  AnomalyReport
        ▼
┌──────────────────────────────────────────────────┐
│ C3 — Prescription + Case Match + Narrative       │
│   in-process. Contains the pipeline's ONLY LLM   │
│   enrich_report(AnomalyReport) → EnrichedReport  │
└──────────────────────────────────────────────────┘
        │  EnrichedReport
        ▼
┌──────────────────────────────────────────────────┐
│ C2 — Response assembly → Frontend                │
└──────────────────────────────────────────────────┘
```

**Locked facts:**

- Three processing stages, not four. C2 calls C3 exactly once.
- Both C1 and C3 are **in-process Python imports**, not HTTP services. Wrap both in `asyncio.to_thread()`.
- Exactly **one LLM call** in the whole pipeline, inside C3. C1's `natural_language_summary` is template-generated.
- C2 is the **only** component that talks to the user. C1 and C3 return valid objects or raise for C2 to catch.

## 3. Component ownership

| Component | Owns |
|---|---|
| **C1** | Synthetic sector baselines, statistical detection, noise filtering, severity scoring, refusal decision |
| **C2 (us)** | Input ingestion, normalization, validation, orchestration, error handling, API surface, **frontend** |
| **C3** | Parameter prescriptions, case retrieval, LLM narrative |

## 4. What C2 actually owns — read this twice

The role title says "Input Parser & API Developer." That undersells it. C2 owns **the spine**:

- Both other components are libraries we call. Their exceptions become our 500s.
- Every failure surfaces through us. If the demo breaks on stage, it breaks in our code.
- **We own the frontend** (confirmed by C1's built/roadmapped table: anomaly cards, severity colouring, refusal view).
- We are last in the dependency chain — both dependencies will land late. **Mocks are the only defence.**

---

# PART II — DATA CONTRACTS

## 5. `models.py` — shared schema

This file is canonical for C2. C1 owns the upstream definitions in `ml_engine/models/`; where we differ, differences are marked and logged in §9.

> **Rule:** C1's repo code is canonical over any handout prose. Where this file disagrees with the repo, the repo wins — re-sync and update §9.

### 5.1 Enums

```python
from enum import Enum

class SectorId(str, Enum):
    TECH_SAAS = "TECH_SAAS"
    RETAIL    = "RETAIL"
    # MFG is OUT OF SCOPE for MVP

class RevenueBand(str, Enum):
    UNDER_1M    = "<1M"
    ONE_TO_10M  = "1M-10M"
    TEN_TO_100M = "10M-100M"
    OVER_100M   = ">100M"

class Granularity(str, Enum):
    MONTHLY   = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL    = "annual"

class SeverityLabel(str, Enum):
    INFO     = "INFO"
    WARNING  = "WARNING"
    CRITICAL = "CRITICAL"
    SEVERE   = "SEVERE"

class DeviationDirection(str, Enum):
    ABOVE_EXPECTED = "above_expected"
    BELOW_EXPECTED = "below_expected"
    AS_EXPECTED    = "as_expected"      # added by C1 — semantics OPEN, see §9

class TrendDirection(str, Enum):
    IMPROVING     = "improving"
    STABLE        = "stable"
    DETERIORATING = "deteriorating"

class RefusalReason(str, Enum):
    NO_METRICS_SUBMITTED  = "no_metrics_submitted"
    LOW_DATA_CONFIDENCE   = "low_data_confidence"
    INSUFFICIENT_PERIODS  = "insufficient_periods"
    CONTRADICTORY_EVIDENCE = "contradictory_evidence"   # reserved, never triggered
```

> **Do not write a two-branch switch on `RefusalReason`.** `CONTRADICTORY_EVIDENCE` is defined but not currently produced by any code path. Handle it (or default) so the UI doesn't break when the trigger lands. Exact string values are inferred from the enum names C1 described — **verify against the repo.**

### 5.2 Input contract — `CompanyInput`

Produced by **C2**, consumed by **C1**.

```python
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Literal
from datetime import date

class DataPoint(BaseModel):
    period: str                 # "YYYY-MM" | "YYYY-QN" | "YYYY"
    value: float
    interpolated: bool = False  # True if C2 gap-filled this point

class MetricEntry(BaseModel):
    metric_id: str              # MUST be canonical — C1 rejects unknown IDs
    granularity: Granularity    # AUTHORITATIVE over reporting_period.type
    values: list[DataPoint] = Field(min_length=1)
    confidence: float = 1.0     # 0–1

class ReportingPeriod(BaseModel):
    type: Granularity           # envelope metadata only
    start: date
    end: date

class CompanyMetadata(BaseModel):
    name: str
    founded_year: Optional[int] = None
    employee_count: int
    annual_revenue: Optional[float] = None
    revenue_band: RevenueBand   # DERIVED by C2 from annual_revenue when present
    region: str

class CompanyInput(BaseModel):
    company_id: str
    sector_id: SectorId
    company_metadata: CompanyMetadata
    reporting_period: ReportingPeriod
    metrics: list[MetricEntry]
    raw_text_context: Optional[str] = None
```

### 5.3 Output contract — `AnomalyReport`

Produced by **C1**, consumed by **C3** and **C2**.

```python
class TrendPoint(BaseModel):
    period: str
    value: float
    z_score: float

class DeviationDetail(BaseModel):
    observed_current: float
    expected_value: float       # BAND-ADJUSTED — not a universal sector median
    expected_std: float         # BAND-ADJUSTED
    z_score: float
    percentile: float
    direction: DeviationDirection

class TrendDetail(BaseModel):
    direction: TrendDirection
    slope: Optional[float] = None
    acceleration: Optional[float] = None
    periods_deviating: Optional[int] = None
    values_over_time: Optional[list[TrendPoint]] = None
    # All Optionals are null when the metric has fewer than the
    # trend-analysis floor for its granularity (see §7.2)

class Anomaly(BaseModel):
    anomaly_id: str
    metric_id: str
    metric_display_name: str
    category: str                       # e.g. "revenue", "retention"
    severity_score: float               # 0–100
    severity_label: SeverityLabel
    deviation: DeviationDetail
    trend: TrendDetail
    correlated_anomalies: list[str]     # anomaly_ids
    noise_confidence: float             # 0–1; P(signal), not P(noise)
    context_tags: list[str]             # fixed vocabulary — §8.3
    natural_language_summary: str       # template-generated by C1, NOT an LLM

class HealthyHighlight(BaseModel):
    metric_id: str          # may be a COMPUTED id absent from metric config
    status: str             # e.g. "healthy"
    percentile: float
    note: str

class RefusalDetail(BaseModel):
    reason: RefusalReason
    # FIELD LIST UNVERIFIED — confirm against repo before building the refusal UI.
    # Expect at minimum a human-readable message and ideally a
    # "what data would resolve this" field.

class ReportMetadata(BaseModel):
    model_version: str
    synthetic_profile_version: Optional[str] = None
    metrics_analyzed: int
    metrics_with_anomalies: int
    metrics_with_missing_data: int
    skipped_metrics: list[str] = []     # unrecognised metric_ids
    processing_time_ms: int

class CompanyProfileSummary(BaseModel):
    revenue_band: RevenueBand
    employee_count: int
    region: str

class AnomalyReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: str = Field(default="anomaly_report_v1", alias="$schema")
    company_id: str
    sector_id: SectorId
    analysis_timestamp: datetime
    reporting_period: ReportingPeriod
    company_profile_summary: CompanyProfileSummary
    overall_health_score: Optional[float] = None   # NULL ON REFUSAL
    anomalies: list[Anomaly] = []
    non_anomalous_highlights: list[HealthyHighlight] = []
    refusal: Optional[RefusalDetail] = None
    metadata: ReportMetadata
```

### 5.4 `EnrichedReport` — C3's output

**PROPOSED. C3 has not signed off.** Build mocks against this; expect revision.

**Governing rule:** C3 returns the `AnomalyReport` it received **verbatim as a nested field**. Enrichment is additive, never replacement.

```python
class Adjustment(BaseModel):
    target_metric_id: str
    target_display_name: str
    action: Literal["INCREASE", "DECREASE"]
    direction_symbol: Literal["+", "-"]
    current_value: Optional[float] = None            # NULL if not submitted
    current_value_source: Literal["submitted", "not_available"]
    target_value: float
    target_basis: str                                # "profile_baseline" | "top_quartile" | ...
    delta: Optional[float] = None                    # NULL when current_value is null
    priority: Literal["HIGH", "MEDIUM", "LOW"]
    rationale: str

class Prescription(BaseModel):
    anomaly_id: str                                  # FK into anomaly_report.anomalies
    prescribed_adjustments: list[Adjustment]
    prescription_summary: str    # NOT "natural_language_summary" — name collision

class MatchedCase(BaseModel):
    case_id: str
    cluster_index: int
    similarity_score: float
    problem_description: str
    root_causes: list[str]
    recommended_actions: list[str]

class ActionItem(BaseModel):
    action: str
    priority: str
    rationale: str

class Narrative(BaseModel):
    situation_summary: str
    likely_root_causes: list[str]
    prioritized_actions: list[ActionItem]
    positives: list[str]

class EnrichmentMetadata(BaseModel):
    llm_model: Optional[str] = None
    llm_tokens_used: Optional[int] = None
    processing_time_ms: int
    cases_searched: int
    cases_matched: int
    unmatched_anomaly_ids: list[str] = []
    degraded: bool = False

class EnrichedReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_version: str = Field(default="enriched_report_v1", alias="$schema")
    anomaly_report: AnomalyReport        # VERBATIM, UNTOUCHED
    prescriptions: list[Prescription] = []
    anomaly_clusters: list[list[str]] = []
    matched_cases: list[MatchedCase] = []
    narrative: Optional[Narrative] = None
    metadata: EnrichmentMetadata
```

### 5.5 C2-internal models

Ours alone. Nobody else depends on these.

```python
class MappingProposal(BaseModel):
    """One resolved column from an uploaded file."""
    source_label: str                    # header as written by the user
    resolved_metric_id: Optional[str]    # None if unresolvable
    match_type: Literal["exact", "alias", "normalized", "unresolved"]
    unit_warning: Optional[str] = None   # e.g. fraction/percent suspicion
    sample_values: list[float] = []

class ParseWarning(BaseModel):
    code: str          # "UNIT_SCALE_SUSPECT" | "SHORT_SERIES" | "UNKNOWN_METRIC" | ...
    metric_id: Optional[str] = None
    message: str

class ParseResult(BaseModel):
    company_input: Optional[CompanyInput]
    proposals: list[MappingProposal]
    warnings: list[ParseWarning]
    blocking_errors: list[str]

class ApiResponse(BaseModel):
    """Envelope. Identical shape whether sync or polled — so we can switch
    without touching the frontend."""
    job_id: str
    status: Literal["complete", "running", "failed", "refused"]
    result: Optional[EnrichedReport] = None
    warnings: list[ParseWarning] = []
    error: Optional[str] = None
```

---

# PART III — WHAT C2 GUARANTEES

## 6. Parsing & normalization rules

| Rule | Detail |
|---|---|
| Canonical metric IDs | Resolve user labels via alias table before sending. Unknown metrics are **not** sent — the user is told. |
| Period normalization | `YYYY-MM` monthly, `YYYY-QN` quarterly, `YYYY` annual. |
| **No disaggregation** | Quarterly stays quarterly. Never split one observation into three — it fabricates data, inflates *n*, and shrinks apparent variance. Gap-filled points carry `interpolated: true`. |
| Unit validation | Every value checked against `valid_min`/`valid_max`, **plus** the distributional check below. |
| Minimum periods | Hard-block below the floor in §7.2. Those metrics are never sent. |
| `granularity` authoritative | Per-metric `granularity` wins over `reporting_period.type`. |
| `revenue_band` derived | From `annual_revenue` when present; overrides user-supplied band. If `annual_revenue` is null, trust the user's band. **Boundary convention still OPEN — §9.** |
| `confidence` assignment | `1.0` form · `0.9` clean CSV · `0.75` ambiguous formatting · `1.0` default |

### 6.1 The distributional unit check — build this, it is not optional

Range validation **cannot** catch scale errors, because the wrong scale is inside the valid range. `gross_margin: 0.72` sits comfortably within `valid_min: -100 / valid_max: 100`. So does `churn_rate: 0.085`.

**The check:** for any metric with `unit: percentage`, if **every** value in the series falls within `0.0–1.0`, flag as a probable fraction/percent encoding error and ask the user to confirm before submitting.

Why it matters: C1's baselines use whole-number percentages (`churn_rate` mean = `2.0` meaning 2%; `gross_margin` mean = `75.0` meaning 75%). A fraction-encoded submission produces a confident `SEVERE` anomaly that is pure artifact. **This is the single most likely way we show a visibly wrong number during the demo.** Cost: about an hour.

### 6.2 Alias resolution

C1's resolver is exact-match after `lower()` + `strip()`. That misses `mrr-growth`, `MRR_Growth`, `MRR Growth (%)`. **C2 owns fuzzy matching** (agreed — we're the only component with a live user, so ambiguity becomes a confirmation prompt rather than a silent guess).

Normalization before comparison: lowercase → strip non-alphanumerics → collapse whitespace. That alone roughly doubles hit rate on real CSVs. Unresolved columns go to the user via `/validate`.

## 7. Validation thresholds

### 7.1 Severity bands (half-open)

```
score >= 75  → SEVERE
score >= 50  → CRITICAL
score >= 25  → WARNING
else         → INFO
```
Exactly 50 is `CRITICAL`.

### 7.2 Minimum periods

| Granularity | C2 hard-blocks | C2 soft-warns | Full trend analysis |
|---|---|---|---|
| Monthly | < 3 | 3–5 | ≥ 6 |
| Quarterly | < 2 | 2–3 | ≥ 4 |
| Annual | < 2 | 2 | ≥ 3 |

**Critical UX consequence:** if **every** submitted metric is below its *trend* floor (not the hard-block floor), C1 issues a **refusal**, not an analysis. A user uploading 5 months for everything gets refused. The soft-warn copy must say this explicitly:

> *"Metrics with fewer than 6 monthly periods get limited trend analysis. If all your metrics are below this, we'll tell you the data is insufficient rather than guess."*

---

# PART IV — C1 REFERENCE (for fixtures and UI)

Facts from C1's live source. Not reimplemented by C2 — needed for fixture design and to answer judges.

## 8.1 Baselines are band-adjusted

Sector YAML defines each metric's distribution (`normal` | `lognormal` | `uniform`) with `mean` / `std` / bounds. Then:

```
calibrated_mean = base_mean + band.mean_adjustment
calibrated_std  = max(base_std + band.std_adjustment, 0.01)
```

`deviation.expected_value` and `expected_std` are **always band-specific**. Never treat them as universal sector medians.

**TECH_SAAS — churn rate (%)**

| Band | Expected mean | Expected std |
|---|---|---|
| `<1M` | 3.5 | 1.4 |
| `1M-10M` | 2.0 | 0.8 |
| `10M-100M` | 1.5 | 0.6 |
| `>100M` | 1.0 | 0.5 |

**TECH_SAAS — CAC ($)**

| Band | Expected mean | Expected std |
|---|---|---|
| `<1M` | 3,000 | 800 |
| `1M-10M` | 4,500 | 1,200 |
| `10M-100M` | 6,500 | 1,800 |
| `>100M` | 9,500 | 2,700 |

> **Consequence for C2:** the band we derive changes every expected value downstream. Getting `revenue_band` wrong shifts the entire analysis. See the open boundary question in §9.

## 8.2 Noise filter — four layers, all must pass

| Layer | Check | Rejection meaning |
|---|---|---|
| L1 Statistical | `\|z\| ≥ 1.5` | Within normal variation |
| L2 Persistence | ≥6 periods: `periods_deviating ≥ 2`; <6 periods: `\|z\| ≥ 2.5` | Transient spike |
| L3 Correlation | No strongly correlated metric moving oppositely (`\|z\| ≥ 1.5` sign conflict) | Contradicted by related metrics |
| L4 Seasonality | If `seasonality.enabled`, must exceed seasonal amplitude | Within expected seasonal swing |

```
base_conf      = min(|z| / 5.0, 0.65)
pers_bonus     = +0.20 if periods_deviating >= 3
                 +0.10 if periods_deviating >= 2
corr_bonus     = +0.15 if a correlated metric also deviates consistently
interp_penalty = -0.30 * interpolated_ratio
noise_confidence = clip(base + pers + corr - interp, 0.30, 0.99)
```

> **Known gap:** metrics failing any layer are not emitted as anomalies, may appear as highlights if favourable, and are otherwise **silently excluded** — invisible in `skipped_metrics` (that's only for unrecognised IDs). C2 currently cannot explain missing metrics to the user. Requested fix in §9.

## 8.3 Severity score

| Component | Max | Formula |
|---|---|---|
| Magnitude | 30 | `min(\|z\|/4.0, 1.0) × 30` |
| Persistence | 20 | `min(periods_deviating/6.0, 1.0) × 20` |
| Trajectory | 20 | `min((\|slope\|/std)/0.5, 1.0) × 20` — **0 without trend support** |
| Importance | 15 | `min(metric_weight, 1.0) × 15` |
| Correlation support | 15 | 15 if ≥1 correlated anomaly confirmed, else 0 |

```
severity_score = clip(raw_total × (0.75 + 0.25 × data_confidence), 0, 100)
```

## 8.4 Health score

```
HIGHER_IS_BETTER: metric_health = percentile
LOWER_IS_BETTER:  metric_health = 100 - percentile
TARGET_BAND:      metric_health = max(0, 100 - |percentile - 50| * 2)

overall_health_score = Σ(metric_health × weight) / Σ(weight)
```
Percentiles via `scipy.stats.norm.cdf`. Null on refusal.

## 8.5 Correlation matrices (drives `correlated_anomalies` and C3 clustering)

Hardcoded per sector in YAML. Threshold `|coefficient| ≥ 0.5`. `correlated_anomalies` lists only metrics that **also** tripped as anomalies.

**TECH_SAAS**

| A | B | Coef |
|---|---|---|
| `monthly_recurring_revenue_growth` | `churn_rate` | −0.65 |
| `monthly_recurring_revenue_growth` | `net_revenue_retention` | +0.78 |
| `churn_rate` | `net_revenue_retention` | **−0.80** |
| `net_revenue_retention` | `lifetime_value` | +0.55 |
| `customer_acquisition_cost` | `burn_rate` | +0.60 |

**RETAIL**

| A | B | Coef |
|---|---|---|
| `gross_margin` | `inventory_turnover` | +0.52 |
| `gross_margin` | `return_rate` | −0.50 (at threshold, included) |
| `inventory_turnover` | `sell_through_rate` | +0.65 |
| `average_order_value` | `revenue_per_sqft` | +0.60 |
| `revenue_per_sqft` | `same_store_sales_growth` | +0.55 |
| `gross_margin` | `same_store_sales_growth` | +0.45 (below threshold — not linked) |
| `average_order_value` | `customer_acquisition_cost` | −0.40 (below threshold — not linked) |

## 8.6 Refusal triggers — complete, checked in order

1. **No metrics submitted** — `metrics` is empty
2. **All metrics have `confidence < 0.35`** — *dead for MVP: C2's lowest assignment is 0.75. Goes live only if OCR returns to scope.*
3. **All metrics below their granularity trend floor** (monthly <6, quarterly <4, annual <3)

No other triggers. `CONTRADICTORY_EVIDENCE` is reserved but never produced.

## 8.7 Metric catalogue & context tags

13 unique metrics; `gross_margin` and `customer_acquisition_cost` span both sectors.

**TECH_SAAS (7)**

| metric_id | context_tags |
|---|---|
| `monthly_recurring_revenue_growth` | growth_decline, topline, saas_velocity |
| `churn_rate` | churn_related, retention_leak, customer_attrition |
| `customer_acquisition_cost` | cac_inflation, acquisition_efficiency, sales_burn |
| `lifetime_value` | ltv_decay, monetization, customer_worth |
| `net_revenue_retention` | nrr_drop, expansion_revenue, account_health |
| `burn_rate` | runway_crisis, burn_spike, capital_efficiency |
| `gross_margin` | margin_compression, cogs_inflation, gross_profit |

**RETAIL (8)**

| metric_id | context_tags |
|---|---|
| `gross_margin` | retail_margin, pricing_pressure, margin_erosion |
| `inventory_turnover` | dead_stock, inventory_velocity, working_capital |
| `average_order_value` | basket_size, pricing_elasticity, aov_drop |
| `revenue_per_sqft` | store_productivity, footfall_efficiency, retail_yield |
| `same_store_sales_growth` | comp_sales, store_growth, retail_velocity |
| `sell_through_rate` | inventory_clearance, sell_through, stock_efficiency |
| `customer_acquisition_cost` | cac_inflation, customer_acquisition, ad_spend_efficiency |
| `return_rate` | product_returns, refund_rate, return_leakage |

**Alias seeds** (extend freely — C2 owns this table):

```yaml
monthly_recurring_revenue_growth: [MRR Growth, MRR Growth %, Monthly Recurring Revenue Growth, MRR]
churn_rate:                       [Churn, Churn %, Customer Churn, Monthly Churn]
customer_acquisition_cost:        [CAC, Acquisition Cost, Cost per Customer]
lifetime_value:                   [LTV, CLV, Customer Lifetime Value]
net_revenue_retention:            [NRR, Net Revenue Retention, Net Dollar Retention, NDR]
burn_rate:                        [Burn, Monthly Burn, Cash Burn]
gross_margin:                     [GM, Gross Margin %, Gross Profit Margin]
same_store_sales_growth:          [Comp Sales, Comparable Store Sales, SSS Growth, Like-for-Like Sales]
sell_through_rate:                [Sell Through, Sell-Through %, STR]
return_rate:                      [Returns, Return %, Product Return Rate, Refund Rate]
inventory_turnover:               [Inventory Turns, Stock Turnover, Turns]
average_order_value:              [AOV, Avg Order Value, Basket Size]
revenue_per_sqft:                 [Revenue per Square Foot, Sales per Sqft, RPSF]
```

---

# PART V — DECISIONS, GAPS, RISKS

## 9. Decision log

### Applied by C2, accepted by C1

| # | Change | Reason |
|---|---|---|
| 1 | `overall_health_score` → `Optional[float] = None` | Declared null-on-refusal but typed `float` — would ValidationError on the refusal demo |
| 2 | `= None` defaults on all bare `Optional[X]` | Pydantic v2 treats bare `Optional` as required-but-nullable |
| 3 | `reporting_period` → `ReportingPeriod`, not `dict` | Was the only untyped field |
| 4 | Distributional fraction/percent check | Range checks cannot catch scale errors |
| 5 | Alias resolver strips non-alphanumerics | Exact-match misses most real CSV headers |
| 6 | `asyncio.to_thread()` | `get_event_loop()` deprecated inside a coroutine |
| 7 | Half-open severity bands | Stated ranges shared endpoints |

### Resolved by C1

| Item | Resolution |
|---|---|
| Period-rule conflict | All-metrics check runs first; mixed history → partial analysis, no refusal |
| Granularity-aware minimums | 6 monthly / 4 quarterly / 3 annual |
| "Sector median" wording | Changed to "expected baseline for a company of this profile" |
| RETAIL metric count | Expanded 4 → 8 |
| `$schema` vs `schema_version` | Aliased field, `populate_by_name=True` |
| `confidence` effect | `severity × (0.75 + 0.25 × confidence)` |
| `correlated_anomalies` | Hardcoded YAML correlation matrix, threshold ≥ 0.5 — not computed |
| `context_tags` | Fixed vocabulary, listed in §8.7 |
| `target_basis` source | Use `deviation.expected_value` (band-adjusted) directly |

### Open — do not block on these, but chase

| # | Item | Owner | Impact on C2 |
|---|---|---|---|
| **O1** | **Silently excluded metrics have no explanation.** Request `metadata.filtered_metrics: [{metric_id, rejected_at, reason}]` — the noise filter already computes it | C1 | High. Without it a user submits 8 metrics, sees 5, and we can't say why. With it we get a strong UI beat: *"we looked at burn rate and concluded it was noise."* |
| **O2** | **`revenue_band` boundary convention.** Is `annual_revenue = 10_000_000` in `1M-10M` or `10M-100M`? | C1 | High. C2 derives the band; the band shifts every baseline. |
| **O3** | **`direction: "as_expected"` semantics.** `HealthyHighlight` has no deviation block, so this can only appear on an `Anomaly` — but an anomaly deviated by definition | C1 | Medium. UI switches on this field. |
| **O4** | `RefusalDetail` field list unverified | C1 | Medium. Blocks the refusal view. |
| **O5** | Percentile uses `norm.cdf` even for `lognormal` metrics (CAC, burn, LTV) — skews `overall_health_score`, our headline number | C1 | Low-medium |
| **O6** | `model_dump()` default is `by_alias=False` → emits `schema_version`, not `$schema`. Standardise on `by_alias=True` at boundaries, or don't validate on the schema field at all for MVP | All | Low |
| **O7** | C3 sign-off on `EnrichedReport` (§5.4) | C3 | High for Phase 5 |
| **O8** | Repo access for C1's `ml_engine` package | C1 | High. Handout prose has repeatedly been stale; repo is canonical. |
| **O9** | `target_value` for metrics absent from the report entirely (e.g. `onboarding_completion_rate`) has no baseline anywhere | C3 | Low for C2 |

## 10. Risks

| Risk | Mitigation |
|---|---|
| **Both dependencies land late** — C2 is last in the chain | Mocks on day 1, switchable by config. Never blocked. |
| `analyze_company()` blocks the event loop | CPU-bound with no I/O (confirmed) → `asyncio.to_thread()` |
| **Frontend overruns** — it always does | API first. Demo from a minimal UI if needed. Judges forgive plain styling, not a broken demo. |
| C3 changes shape unilaterally | Contract v1 §6 is a spec. Mocks match it. If he deviates, adapt in an adapter layer — not throughout |
| Unit-scale bug produces a visibly wrong number on stage | §6.1 check. One hour. Non-negotiable. |
| Demo video underestimated | It takes half a day, not an hour. Budget it in Phase 5. |

## 11. Anti-goals

- **Never invent a number** that wasn't computed or submitted
- **Never modify** an upstream component's values
- **Never raise to the user** from C1/C3 — return a valid object or let C2 catch it
- **No second LLM call** anywhere in C2
- **No hardcoded metric IDs, sectors, or thresholds** in engine code — everything from config
- Don't re-implement C1's statistics in C2

---

# PART VI — BUILD PLAN

## 12. Ordering principle

**Vertical slice first, then enrich.** The whole pipeline runs end-to-end on mocks by Phase 1, so every later phase *replaces a fake part with a real one* rather than adding a missing part. Nothing is ever half-built.

**Frontend (Phase 3) comes before real integration (Phase 4) deliberately.** If C1 and C3 slip to Saturday, we still have a complete, clickable, demoable product on mocks. Reversing them means a slip leaves us with nothing to show.

## 13. Phases

| Phase | Goal | Est. | Depends on |
|---|---|---|---|
| **0** | Foundation & contracts | 2–3h | Nothing |
| **1** | Vertical slice on mocks | 3–4h | P0 |
| **2** | Real input layer | 1 day | P1 |
| **3** | Frontend | 1 day | P1 (**not** P2) |
| **4** | Real integration | 1 day | C1, C3 delivery |
| **5** | Hardening & demo | half day | P4 |

### Phase 0 — Foundation & contracts

Repo scaffold, dependencies, `models.py` (§5, all fixes applied), `metric_config.yaml` (§8.7), `MockMLEngine` + `MockCaseMatcher` returning schema-valid fixtures, `/health`, test scaffold.

**Exit:** tests pass · mocks construct a valid `AnomalyReport` and `EnrichedReport` · `/health` returns 200 · a fixture round-trips through `model_dump()` and back.

### Phase 1 — Vertical slice on mocks

`POST /analyze` accepting well-formed `CompanyInput` JSON → orchestrator → mock C1 → mock C3 → assembled `ApiResponse`. Degradation logic on every stage. No parsing, no UI.

**Exit:** curl a JSON payload, get a full response including narrative · kill any one mock and still get a partial response, never a 500 · refusal fixture returns `status: "refused"` with no narrative.

### Phase 2 — Real input layer

CSV + manual form → `CompanyInput`. Alias resolution with normalization (§6.2), unit validation including the distributional check (§6.1), period normalization, granularity handling, minimum-period enforcement (§7.2), `POST /validate` for the mapping-confirmation flow.

**Exit:** upload a deliberately messy CSV — bad headers, fraction-encoded percentages, a short series, an unknown column — and get either a correct `CompanyInput` or a specific, actionable error for each problem.

### Phase 3 — Frontend

Upload → mapping confirmation → results (health score, severity-coloured anomaly cards, prescriptions, matched cases, narrative, highlights) → refusal view → degraded banner. Still on mocks.

**Exit:** full click-through demo with zero dependency on C1 or C3 · all four render states verified (normal / refusal / degraded / skipped-metrics warning).

### Phase 4 — Real integration

Swap mock C1 → real `ml_engine`, mock C3 → real `enrich_report`. Threadpool wrapping, timeouts, latency measurement, sync-vs-async decision confirmed against real numbers.

**Exit:** real end-to-end run within the latency budget · adapter layer absorbs any C3 schema drift · mocks still switchable via config.

### Phase 5 — Hardening & demo

Three fixture scenarios (healthy / critical / refusal), error-path sweep, `POST /feedback`, README, demo script, **demo video (half a day)**.

**Exit:** demo runs clean three consecutive times from a cold start.

## 14. API surface

```
POST /analyze          run the pipeline
GET  /metrics/{sector} canonical metric list — feeds the frontend dropdown
POST /validate         dry-run the parser, return MappingProposals for confirmation
POST /feedback         record the user's verdict (file-backed for MVP)
GET  /health           liveness + component import check
```

`/validate` is worth building even though nobody asked — it enables the mapping-confirmation UI and makes a good demo beat: *watch it read the spreadsheet and ask me to confirm.*

## 15. Degradation matrix

Every stage degrades, never dies. A demo showing partial results survives; a 500 doesn't.

| Failure | Behaviour |
|---|---|
| Parse fails | `blocking_errors` returned, pipeline never starts |
| C1 raises | Parse result + clear error. Not a 500 |
| C1 returns refusal | `status: "refused"`. Render refusal directly. **No C3 call, no LLM.** |
| C3 finds no cases | `matched_cases: []`, narrative still attempted |
| C3 LLM fails | `narrative: null`, `degraded: true`, everything else rendered + banner |
| C3 raises entirely | Render the `AnomalyReport` alone. Anomalies without prescriptions still demo well |

### UI render states

| Case | UI |
|---|---|
| Normal | Health score, anomaly cards, prescriptions, cases, narrative, highlights |
| Refusal | **Health score as "N/A"** — never "50/100". Reason + what data would resolve it |
| Degraded | Everything available + "narrative unavailable" banner |
| Skipped metrics | Warning listing unrecognised IDs from `metadata.skipped_metrics` |

## 16. Scope — locked

**In:** manual form + CSV · `TECH_SAAS` + `RETAIL` · alias-table matching with normalization · in-memory storage · `/feedback` to file · one LLM call (C3's) · refusal path · degraded rendering · four UI render states.

**Out:** PDF/OCR · Excel · `MFG` · auth · rate limiting · database persistence · multi-company comparison · historical trend across submissions.

**Deferred but designed** (present as roadmap, never as built): Living Knowledge Base feedback loop, entity masking, dynamic user profiling, unstructured news ingestion.

> Keep deck claims consistent with this list. A judge comparing the deck to the demo is the most likely way we lose points.

## 17. Tech stack & structure

Python 3.11+ · FastAPI · Pydantic v2 · pandas (CSV) · pytest · Next.js + TypeScript · Vercel + Railway.

```
api/
├── models/
│   ├── shared.py          # CompanyInput, AnomalyReport, EnrichedReport (§5)
│   └── internal.py        # ParseResult, ApiResponse, MappingProposal (§5.5)
├── config/
│   ├── metric_config.yaml # metrics, units, ranges, aliases (§8.7)
│   └── settings.py        # USE_MOCKS, timeouts, thresholds
├── parsing/
│   ├── ingest.py          # CSV + form → raw frame
│   ├── resolver.py        # alias + normalization (§6.2)
│   ├── validation.py      # units, distributional check, periods (§6.1, §7.2)
│   └── builder.py         # → CompanyInput
├── orchestration/
│   ├── pipeline.py        # the spine
│   ├── adapters.py        # absorbs C1/C3 schema drift
│   └── degradation.py     # §15
├── mocks/
│   ├── mock_ml.py
│   └── mock_c3.py
├── routes/
└── tests/
    └── fixtures/          # healthy, critical, refusal, degraded
```

## 18. Fixture design — derived from §8.3

The severity formula constrains what a fixture can produce. Design demo data accordingly.

- **Correlation support (15 pts) requires a *second* correlated metric to also trip.** A single-metric submission can never earn it.
- **Trajectory (20 pts) is zero without trend support** — i.e. below 6 monthly periods.

A lone metric with 4 periods maxes out near **52** — barely `CRITICAL`. **To demo a `SEVERE` anomaly you need at least two correlated metrics, both with ≥6 monthly periods.**

Strongest pair available: `churn_rate` ↔ `net_revenue_retention` at **−0.80**. Second: `monthly_recurring_revenue_growth` ↔ `net_revenue_retention` at +0.78.

**Also:** L3 will suppress an anomaly if a correlated metric moves the opposite way — don't build a fixture where that happens accidentally.

**Four required fixtures:**

| Fixture | Design |
|---|---|
| `healthy` | All metrics near baseline. Exercises `non_anomalous_highlights` and a high health score |
| `critical` | `churn_rate` + `net_revenue_retention` both tripping, ≥6 monthly periods each. Produces `SEVERE` + a real cluster for C3 |
| `refusal` | All metrics at 4 monthly periods. Triggers refusal reason 3 |
| `degraded` | Valid `critical` input, C3 mock configured to fail the LLM call |

## 19. Immediate next actions

1. **Chase O8 (repo access)** — handout prose has been stale repeatedly; the repo is canonical
2. **Send O1, O2, O3, O4 to C1** as one short message — none blocks us, all affect the UI
3. **Start Phase 0** — it depends on nothing and nothing depends on waiting

---

*Changes to any contract go in Pipeline Contract v1 first, are announced in the group, and only then appear in code.*