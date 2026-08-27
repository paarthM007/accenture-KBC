"""Dumps all four fixtures to tests/fixtures/json/ as the concrete artifact
for C1 and C3 to build against (Phase0-Plan T0.6 / handoff to Phase 1).

Run from the project root:
    python -m api.tests.fixtures.dump_fixtures
"""

import json
from pathlib import Path

from api.tests.fixtures.builders import FIXTURE_BUILDERS

OUT_DIR = Path(__file__).parent / "json"


def dump_all() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, builder in FIXTURE_BUILDERS.items():
        company_input, anomaly_report = builder()
        (OUT_DIR / f"{name}_company_input.json").write_text(
            json.dumps(company_input.model_dump(mode="json", by_alias=True), indent=2),
            encoding="utf-8",
        )
        (OUT_DIR / f"{name}_anomaly_report.json").write_text(
            json.dumps(anomaly_report.model_dump(mode="json", by_alias=True), indent=2),
            encoding="utf-8",
        )
        print(f"wrote {name}_company_input.json and {name}_anomaly_report.json")


if __name__ == "__main__":
    dump_all()
