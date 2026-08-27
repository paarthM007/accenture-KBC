# CLAUDE.md

businessintelligence.ai — a KPI storytelling engine (Accenture Innovation
Challenge 2026, Problem Statement 3). A company submits business metrics; the
system compares them to a synthetic sector/size baseline, detects meaningful
anomalies, prescribes corrective actions, retrieves similar historical cases,
and produces an executive narrative — or refuses to guess when the evidence
is insufficient.

## This repo is C2

Three components. C1 (Anomaly Detection) and C3 (Prescription, Case Match,
Narrative) are separate repos, both called in-process. C2 owns everything
else: input ingestion, normalization, validation, orchestration, error
handling, the API surface, and the frontend.

```
User → C2 parse/validate → C1.analyze_company() → [refusal? stop here]
                          → C3.enrich_report() → C2 assembles → user
```

C2 is last in the chain and the only component with a live user. Every C1/C3
exception becomes our problem, not an HTTP 500.

## The architectural boundary — do not breach

`api/orchestration/pipeline.py::run_pipeline()` takes a `CompanyInput` and
nothing else. It does not know about CSV, forms, or HTTP. Phase 2's parser
(`api/parsing/`) builds a `CompanyInput` and hands it to `run_pipeline()`
unchanged — this is why the parser can be replaced or extended without
touching orchestration, and vice versa. If a change would require
`run_pipeline()` to accept anything else, that change is wrong.

## Canonical schema

`api/models/shared.py` is canonical for `CompanyInput`, `AnomalyReport`,
`EnrichedReport`. C1 owns the real schema in its own repo
(`ml_engine/models/`); if it ever conflicts with this file, **C1's repo wins**
— resync this file and log the change in `docs/C2_REFERENCE.md` §7.
`api/models/internal.py` holds C2-only models (nobody else depends on them).

## Invariants

- **No HTTP 500, ever, on an anticipated path.** Every C1/C3 failure mode
  (raise, timeout, malformed output, refusal) degrades into a structured
  `ApiResponse`/`ValidateResponse`. The one catch-all handler in `api/main.py`
  exists for genuinely unexpected bugs, not as a normal exit.
- **Every stage degrades, never dies.** `degraded: true` + `degraded_reason`
  on `EnrichedReport.metadata`, not a different status code.
- **No business logic in the orchestrator.** `pipeline.py` routes, times, and
  catches. It never inspects an anomaly or computes anything.
- **No statistics computed in C2.** z-scores, severity, health score, noise
  filtering — all C1. If you find yourself computing one in `api/`, stop.
- **No hardcoded metric IDs, sectors, or thresholds outside
  `api/config/metric_config.yaml`.**
- **Never invent a number.** A value not submitted or computed upstream is
  `null`, never `0` or a guess.

## Commands

```bash
uvicorn api.main:app --reload                              # backend, :8000
pytest                                                      # 199 tests
python -m api.tests.fixtures.dump_fixtures                  # CompanyInput/AnomalyReport JSON
PYTHONPATH=. python scripts/dump_scenario_responses.py       # full ApiResponse JSON (feeds frontend)
cd web && npm run dev                                        # frontend, :3000 (backend must be running)
cd web && npm run types                                      # regenerate src/types/api.ts (backend must be running)
```

## Read next

- `pipeline-Contract-V1.md` — the cross-team contract. Overrides this file
  and `docs/C2_REFERENCE.md` wherever they disagree, until all three
  components sign off on it.
- `docs/C2_REFERENCE.md` — the full integration reference, generated from
  code. **Its §7 (Deviations) lists every place this repo currently
  disagrees with `pipeline-Contract-V1.md`** — read that before assuming the
  contract document is current.
- `C2-MasterPlan.md` — this component's build plan and design rationale.
- Per-phase task breakdowns (`Phase0-Plan.md` … `Phase3-Plan.md`) and the doc-
  generation brief are kept outside this repo (`tasks/`, gitignored —
  internal working documents, not deliverables). If you're reading this from
  a clone, they aren't there.
