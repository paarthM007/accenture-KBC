"""One-off script: dumps a full ApiResponse JSON per demo scenario, using the
existing fixture builders + mocks directly (no HTTP round trip, no server
restart needed). Feeds the frontend's scenario switcher (Phase3-Plan T3.8) —
"No new backend endpoints" rules out a live runtime-scenario endpoint, so the
switcher swaps between the real API and these static snapshots instead.

Run from the project root:
    ./.venv/Scripts/python.exe scripts/dump_scenario_responses.py
"""

import json
import uuid
from pathlib import Path

from api.mocks.mock_c3 import MockC3
from api.models.internal import ApiResponse, Timings
from api.orchestration.degradation import wrap_bare_report
from api.tests.fixtures.builders import FIXTURE_BUILDERS

OUT_DIR = Path(__file__).parent.parent / "web" / "src" / "lib" / "scenario-fixtures"


def build_response(scenario: str) -> ApiResponse:
    _, report = FIXTURE_BUILDERS[scenario]()

    if report.refusal is not None:
        enriched = wrap_bare_report(report, degraded=False, reason=None)
        return ApiResponse(
            job_id=str(uuid.uuid4()),
            status="refused",
            result=enriched,
            timings=Timings(c1_ms=200, c3_ms=None, total_ms=205),
        )

    fail_llm = scenario == "degraded"
    c3 = MockC3(fail_llm=fail_llm, sleep_s=0)
    enriched = c3.enrich_report(report)
    return ApiResponse(
        job_id=str(uuid.uuid4()),
        status="complete",
        result=enriched,
        timings=Timings(c1_ms=200, c3_ms=1500, total_ms=1700),
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for scenario in FIXTURE_BUILDERS:
        response = build_response(scenario)
        out_path = OUT_DIR / f"{scenario}.json"
        out_path.write_text(
            json.dumps(response.model_dump(mode="json", by_alias=True), indent=2), encoding="utf-8"
        )
        print(f"wrote {out_path.relative_to(Path(__file__).parent.parent)}")


if __name__ == "__main__":
    main()
