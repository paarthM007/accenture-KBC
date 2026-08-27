# C2 Integration Reference

Generated from the code in this repository as it exists today (verified against
source, not against the phase plans or `pipeline-Contract-V1.md`). Where the
code disagrees with the contract, the disagreement is documented here and
flagged in **[§7 — Deviations](#7-deviations)**. Read §7 first.

All file paths are repo-relative from the project root (the directory containing
this `docs/` folder).

---

## 3.1 What C2 is

C2 is the API, parsing, and orchestration layer of a three-component pipeline
that turns a company's submitted business metrics into an anomaly report, a
set of prescriptions, and an executive narrative — or a refusal when the
evidence is insufficient. It is the only component with a live user: it
ingests CSV/JSON input, normalizes and validates it into a shared schema,
calls two in-process components (C1 for detection, C3 for prescription/
narrative) as plain Python function calls wrapped in a thread pool, and
assembles the final response — degrading gracefully at every stage rather
than returning an HTTP 500.

```
User (form / CSV upload)
        │
        ▼
┌──────────────────────────────────────────────┐
│ C2 — parse → validate → CompanyInput          │  api/parsing/*
└──────────────────────────────────────────────┘
        │  CompanyInput (Pydantic model instance)
        ▼
┌──────────────────────────────────────────────┐
│ C1 — analyze_company(CompanyInput)            │  in-process call, threadpool-wrapped
│      → AnomalyReport                          │  api/orchestration/pipeline.py
└──────────────────────────────────────────────┘
        │
        ├── report.refusal is not None ──────────────┐
        │   (C3 is NEVER called)                      │
        ▼ refusal is None                             │
┌──────────────────────────────────────────────┐      │
│ C3 — enrich_report(AnomalyReport)             │      │
│      → EnrichedReport                         │      │
└──────────────────────────────────────────────┘      │
        │  EnrichedReport                              │
        ▼                                              ▼
┌────────────────────────────────────────────────────────────┐
│ C2 — ApiResponse assembly                                   │
│   status="complete" (incl. degraded)   status="refused"     │
└────────────────────────────────────────────────────────────┘
```

The refusal short-circuit is implemented in `api/orchestration/pipeline.py`,
function `run_pipeline`, immediately after the C1 call returns
(`if report.refusal is not None:`). It returns before `get_c3()` is ever
called.

---

## 3.2 Repository map

### Root

| Path | Purpose |
|---|---|
| `requirements.txt` | Backend Python dependencies |
| `pytest.ini` | Points pytest at `api/tests` |
| `.env.example` | Backend environment variable template |
| `.gitignore` | `.venv/`, `__pycache__/`, `.env`, `feedback.jsonl`, `tasks/`, frontend build artifacts, OS/editor cruft |
| `README.md` | Setup/run/test commands, known limitations |
| `CLAUDE.md` | Terse context for future coding sessions in this repo |
| `pipeline-Contract-V1.md` | Cross-team contract — see §7 for where the code deviates |
| `C2-MasterPlan.md` | This component's build plan and design rationale |
| `tasks/` | Per-phase task breakdowns and the brief that generated this document — **gitignored, not part of the pushed repo.** Internal working documents; not visible to anyone working from a clone. |
| `scripts/dump_scenario_responses.py` | Dumps a full `ApiResponse` JSON per demo scenario (feeds the frontend's scenario switcher); see §3.8 |

### `api/` — backend

| Path | Purpose |
|---|---|
| `api/main.py` | FastAPI app, CORS, the three global exception handlers |
| `api/config/settings.py` | `Settings` (pydantic-settings) — see §3.7 |
| `api/config/loader.py` | Loads/caches `metric_config.yaml`; exposes `metrics()`, `thresholds()`, `revenue_bands()` |
| `api/config/metric_config.yaml` | Per-metric parsing config, thresholds, revenue bands — see §3.7 |
| `api/models/shared.py` | `CompanyInput`, `AnomalyReport`, `EnrichedReport` and every nested model — the cross-team contract as implemented |
| `api/models/internal.py` | C2-only models: `ParseWarning(Code)`, `MappingProposal`, `RawCell`/`RawTable`, `FormMetadata`, `ValidateResponse`, `ErrorCode`, `Timings`, `ApiResponse` |
| `api/orchestration/pipeline.py` | `run_pipeline()` — the spine; see §3.4/§3.5 |
| `api/orchestration/resolver.py` | `get_c1()`/`get_c3()` — lazy real-vs-mock import switch |
| `api/orchestration/adapters.py` | `adapt_c3_output()`, `C3ContractViolation` |
| `api/orchestration/degradation.py` | `wrap_bare_report()` — the shared bare-`EnrichedReport` fallback |
| `api/mocks/mock_ml.py` | `MockMLEngine` — stands in for `ml_engine.analyze_company` |
| `api/mocks/mock_c3.py` | `MockC3` — stands in for C3's `enrich_report` |
| `api/parsing/ingest.py` | `ingest_csv()`, `ingest_form()` — file → `RawTable` |
| `api/parsing/resolver.py` | `normalize()`, `resolve()` — alias/name → canonical `metric_id` |
| `api/parsing/primitives.py` | `parse_number()`, `parse_period()`, gap/trim/interpolate functions |
| `api/parsing/validation.py` | `validate_and_build_metric()`, `check_refusal_likely()` |
| `api/parsing/builder.py` | `build_company_input()` — ties resolver + validation into one `ParseResult` |
| `api/routes/health.py` | `GET /health` |
| `api/routes/analyze.py` | `POST /analyze`, `POST /analyze/upload` |
| `api/routes/validate.py` | `POST /validate` |
| `api/tests/fixtures/builders.py` | `FIXTURE_BUILDERS` — the four demo scenarios as Python functions |
| `api/tests/fixtures/dump_fixtures.py` | Dumps `CompanyInput`/`AnomalyReport` JSON per scenario; see §3.8 |
| `api/tests/fixtures/csv/*.csv` | 15-file messy-CSV corpus; see §3.8 |
| `api/tests/fixtures/json/*.json` | Output of `dump_fixtures.py` (checked in) |
| `api/tests/test_*.py` | 15 test files, 199 tests total (see §3.9 for exact per-file counts is unnecessary — `pytest --collect-only -q` gives the live number) |

### `web/` — frontend

| Path | Purpose |
|---|---|
| `web/package.json` | Next.js 16 / React 19 / Tailwind v4; `npm run types` regenerates `src/types/api.ts` from the live backend's OpenAPI schema |
| `web/next.config.ts` | Default, no overrides |
| `web/tsconfig.json` | `@/*` → `src/*` path alias |
| `web/.env.example` / `web/.env.local` | `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_SHOW_SCENARIO_SWITCHER` |
| `web/src/app/layout.tsx` | Root layout, Google Fonts (Inter, Inter Tight) |
| `web/src/app/page.tsx` | The whole app's state machine: `form → mapping → results` |
| `web/src/app/globals.css` | Design tokens as CSS custom properties, tabular-nums utility, focus-ring rule, reduced-motion rule |
| `web/src/lib/api.ts` | `health()`, `analyzeJson()`, `validate()`, `analyzeUpload()` — the only file that talks to the backend |
| `web/src/lib/metricDisplay.ts` | `titleCaseMetricId()` — fallback for metric IDs absent from config |
| `web/src/lib/revenueBand.ts` | `previewRevenueBand()` — client-side-only cosmetic preview, duplicates the backend's band logic |
| `web/src/lib/scenarios.ts` | `SCENARIOS`, `SCENARIO_LABELS` — loads the four static JSON snapshots |
| `web/src/lib/scenario-fixtures/*.json` | Output of `scripts/dump_scenario_responses.py` (checked in) |
| `web/src/types/api.ts` | Generated by `openapi-typescript`; **do not hand-edit** |
| `web/src/components/HealthScore.tsx` | Renders `overall_health_score`; `null` → "N/A" |
| `web/src/components/Narrative.tsx` | Renders the four `Narrative` fields distinctly |
| `web/src/components/AnomalyCard.tsx` | One anomaly: signature bar, observed/expected/delta, sparkline, tags, correlation links |
| `web/src/components/SeverityConfidenceBar.tsx` | The severity/confidence signature element |
| `web/src/components/Sparkline.tsx` | Hand-rolled SVG line from `trend.values_over_time` |
| `web/src/components/PrescriptionCard.tsx` | One `Prescription`; `current_value: null` → "not currently tracked" |
| `web/src/components/MatchedCases.tsx` | Collapsible list of `MatchedCase` |
| `web/src/components/Highlights.tsx` | `non_anomalous_highlights`, title-cases unknown `metric_id`s |
| `web/src/components/SkippedMetricsNotice.tsx` | Renders `metadata.skipped_metrics` |
| `web/src/components/ParseWarningsNotice.tsx` | Renders `ApiResponse.warnings` on the results screen |
| `web/src/components/DegradedBanner.tsx` | Shown when `metadata.degraded` |
| `web/src/components/RefusalView.tsx` | The refusal screen |
| `web/src/components/ResultsView.tsx` | Composes all of the above for `status: complete/refused` |
| `web/src/components/MappingConfirmation.tsx` | Renders `ValidateResponse` — proposals, warnings, inferred block, ready-gated Analyse button |
| `web/src/components/InputForm.tsx` | Company metadata + file input |
| `web/src/components/ScenarioSwitcher.tsx` | Dev-only state override, gated by `NEXT_PUBLIC_SHOW_SCENARIO_SWITCHER` |

---

## 3.3 API surface

### `GET /health`

No request body.

**Response 200** (`api/routes/health.py`, plain `dict`, not a Pydantic model):

```json
{
  "status": "ok",
  "version": "0.1.0",
  "components": {
    "c1": { "mode": "mock", "importable": false },
    "c3": { "mode": "mock", "importable": false }
  },
  "config": { "metrics_loaded": 13, "sectors": ["RETAIL", "TECH_SAAS"] }
}
```

`mode` reflects `settings.USE_MOCK_C1`/`USE_MOCK_C3`. `importable` is a live
`importlib.import_module()` attempt against `settings.C1_MODULE_NAME` /
`settings.C3_MODULE_NAME`, wrapped in try/except — never raises.

```bash
curl http://localhost:8000/health
```

### `POST /analyze`

- **Request:** `application/json`, body = a `CompanyInput` JSON object (see §3.6). All fields required except `raw_text_context`, `founded_year`, `annual_revenue`.
- **Response 200:** `ApiResponse` (see §3.6 for full shape).
- **Response 422:** `RequestValidationError` caught by `api/main.py`'s handler → `ApiResponse` with `status: "failed"`, `error: "VALIDATION_ERROR"`, one `ParseWarning` (`code: "SCHEMA_VALIDATION_ERROR"`) per Pydantic error.
- **Response 500:** only on a genuinely unhandled exception (`api/main.py`'s catch-all) or an escaped `C3ContractViolation` — `ApiResponse` with `error: "INTERNAL_ERROR"` or `"C3_CONTRACT_VIOLATION"` respectively. Not expected in normal operation.

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d @api/tests/fixtures/json/critical_company_input.json
```

### `POST /analyze/upload`

- **Request:** `multipart/form-data`.
  | Field | Required | Type |
  |---|---|---|
  | `file` | yes | CSV file |
  | `metadata` | yes | JSON string, see `FormMetadata` in §3.6 |
  | `mapping_overrides` | no | JSON string, `{source_label: metric_id}` |
- **Response 200:** `ApiResponse`. Parse warnings from ingestion/resolution/validation are merged into `ApiResponse.warnings` ahead of anything C1/C3 add (`api/routes/analyze.py`, `response.model_copy(update={"warnings": result.warnings + response.warnings})`).
- **Response 200 with `status: "failed"`:** invalid `metadata` JSON, invalid `mapping_overrides` JSON, or an `IngestError` (bad file type, oversized, unreadable, ambiguous shape) — all caught in the route and turned into `_failed_before_pipeline()`, never propagate to a 500.
- **Response 422:** malformed multipart request itself (e.g. missing `file`) — same `RequestValidationError` handler as above.

```bash
curl -X POST http://localhost:8000/analyze/upload \
  -F "file=@api/tests/fixtures/csv/clean_wide.csv;type=text/csv" \
  -F 'metadata={"company_name":"Acme Co","sector_id":"TECH_SAAS","employee_count":40,"region":"US","annual_revenue":4000000}'
```

### `POST /validate`

- **Request:** `multipart/form-data`, fields `file` (required) and `metadata` (required) — no `mapping_overrides`.
- **Response 200:** `ValidateResponse` (see §3.6) — **never** `ApiResponse`. Never calls C1 or C3.
- **Response 422:** malformed multipart request — `api/main.py`'s handler special-cases `request.url.path == "/validate"` to return a `ValidateResponse`-shaped body (`blocking_errors` populated, `ready: false`), not an `ApiResponse`.

```bash
curl -X POST http://localhost:8000/validate \
  -F "file=@api/tests/fixtures/csv/fraction_percentages.csv;type=text/csv" \
  -F 'metadata={"company_name":"Acme Co","sector_id":"TECH_SAAS","employee_count":40,"region":"US","annual_revenue":4000000}'
```

### `POST /feedback` — **not implemented**

Referenced in `pipeline-Contract-V1.md` §7 and the master plan's locked API
surface, and named explicitly in the brief this document was generated from.
**No route, handler, or model for it exists anywhere in `api/`.** `grep -rn
"feedback" api/ --include=*.py` matches only a settings field
(`FEEDBACK_LOG_PATH` in `api/config/settings.py`) and one docstring comment in
`api/parsing/builder.py`; neither is read or written by any code. This is
Phase 5 (Hardening & Demo) work per the phase plans and has not started. If
C1 or C3 are building against its existence, they are building against a
document, not this code — see §7.

### Everything else that exists

No other routes are registered on the FastAPI app (`api/main.py`'s
`app.include_router()` calls are exactly `health.router`, `analyze.router`,
`validate.router`).

---

## 3.4 How C2 calls C1

**Call site:** `api/orchestration/pipeline.py`, function `run_pipeline`, lines 49–53:

```python
c1_callable = get_c1()
report = await asyncio.wait_for(
    asyncio.to_thread(c1_callable, company_input), timeout=settings.C1_TIMEOUT_S
)
```

`get_c1()` lives in `api/orchestration/resolver.py`. If `settings.USE_MOCK_C1`
is true (default), it returns a bound `MockMLEngine(...).analyze_company`.
Otherwise it lazily `importlib.import_module(settings.C1_MODULE_NAME)`
(default `"ml_engine"`) and `getattr(module, settings.C1_ENTRYPOINT_NAME)`
(default `"analyze_company"`) inside a try/except — on `ImportError` or
`AttributeError` it logs a warning and falls back to the mock. **The real
module is never imported at module load time anywhere in this codebase.**

**Payload:** a `CompanyInput` **Pydantic model instance**, not a dict and not
JSON. `analyze_company` (real or mock) is called as `c1_callable(company_input)`
— a plain in-process Python function call. If C1's real `analyze_company`
expects a dict or a different model class, that is unconfirmed — see §7.

**Wrapping:** `asyncio.to_thread()` (moves the blocking call off the event
loop) inside `asyncio.wait_for(timeout=settings.C1_TIMEOUT_S)` (env var
`C1_TIMEOUT_S`, default `10` seconds, type `float`).

**Outcomes**, exactly as branched in `run_pipeline`:

| Outcome | C2 behaviour |
|---|---|
| Valid `AnomalyReport`, `refusal is None` | Proceeds to call C3 |
| Valid `AnomalyReport`, `refusal is not None` | Short-circuits: `wrap_bare_report(report, degraded=False, reason=None)`, `status: "refused"`. **C3 is never called.** |
| Raises any `Exception` | `status: "failed"`, `error: "C1_FAILED"`, `result: null` |
| Exceeds `C1_TIMEOUT_S` (`TimeoutError`) | `status: "failed"`, `error: "C1_TIMEOUT"`, `result: null`. The worker thread is **not** killed — see the "threading gotcha" note in `pipeline.py`'s module docstring and the root README's Known Limitations. |

### Guarantee list — what C2 will never send C1

| Guarantee | Enforced by | Holds? |
|---|---|---|
| No unknown `metric_id`s | `api/parsing/resolver.py::resolve()` — an unresolved/ambiguous/sector-mismatched column gets `resolved_metric_id=None` and is never added to `resolved_cells` in `api/parsing/builder.py::build_company_input()` | ✅ |
| No metric below its hard-block floor | `api/parsing/validation.py::validate_and_build_metric()`, step 9: returns `(None, warnings)` when `n < band["hard_block"]` | ✅ |
| No disaggregated quarterly (or annual) data | No code path anywhere splits one observation into several. This is an absence, not an active check — grep confirms no such transformation exists in `api/parsing/` | ✅ |
| No non-contiguous series | `api/parsing/primitives.py::apply_gap_policy()` — every metric that reaches `CompanyInput.metrics` has had gaps ≤3 periods linearly interpolated and gaps ≥4 periods trimmed to the most recent contiguous block, before being counted or returned | ✅ |
| No unvalidated units | `validate_and_build_metric()` — range check (step 6, against `metric_config.yaml`'s `valid_min`/`valid_max`) nulls out-of-range points; distributional check (step 5, `UNIT_SCALE_SUSPECT`) excludes the whole metric if it looks fraction-encoded | ✅ |
| **No empty metric lists** | **Not guaranteed.** See below. | ❌ |

**On the empty-metrics case:** if every submitted metric is excluded during
validation (e.g. every column is `UNIT_SCALE_SUSPECT`, or every series is
`SHORT_SERIES`), `build_company_input()` still constructs and returns a
`CompanyInput` with `metrics: []`. `api/routes/analyze.py`'s
`/analyze/upload` handler only checks `result.blocking_errors` (always `[]`
in the current code — nothing in `builder.py` ever populates it) before
calling `run_pipeline()`; it does not check for an empty `metrics` list. The
empty `CompanyInput` is sent to C1 as-is, relying entirely on C1's own
`NO_METRICS_SUBMITTED` refusal trigger. This is deliberate current behaviour,
not a bug, but it is a known rough edge: the resulting refusal reason is
misleading, since the user did submit metrics — C2 silently discarded all of
them and gave no indication in the refusal itself of why. Scheduled for
Phase 5 hardening: C2 should instead return its own blocking error naming the
specific exclusion reasons (fraction-encoded, short series, etc.) rather than
letting C1 answer with a generic "no metrics submitted." See also §7.

---

## 3.5 How C2 calls C3

**Call site:** `api/orchestration/pipeline.py`, function `run_pipeline`, lines 93–98:

```python
c3_callable = get_c3()
raw = await asyncio.wait_for(
    asyncio.to_thread(c3_callable, report), timeout=settings.C3_TIMEOUT_S
)
enriched = adapt_c3_output(raw, original=report)
```

`get_c3()` (`api/orchestration/resolver.py`) mirrors `get_c1()` exactly:
mock by default (`MockC3(...).enrich_report`), else lazy
`importlib.import_module(settings.C3_MODULE_NAME)` (default `"c3_engine"` —
**unconfirmed, placeholder**, see §7) + `getattr(..., settings.C3_ENTRYPOINT_NAME)`
(default `"enrich_report"`, also unconfirmed), falling back to the mock on
`ImportError`/`AttributeError`.

**Payload:** the `AnomalyReport` **Pydantic model instance** C1 returned,
passed directly as `c3_callable(report)` — again a plain in-process call, not
serialized.

**Wrapping:** same pattern as C1 — `asyncio.to_thread()` inside
`asyncio.wait_for(timeout=settings.C3_TIMEOUT_S)` (env `C3_TIMEOUT_S`,
default `30` seconds).

### What the adapter validates (`api/orchestration/adapters.py::adapt_c3_output`)

1. **Type check.** If `raw` is already an `EnrichedReport` instance, pass
   through. If it's a `dict`, attempt `EnrichedReport.model_validate(raw)`.
   Anything else (or a dict that fails validation) raises
   `C3ContractViolation`.
2. **Verbatim check.** `if enriched.anomaly_report != original:` — if C3
   modified, stripped, or renamed fields on the nested report, this fires.
   **This does not raise.** It logs `logger.error(...)` and silently
   substitutes `original` back in via `enriched.model_copy(update=
   {"anomaly_report": original})`. The rest of C3's output (prescriptions,
   narrative, etc.) is kept as-is.

### Drift cases

| C3 output | Adapter behaviour | Result |
|---|---|---|
| Valid `EnrichedReport`, `anomaly_report` unchanged | Pass through | Normal `status: "complete"` |
| Valid `EnrichedReport`, `anomaly_report` modified/renamed fields | Logged error, `anomaly_report` silently replaced with the original | `status: "complete"`, **not** marked degraded — the substitution is visible only in logs |
| Dict that fails `EnrichedReport.model_validate()` | Raises `C3ContractViolation` | Caught in `run_pipeline`'s except clause → `wrap_bare_report(report, degraded=True, reason="c3_contract_violation")` |
| Any other type (e.g. `None`, a string) | Raises `C3ContractViolation` | Same as above |
| Raises any other `Exception` | Not the adapter's concern — caught directly in `run_pipeline` | `wrap_bare_report(report, degraded=True, reason="c3_failed")` |
| Exceeds `C3_TIMEOUT_S` | `asyncio.TimeoutError` | `wrap_bare_report(report, degraded=True, reason="c3_timeout")`. Worker thread not killed (same caveat as C1). |

### C3 is not called on refusal

Enforced in two places:

1. **Primary:** `run_pipeline`'s refusal short-circuit (§3.4) returns before
   `get_c3()` is ever called — lines 78–89 of `pipeline.py`.
2. **Defensive guard:** `MockC3.enrich_report()` itself
   (`api/mocks/mock_c3.py`, lines 62–77) checks `if report.refusal is not
   None:` as its first real branch (after the `raise_on_call` check) and
   returns a bare `EnrichedReport` with no simulated LLM sleep, mirroring
   Contract §6.3's mandated defensive guard. If C3's *real* module doesn't
   implement this same guard, primary enforcement in C2 still holds — this
   is documented as belt-and-suspenders, not the only line of defence.

### How `metadata.degraded` / `degraded_reason` are surfaced

Both fields live on `EnrichmentMetadata` (`api/models/shared.py`). C2 does
**not** distinguish, when rendering, whether `degraded` was set by C2 itself
or by C3:

- **C2-set** (`api/orchestration/degradation.py::wrap_bare_report`, and the
  three call sites in `pipeline.py`): `degraded=True` with
  `degraded_reason` always one of the literal strings `"c3_timeout"`,
  `"c3_failed"`, or `"c3_contract_violation"`.
- **C3-set** (conventional, per `EnrichmentMetadata`'s docstring, not
  enforced): `degraded=True` with `degraded_reason` expected to be
  `"llm_failed"` / `"llm_timeout"` / `"case_match_failed"`. **`MockC3` does
  not follow this convention** — its `fail_llm=True` path
  (`api/mocks/mock_c3.py`, lines 105–109) sets `degraded=True` but leaves
  `degraded_reason` at its default of `None`. The frontend's
  `DegradedBanner` only shows a "Details" disclosure when `degradedReason`
  is truthy, so in the current mock, the degraded banner for a simulated LLM
  failure shows with no details link — this is a fidelity gap in the mock,
  not a contract violation (`degraded_reason` is documented as optional).

`degraded_reason` itself is a C2-proposed, unsigned addition to the contract
— see §7.

---

## 3.6 Data contracts as implemented

Canonical source: `api/models/shared.py` (cross-team models) and
`api/models/internal.py` (C2-only models). The examples below were produced
by running:

```bash
./.venv/Scripts/python -m api.tests.fixtures.dump_fixtures
PYTHONPATH=. ./.venv/Scripts/python scripts/dump_scenario_responses.py
```

### `CompanyInput` — the `critical` fixture (`api/tests/fixtures/json/critical_company_input.json`)

```json
{
  "company_id": "company_critical_001",
  "sector_id": "TECH_SAAS",
  "company_metadata": {
    "name": "Churn Co",
    "founded_year": 2020,
    "employee_count": 52,
    "annual_revenue": 3200000.0,
    "revenue_band": "1M-10M",
    "region": "US"
  },
  "reporting_period": { "type": "monthly", "start": "2024-01-01", "end": "2024-08-31" },
  "metrics": [
    {
      "metric_id": "churn_rate",
      "granularity": "monthly",
      "values": [
        { "period": "2024-01", "value": 2.1, "interpolated": false },
        { "period": "2024-02", "value": 2.5, "interpolated": false },
        { "period": "2024-03", "value": 3.0, "interpolated": false },
        { "period": "2024-04", "value": 3.4, "interpolated": false },
        { "period": "2024-05", "value": 3.9, "interpolated": false },
        { "period": "2024-06", "value": 4.3, "interpolated": false },
        { "period": "2024-07", "value": 4.8, "interpolated": false },
        { "period": "2024-08", "value": 5.2, "interpolated": false }
      ],
      "confidence": 1.0
    }
  ],
  "raw_text_context": null
}
```
*(`net_revenue_retention` and `gross_margin` entries omitted here for length — full file has all three; see the actual JSON file for the complete list.)*

### `AnomalyReport` — the `critical` fixture, first anomaly only shown

Full file: `api/tests/fixtures/json/critical_anomaly_report.json`. Shape (both anomalies, highlight, metadata all present in the real file):

```json
{
  "$schema": "anomaly_report_v1",
  "company_id": "company_critical_001",
  "sector_id": "TECH_SAAS",
  "overall_health_score": 38.0,
  "anomalies": [
    {
      "anomaly_id": "anom_critical_churn_rate",
      "metric_id": "churn_rate",
      "severity_score": 82.0,
      "severity_label": "SEVERE",
      "deviation": {
        "observed_current": 5.2, "expected_value": 2.0, "expected_std": 0.8,
        "z_score": 4.0, "percentile": 99.9, "direction": "above_expected"
      },
      "trend": { "direction": "deteriorating", "slope": 0.443, "periods_deviating": 6, "values_over_time": [ "...8 points, see file..." ] },
      "correlated_anomalies": ["anom_critical_nrr"],
      "noise_confidence": 0.93,
      "context_tags": ["churn_related", "retention_leak", "customer_attrition"],
      "natural_language_summary": "Churn rate rose from 2.1% to 5.2% over the past 8 months, consistently exceeding the expected baseline of 2.0% for a company of this profile."
    }
  ],
  "refusal": null
}
```

### `EnrichedReport` — full, from the `critical` scenario snapshot (`web/src/lib/scenario-fixtures/critical.json`'s `result` field)

```json
{
  "$schema": "enriched_report_v1",
  "anomaly_report": { "...verbatim AnomalyReport, see above..." },
  "prescriptions": [
    {
      "anomaly_id": "anom_critical_churn_rate",
      "prescribed_adjustments": [
        {
          "target_metric_id": "churn_rate",
          "target_display_name": "Churn Rate (%)",
          "action": "DECREASE",
          "direction_symbol": "-",
          "current_value": 5.2,
          "current_value_source": "submitted",
          "target_value": 2.0,
          "target_basis": "profile_baseline",
          "delta": -3.2,
          "priority": "HIGH",
          "rationale": "Move Churn Rate (%) toward the expected baseline for this profile."
        }
      ],
      "prescription_summary": "Address Churn Rate (%) to move back toward baseline."
    }
  ],
  "anomaly_clusters": [["anom_critical_churn_rate", "anom_critical_nrr"]],
  "matched_cases": [
    {
      "case_id": "case_mock_001", "cluster_index": 0, "similarity_score": 0.82,
      "problem_description": "Historical case resembling the Churn Rate (%) deviation.",
      "root_causes": ["Mock root cause A", "Mock root cause B"],
      "recommended_actions": ["Mock recommended action"]
    }
  ],
  "narrative": {
    "situation_summary": "Mock narrative: the submitted metrics show a coordinated deterioration consistent with the flagged anomalies.",
    "likely_root_causes": ["...", "..."],
    "prioritized_actions": [{ "action": "Investigate Churn Rate (%)", "priority": "HIGH", "rationale": "Flagged anomaly in this report." }],
    "positives": ["Gross margin remains stable near the expected baseline for this profile."]
  },
  "metadata": {
    "llm_model": "mock-llm-v1", "llm_tokens_used": 512, "processing_time_ms": 0,
    "cases_searched": 10, "cases_matched": 2, "unmatched_anomaly_ids": [],
    "degraded": false, "degraded_reason": null
  }
}
```

### Refusal response — full `ApiResponse` (`web/src/lib/scenario-fixtures/refusal.json`)

```json
{
  "job_id": "716eddd9-fc51-4b26-8f0b-09922c9d0a34",
  "status": "refused",
  "result": {
    "$schema": "enriched_report_v1",
    "anomaly_report": {
      "$schema": "anomaly_report_v1",
      "company_id": "company_refusal_001",
      "sector_id": "TECH_SAAS",
      "overall_health_score": null,
      "anomalies": [],
      "non_anomalous_highlights": [],
      "refusal": {
        "reason": "insufficient_periods",
        "message": "Every submitted metric has fewer than 6 monthly periods, the floor for full trend analysis. We can't reliably separate a genuine shift from noise with this little history.",
        "suggested_resolution": "Submit at least 6 consecutive monthly periods for at least one metric to receive a full analysis."
      },
      "metadata": { "model_version": "0.1.0-mock", "metrics_analyzed": 3, "metrics_with_anomalies": 0, "metrics_with_missing_data": 0, "skipped_metrics": [], "processing_time_ms": 45 }
    },
    "prescriptions": [], "anomaly_clusters": [], "matched_cases": [], "narrative": null,
    "metadata": { "llm_model": null, "llm_tokens_used": null, "processing_time_ms": 0, "cases_searched": 0, "cases_matched": 0, "unmatched_anomaly_ids": [], "degraded": false, "degraded_reason": null }
  },
  "warnings": [],
  "error": null,
  "timings": { "c1_ms": 200, "c3_ms": null, "total_ms": 205 }
}
```

Note `timings.c3_ms: null` — the field is only ever populated when C3 was
actually called (`api/orchestration/pipeline.py`).

---

## 3.7 Configuration

### `api/config/settings.py` — every field

| Name | Type | Default | Controls |
|---|---|---|---|
| `USE_MOCK_C1` | `bool` | `True` | Whether `get_c1()` returns the mock or attempts the real import |
| `USE_MOCK_C3` | `bool` | `True` | Same, for C3 |
| `MOCK_SCENARIO` | `Literal["healthy","critical","refusal","degraded"]` | `"critical"` | Which `FIXTURE_BUILDERS` entry `MockMLEngine` returns |
| `C1_TIMEOUT_S` | `float` | `10` | `asyncio.wait_for` timeout around the C1 call |
| `C3_TIMEOUT_S` | `float` | `30` | Same, for C3 |
| `LLM_TIMEOUT_S` | `int` | `20` | **Defined but not read anywhere in the code.** No call site references `settings.LLM_TIMEOUT_S`. |
| `MAX_UPLOAD_MB` | `int` | `10` | File-size check in `api/parsing/ingest.py::ingest_csv()` |
| `FEEDBACK_LOG_PATH` | `str` | `"./feedback.jsonl"` | **Defined but not read anywhere.** No `/feedback` route exists (§3.3). |
| `C1_MODULE_NAME` | `str` | `"ml_engine"` | Module `get_c1()` imports when not mocked |
| `C1_ENTRYPOINT_NAME` | `str` | `"analyze_company"` | Attribute name looked up on that module |
| `C3_MODULE_NAME` | `str` | `"c3_engine"` | ⚠️ **UNVERIFIED placeholder** — no handout or code has confirmed C3's real module name |
| `C3_ENTRYPOINT_NAME` | `str` | `"enrich_report"` | ⚠️ **UNVERIFIED placeholder** |
| `MOCK_C1_RAISE_ON_CALL` | `bool` | `False` | Forces `MockMLEngine.analyze_company` to raise |
| `MOCK_C1_SLEEP_S` | `float` | `0.2` | `MockMLEngine`'s simulated CPU-bound delay |
| `MOCK_C3_RAISE_ON_CALL` | `bool` | `False` | Forces `MockC3.enrich_report` to raise |
| `MOCK_C3_FAIL_LLM` | `bool` | `False` | `MockC3` returns `narrative=None`, `degraded=True` |
| `MOCK_C3_SLEEP_S` | `float` | `1.5` | `MockC3`'s simulated LLM-call delay |

Loaded via `pydantic_settings.BaseSettings` with `env_file=".env"`,
`extra="ignore"`. The two dead settings above (`LLM_TIMEOUT_S`,
`FEEDBACK_LOG_PATH`) are not errors — they're forward-declared for work that
hasn't landed (Phase 5) — but no current code path consumes them.

### `.env.example` (backend, repo root)

```bash
USE_MOCK_C1=true
USE_MOCK_C3=true
MOCK_SCENARIO=critical
C1_TIMEOUT_S=10
C3_TIMEOUT_S=30
LLM_TIMEOUT_S=20
MAX_UPLOAD_MB=10
FEEDBACK_LOG_PATH=./feedback.jsonl

C1_MODULE_NAME=ml_engine
C1_ENTRYPOINT_NAME=analyze_company
C3_MODULE_NAME=c3_engine
C3_ENTRYPOINT_NAME=enrich_report

MOCK_C1_RAISE_ON_CALL=false
MOCK_C1_SLEEP_S=0.2
MOCK_C3_RAISE_ON_CALL=false
MOCK_C3_FAIL_LLM=false
MOCK_C3_SLEEP_S=1.5
```

### `.env.example` (frontend, `web/.env.example`)

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_SHOW_SCENARIO_SWITCHER=false
```

### `metric_config.yaml` structure

Top-level keys: `metrics` (dict, 13 entries), `thresholds` (`min_periods`,
`severity_bands`, `confidence`), `revenue_bands` (list).

One full metric entry:

Verbatim from the file:

```yaml
  churn_rate:
    display_name: "Churn Rate (%)"
    unit: percentage
    valid_min: 0.0
    valid_max: 100.0
    direction: lower_is_better
    sector_ids: [TECH_SAAS]
    category: retention
    common_aliases: ["Churn", "Churn %", "Customer Churn", "Monthly Churn"]
```

(`unit` values used across the file: `percentage`, `currency_usd`, `ratio` —
confirmed by reading every metric entry, not a schema declaration.)

`thresholds.severity_bands` is present in the YAML but **not read by any
Python code** (`grep -rn severity_bands api/` matches only the YAML file
itself) — C1 owns severity scoring; this key documents C1's convention for
reference only. `thresholds.confidence.form` and `thresholds.confidence.default`
are similarly present but unused: `api/parsing/builder.py` hardcodes
`confidence = 1.0` for the `"form"` shape directly rather than reading
`thresholds()["confidence"]["form"]`; only `clean_csv` and `ambiguous_csv`
are actually read (`build_company_input()`, lines 160/162).

`requirements.txt` lists `scipy>=1.13`, but no `.py` file in this repo
imports `scipy` — it is an unused dependency (installs cleanly, does nothing).

### Canonical `metric_id`s per sector

**TECH_SAAS (7):** `monthly_recurring_revenue_growth`, `churn_rate`,
`customer_acquisition_cost`\*, `lifetime_value`, `net_revenue_retention`,
`burn_rate`, `gross_margin`\*

**RETAIL (8):** `gross_margin`\*, `customer_acquisition_cost`\*,
`inventory_turnover`, `average_order_value`, `revenue_per_sqft`,
`same_store_sales_growth`, `sell_through_rate`, `return_rate`

\* shared between both sectors (13 unique `metric_id`s total, confirmed by
`test_config.py::test_all_13_metrics_present`).

---

## 3.8 Mocks and fixtures

### Enabling each mock independently

`USE_MOCK_C1` and `USE_MOCK_C3` are independent booleans (`api/config/settings.py`)
— set either to `false` to attempt the real import for that component only.

### Selecting a scenario

`MOCK_SCENARIO=healthy|critical|refusal|degraded` (env var or `.env`). Read
by `api/orchestration/resolver.py::_mock_c1()` when constructing
`MockMLEngine`. Note: `MockC3`'s behaviour for the `"degraded"` scenario is
**not** automatic — `MockMLEngine` returns the same `AnomalyReport` for
`"critical"` and `"degraded"` (see `build_degraded()` in `builders.py`,
which just calls `build_critical()`); it is `MOCK_C3_FAIL_LLM=true` that
actually produces the degraded *output*. `scripts/dump_scenario_responses.py`
sets this automatically (`fail_llm = scenario == "degraded"`), but running
the live server with `MOCK_SCENARIO=degraded` alone does **not** trigger
`MockC3`'s fail path unless `MOCK_C3_FAIL_LLM=true` is also set.

### Injecting each failure mode

| Setting | Effect |
|---|---|
| `MOCK_C1_RAISE_ON_CALL=true` | `MockMLEngine.analyze_company` raises `RuntimeError` |
| `MOCK_C1_SLEEP_S=<seconds>` | Set above `C1_TIMEOUT_S` to force a C1 timeout |
| `MOCK_C3_RAISE_ON_CALL=true` | `MockC3.enrich_report` raises `RuntimeError` |
| `MOCK_C3_FAIL_LLM=true` | `MockC3` returns `narrative=None`, `metadata.degraded=True` |
| `MOCK_C3_SLEEP_S=<seconds>` | Set above `C3_TIMEOUT_S` to force a C3 timeout |

### The four fixtures (`api/tests/fixtures/builders.py`)

| Fixture | Company / shape | What it exercises |
|---|---|---|
| `healthy` | `Acme SaaS Co`, TECH_SAAS, 12 monthly periods, 5 metrics | `anomalies: []`, 3 highlights including `ltv_cac_ratio` (a computed `metric_id` absent from `metric_config.yaml`), `overall_health_score: 78.0` |
| `critical` | `Churn Co`, TECH_SAAS, 8 monthly periods, 3 metrics | 2 mutually-correlated anomalies (`churn_rate` ↔ `net_revenue_retention`), `SEVERE`/`CRITICAL` labels, full `trend.values_over_time`, `overall_health_score: 38.0` |
| `refusal` | `Small Test Co`, TECH_SAAS, 4 monthly periods, 3 metrics | `refusal.reason: "insufficient_periods"`, `overall_health_score: null`, `anomalies: []` |
| `degraded` | Identical to `critical` (`build_degraded()` just calls `build_critical()`) | The distinguishing behaviour lives entirely in `MockC3`, not this fixture |

### Dumping fixtures to JSON

```bash
./.venv/Scripts/python -m api.tests.fixtures.dump_fixtures
```
Writes `{scenario}_company_input.json` and `{scenario}_anomaly_report.json`
to `api/tests/fixtures/json/` for all four scenarios.

```bash
PYTHONPATH=. ./.venv/Scripts/python scripts/dump_scenario_responses.py
```
Writes a full `ApiResponse` JSON (including a `MockC3`-produced
`EnrichedReport`) per scenario to `web/src/lib/scenario-fixtures/` — this is
what the frontend's scenario switcher actually loads.

---

## 3.9 Behaviour tables

### Degradation matrix (`api/orchestration/pipeline.py`)

| Failure | C2 behaviour | `status` | What the UI shows |
|---|---|---|---|
| C1 raises | `_finish_failed(..., ErrorCode.C1_FAILED)` | `failed` | Generic error message (`ResultsView`'s `!response.result` branch) |
| C1 exceeds `C1_TIMEOUT_S` | `_finish_failed(..., ErrorCode.C1_TIMEOUT)` | `failed` | Same |
| C1 returns `refusal` | `wrap_bare_report(degraded=False, reason=None)` | `refused` | `RefusalView` — health score "N/A", no prescriptions/narrative |
| C3 raises | `wrap_bare_report(degraded=True, reason="c3_failed")` | `complete` | `DegradedBanner` + full anomalies/health score, no narrative |
| C3 exceeds `C3_TIMEOUT_S` | `wrap_bare_report(degraded=True, reason="c3_timeout")` | `complete` | Same |
| C3 output fails validation entirely | `wrap_bare_report(degraded=True, reason="c3_contract_violation")` | `complete` | Same |
| C3 output valid but `anomaly_report` drifted | Silently substituted back, logged only | `complete` | **No visible difference** — not marked degraded |
| Malformed request body | `RequestValidationError` handler | `failed` (422) | Generic error message |
| Any other unhandled exception | Catch-all handler | `failed` (500) | Generic error message |
| Escaped `C3ContractViolation` (should be unreachable) | Dedicated handler | `failed` (500) | Generic error message |

### Warning codes (`ParseWarningCode`, `api/models/internal.py`)

| Code | Fires when | Raised in |
|---|---|---|
| `UNKNOWN_METRIC` | Column doesn't resolve to any known `metric_id`; also when `mapping_overrides` names a nonexistent `metric_id` | `api/parsing/resolver.py::resolve()`; `api/parsing/builder.py::build_company_input()` |
| `SECTOR_MISMATCH` | Resolves to a real metric not offered for the submitted sector | `api/parsing/resolver.py::resolve()` |
| `AMBIGUOUS_MAPPING` | Normalized label matches ≥2 distinct metrics | `api/parsing/resolver.py::resolve()` |
| `UNIT_SCALE_SUSPECT` | All values of a `percentage`-unit metric (≥3 values) fall in `[0.0, 1.0]` | `api/parsing/validation.py::validate_and_build_metric()`, step 5 |
| `OUT_OF_RANGE` | Value outside `valid_min`/`valid_max` | Same, step 6 |
| `SHORT_SERIES` | Below hard-block (excludes) or in the soft-warn band (includes with warning) — same code, both cases | Same, steps 1/9 |
| `SPARSE_SERIES` | >50% of a metric's submitted values were missing/invalid | Same, step 6 |
| `CONSTANT_SERIES` | Every surviving value identical | Same, step 8 |
| `DUPLICATE_PERIOD` | Same period appears >1x for one metric (kept the last) | Same, step 2 |
| `MIXED_GRANULARITY` | One metric's periods don't share one granularity | Same, step 3 |
| `AMBIGUOUS_NUMBER_FORMAT` | Column mixes American/European number separators — all values in the column discarded | Same, step 4 |
| `SERIES_TRIMMED` | A ≥4-period gap trimmed the series to its most recent contiguous block | `api/parsing/primitives.py::apply_gap_policy()` |
| `INTERPOLATED_POINTS` | Any 1–3 period gap was linearly interpolated | Same |
| `INTERPOLATION_HEAVY` | >30% of the final series is interpolated | Same |
| `DATE_TRUNCATED` | A full date (`YYYY-MM-DD`) was truncated to its period | `api/parsing/primitives.py::parse_period()` |
| `TWO_DIGIT_YEAR_FUTURE` | A 2-digit year, assumed 2000s, landed >1 year in the future | Same |
| `REFUSAL_LIKELY` | Every surviving metric is below its trend floor | `api/parsing/validation.py::check_refusal_likely()` |
| `SCHEMA_VALIDATION_ERROR` | Generic body-shape failure (JSON body, non-UTF-8 file decode) | `api/main.py`'s `RequestValidationError` handler; `api/parsing/ingest.py::_decode()` |
| `AMBIGUOUS_SHAPE` | **Defined but never raised.** The code path it describes (`_detect_shape()` unable to determine wide vs. transposed) raises a plain `IngestError` directly instead of a `ParseWarning` with this code. | *(none — dead enum member)* |

### Error codes (`ErrorCode`, `api/models/internal.py`)

| Code | Fires when | Raised in |
|---|---|---|
| `VALIDATION_ERROR` | Request body/multipart fails validation | `api/main.py`, `api/routes/analyze.py` |
| `C1_FAILED` | C1 raised | `api/orchestration/pipeline.py` |
| `C1_TIMEOUT` | C1 exceeded `C1_TIMEOUT_S` | Same |
| `C1_UNAVAILABLE` | **Reserved, never set.** `get_c1()` falls back to the mock silently (with a log warning) rather than surfacing this to the client. | *(none)* |
| `C3_FAILED` | C3 raised | `api/orchestration/pipeline.py` |
| `C3_TIMEOUT` | C3 exceeded `C3_TIMEOUT_S` | Same |
| `C3_CONTRACT_VIOLATION` | C3 output unparseable, or (unreachably) escaped the orchestrator | `api/orchestration/pipeline.py`; `api/main.py`'s dedicated handler |
| `INTERNAL_ERROR` | Any other unhandled exception | `api/main.py`'s catch-all handler |

### Validation thresholds (`metric_config.yaml` → `thresholds`)

| Granularity | Hard block | Soft warn | Full trend |
|---|---|---|---|
| Monthly | < 3 | 3–5 | ≥ 6 |
| Quarterly | < 2 | 2–3 | ≥ 4 |
| Annual | < 2 | 2 | ≥ 3 |

Gap policy tiers (`api/parsing/primitives.py::apply_gap_policy`,
`break_threshold=4` hardcoded, not configurable): gaps of 1–3 periods →
linear interpolation, `interpolated: true`; gaps of ≥4 periods → trim to the
most recent contiguous block, `SERIES_TRIMMED`.

`severity_bands` (SEVERE ≥75, CRITICAL ≥50, WARNING ≥25) exist in
`metric_config.yaml` for reference but are **not computed by any C2 code** —
severity scoring is C1's responsibility.

---

## 3.10 Running locally

Verified on Python 3.14.2, Node v24.15.0, npm 11.12.1, Windows, from a shell
that supports the `./.venv/Scripts/python` path style shown (adjust to
`./.venv/bin/python` on macOS/Linux).

### Backend

```bash
cd <repo-root>
python -m venv .venv
.venv\Scripts\activate          # Windows; `source .venv/bin/activate` elsewhere
pip install -r requirements.txt
cp .env.example .env
uvicorn api.main:app --reload   # serves on http://localhost:8000
```

### Tests

```bash
pytest                          # 199 tests, api/tests/ (see pytest.ini)
```

### Dump fixtures (needed once before first frontend run, and after any model/fixture change)

```bash
python -m api.tests.fixtures.dump_fixtures
PYTHONPATH=. python scripts/dump_scenario_responses.py
```

### Frontend

Requires the backend running first (type generation hits it live).

```bash
cd web
npm install
cp .env.example .env.local      # set NEXT_PUBLIC_SHOW_SCENARIO_SWITCHER=true for local dev
npm run types                   # regenerates src/types/api.ts from http://localhost:8000/openapi.json
npm run dev                     # serves on http://localhost:3000
```

Nothing non-obvious was needed on this machine — no `--break-system-packages`,
no platform-specific pandas/numpy wheel issues on Python 3.14.

---

## 7. Deviations

Read this section first.

| # | Where | Contract says (or is silent) | Code actually does | Resolves when |
|---|---|---|---|---|
| 1 | `EnrichmentMetadata.degraded_reason` (`api/models/shared.py`) | Contract §6.2's `EnrichmentMetadata` has no `degraded_reason` field | C2 added it, additive/optional, `Optional[str]`, deliberately not an enum. Announced internally as "C2-PROPOSED v1.2" but **not yet raised with C1/C3 as a contract amendment**. | C3's owner reviews and either adopts it or the field is renamed/removed |
| 2 | Empty `metrics: []` reaching C1 (`api/parsing/builder.py`) | Neither the contract nor the phase plans state this explicitly; the brief that requested this document assumed C2 guarantees non-empty metric lists | **It does not.** If every submitted metric is excluded during validation, C2 sends `metrics: []` and relies on C1's own `NO_METRICS_SUBMITTED` refusal. The resulting refusal reason is misleading — the user did submit data; C2 discarded all of it for reasons never surfaced in the refusal itself. | Scheduled for Phase 5: C2 should return its own blocking error naming the actual exclusion reasons instead of deferring to a generic C1 refusal. Flagged here and in §3.4 so C1's developer doesn't build handling around an assumption that's about to change. |
| 3 | `RefusalDetail.message` / `.suggested_resolution` (`api/models/shared.py`) | Contract §5.1 shows `message` as a bare (required) `str`; only `reason` is confirmed against C1's actual source | Both fields are `Optional[str] = None` on C2's side, and `model_config = ConfigDict(extra="allow")` is set so any real fields from C1 that weren't predicted survive rather than being dropped | C1 shares real `RefusalDetail` field names/types from `ml_engine`'s source |
| 4 | `C3_MODULE_NAME` / `C3_ENTRYPOINT_NAME` (`api/config/settings.py`) | Contract doesn't name a module | Hardcoded placeholders `"c3_engine"` / `"enrich_report"`, explicitly marked ⚠️ UNVERIFIED in code comments | C3 confirms the real module path and entry-point signature |
| 5 | `POST /feedback` | Named in the contract's locked API surface (§7) and in this document's own generation brief | **Does not exist in the code at all** — no route, model, or handler. `FEEDBACK_LOG_PATH` setting exists but is unread. | Phase 5 (Hardening & Demo) |
| 6 | `AMBIGUOUS_SHAPE` warning code (`api/models/internal.py`) | N/A — internal, not contract-governed | Defined in the `ParseWarningCode` enum but never actually raised; the code path it names raises a plain `IngestError` (blocking) instead | Cosmetic — either wire the enum in or remove it |
| 7 | `EnrichedReport` as a whole (`api/models/shared.py`) | Contract §11 sign-off table is empty for all three components | The entire schema is implemented and exercised by the mocks/tests, but is explicitly still "PROPOSED" per the code's own docstring | C1, C2, C3 all sign §11 |

### ⚠️ UNVERIFIED items and what would resolve them

| Item | Why it's unverified | Resolves when |
|---|---|---|
| C1's real `analyze_company` signature — does it accept a `CompanyInput` **instance** or a plain `dict`? | `get_c1()` calls it with a live `CompanyInput` object (§3.4); no real `ml_engine` module has ever been available to import in this environment to confirm it accepts that | C1 repo access lands, or C1's developer confirms directly |
| C3's real module name/entry point (`c3_engine.enrich_report`) | Placeholder values in `settings.py`, explicitly commented `# UNVERIFIED — ask C3 this week` | C3 confirms |
| Whether real C3 implements the refusal defensive guard (Contract §6.3) | Only `MockC3` has been observed; no real C3 code exists to inspect | C3 repo access lands |
| `RefusalDetail`'s true field set beyond `reason` | Only `reason` is confirmed against C1's actual source per the contract's own text; `message`/`suggested_resolution` are C2's guesses | C1 shares `ml_engine`'s real `output_schema.py` |
| Real C1/C3 latency (used to decide the sync-vs-async swap noted in the root README) | Never measured — only mock sleeps (`0.2s`/`1.5s`) have been observed | Phase 4, once real C1/C3 are wired in |

## Verification pass performed

Every file path, function/route signature, and env var named above was
re-read directly from the files on disk in this session (not recalled from
memory of writing them) immediately before this document was generated;
every JSON example was produced by actually running `dump_fixtures.py` and
`dump_scenario_responses.py` in this session, not hand-written or reused
from an earlier run. `grep` was used to confirm claimed non-usage (`scipy`,
`AMBIGUOUS_SHAPE`, `severity_bands`, `LLM_TIMEOUT_S`, `FEEDBACK_LOG_PATH`,
`C1_UNAVAILABLE`) rather than asserting absence from memory. Total test
count (199) and per-file counts were taken from a live `pytest --collect-only`
run, not estimated.

Not independently verifiable from this repository alone (listed once here
rather than repeated per-section): anything about C1's or C3's actual
internals, since neither real module exists on disk in this environment —
every claim above about "what C1/C3 will do" is inferred from C2's own
handling code (what it's built to expect), not from observing real C1/C3
behavior.
