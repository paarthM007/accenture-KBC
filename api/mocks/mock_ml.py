"""Stand-in for `ml_engine.analyze_company`. Signature matches the real entry
point exactly (Contract §3) so Phase 4 is an import swap and nothing more.
"""

import time

from api.models.shared import AnomalyReport, CompanyInput
from api.tests.fixtures.builders import FIXTURE_BUILDERS


class MockMLEngine:
    def __init__(self, scenario: str = "critical", raise_on_call: bool = False, sleep_s: float = 0.2):
        if scenario not in FIXTURE_BUILDERS:
            raise ValueError(f"Unknown MOCK_SCENARIO: {scenario!r}")
        self.scenario = scenario
        self.raise_on_call = raise_on_call
        self.sleep_s = sleep_s  # mimics CPU-bound work; exercises asyncio.to_thread() from day one

    def analyze_company(self, payload: CompanyInput) -> AnomalyReport:
        if self.raise_on_call:
            raise RuntimeError("MockMLEngine configured to raise (raise_on_call=True)")

        time.sleep(self.sleep_s)

        _, report = FIXTURE_BUILDERS[self.scenario]()
        # Override so the response is at least internally consistent with the
        # actual request, even though the rest of the report is canned.
        return report.model_copy(update={"company_id": payload.company_id, "sector_id": payload.sector_id})
