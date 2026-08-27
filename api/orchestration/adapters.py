"""Adapter seam (Phase1-Plan T1.4). In Phase 1, with mocks, this is nearly a
passthrough — but it gives Phase 4 exactly one place to absorb C3 drift,
instead of scattering compatibility shims through the orchestrator.

# KNOWN DRIFT RISKS (Contract §6.1) — his earlier draft did all three:
#   - renamed `anomalies` -> `detected_anomalies`
#   - renamed `metric_id` -> `source_metric`
#   - dropped `company_profile_summary`
# If he ships any of those again, this is where it gets caught.
"""

import logging
from typing import Any

from api.models.shared import AnomalyReport, EnrichedReport

logger = logging.getLogger(__name__)


class C3ContractViolation(Exception):
    """Raised when raw C3 output can't be coerced into a valid EnrichedReport
    at all. Caught by the orchestrator -> degraded path (Contract §6.1)."""


def adapt_c3_output(raw: Any, *, original: AnomalyReport) -> EnrichedReport:
    if isinstance(raw, EnrichedReport):
        enriched = raw
    elif isinstance(raw, dict):
        try:
            enriched = EnrichedReport.model_validate(raw)
        except Exception as exc:  # noqa: BLE001 — any validation failure is a contract violation
            raise C3ContractViolation(f"C3 output failed schema validation: {exc}") from exc
    else:
        raise C3ContractViolation(f"C3 returned an unrecognised type: {type(raw)!r}")

    if enriched.anomaly_report != original:
        # The exact failure Contract §6.1 exists to prevent. C2 keeps
        # working; the violation is loud in the logs, not silent in the UI.
        logger.error(
            "C3 output did not preserve the AnomalyReport verbatim (Contract §6.1 violation) — "
            "substituting the original report back in."
        )
        enriched = enriched.model_copy(update={"anomaly_report": original})

    return enriched
