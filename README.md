# businessintelligence.ai — C2 (API, Parsing & Orchestration)

This repository is the **C2** component of a three-component pipeline for the Accenture
Innovation Challenge 2026 (Problem Statement 3): a KPI storytelling engine that detects
anomalies in a company's business metrics, prescribes corrective actions, and produces an
executive narrative.

C2 owns input ingestion, normalization, validation, pipeline orchestration, error handling,
the API surface, and the frontend. It calls two other in-process components:

- **C1** — Anomaly Detection Engine (`analyze_company(CompanyInput) -> AnomalyReport`)
- **C3** — Prescription, Case Matching & Narrative (`enrich_report(AnomalyReport) -> EnrichedReport`)

Both are mocked in this repo until they land; see `api/config/settings.py` for the
`USE_MOCK_C1` / `USE_MOCK_C3` switches.

**Source of truth, in order of authority:**

1. `pipeline-Contract-V1.md` — the cross-team contract. Overrides everything below once signed off.
2. `docs/C2_REFERENCE.md` — generated from this code; read its §7 (Deviations) for every place the implementation currently disagrees with the contract.
3. `C2-MasterPlan.md` — this component's build plan and design rationale.

Per-phase task breakdowns (`Phase0-Plan.md` … `Phase3-Plan.md`) and the brief
that generated `docs/C2_REFERENCE.md` are internal working documents, kept
outside this repo (`tasks/`, gitignored).

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
cp .env.example .env
```

## Run

```bash
uvicorn api.main:app --reload
```

## Test

```bash
pytest
```

## API

```
POST /analyze          run the pipeline (CompanyInput JSON in, ApiResponse out)
POST /analyze/upload    parse a CSV upload, then run the same unchanged pipeline
POST /validate          dry-run the parser: proposals + warnings, no C1/C3, free and repeatable
GET  /health            liveness + component import check
```

`/validate` and `/analyze/upload` take multipart requests: a `file` (CSV) plus
a `metadata` field (JSON-encoded `FormMetadata` — company name, sector,
employee count, region, and either `annual_revenue` or `revenue_band`).
`/analyze/upload` also accepts an optional `mapping_overrides` field (JSON
object of `{source_label: metric_id}`) carrying the user's corrections from a
prior `/validate` call.

See `api/tests/fixtures/csv/` for the messy-CSV corpus (wide/transposed
shapes, unit-scale errors, gaps, structural breaks, wrong-sector columns,
garbage input) — each fixture is a worked example of one specific parsing
edge case and the warning code it produces.

## Known limitations (MVP)

- **A C1/C3 timeout does not kill the worker thread.** `asyncio.wait_for()`
  wrapping `asyncio.to_thread()` returns control to the caller but the thread
  itself keeps running until the mocked/real call finishes — a hung call
  leaks a thread for the rest of the process's lifetime. Every timeout logs
  an explicit warning (`thread_abandoned=true`) so a stuck demo has a visible
  cause. The real fix is a process pool with cancellation; out of scope for
  MVP, scoped as a ~2h Phase 4 task if real latency demands it.
- **Synchronous request/response.** Mock latency (~1.7s) is fine for a
  synchronous call; real latency (C1 ~3s + C3 LLM 5–15s) likely isn't. The
  `ApiResponse` envelope already carries `job_id`/`status` so the swap to an
  async job-store + polling model changes no response shape. The swap path
  (in-memory `dict[job_id, ApiResponse]`, background task, `GET
  /analyze/{job_id}`) is documented in this component's internal build plan,
  scoped as a ~2h task once real latency is measured.
