"""The orchestrator — the spine (Phase1-Plan T1.3). Routes, times, and
catches. No business logic: it never inspects an anomaly, computes a score,
or decides what's important.

Status semantics, decided once, here:

    complete  Pipeline ran. Includes degraded runs.         result populated
    refused   C1 declined to analyse — insufficient evidence. result populated (bare wrap)
    failed    C1 unavailable. Nothing to show.               result=None, error populated
    running   Reserved for the async swap. Unused in Phase 1. result=None

Degraded is not a fifth status — it's status="complete" with
result.metadata.degraded=true. `refused` is not a failure; it's the system
working as designed (Contract §6.3) and must never render as an error state.

The threading gotcha: asyncio.wait_for() around asyncio.to_thread() returns
control but does not kill the thread. A hung C1/C3 call keeps a worker thread
occupied for the process's lifetime. Accepted for MVP — the real fix (a
process pool with cancellation) is out of scope — but every timeout logs a
warning stating the thread was abandoned, so a stuck demo has a visible cause.
"""

import asyncio
import logging
import time
import uuid

from api.config.settings import settings
from api.models.internal import ApiResponse, ErrorCode, Timings
from api.models.shared import CompanyInput
from api.orchestration.adapters import C3ContractViolation, adapt_c3_output
from api.orchestration.degradation import wrap_bare_report
from api.orchestration.resolver import get_c1, get_c3

logger = logging.getLogger(__name__)


def _ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


async def run_pipeline(company_input: CompanyInput) -> ApiResponse:
    job_id = str(uuid.uuid4())
    t0 = time.monotonic()
    logger.info("pipeline stage=start job_id=%s company_id=%s", job_id, company_input.company_id)

    # ---------------- Stage 1: C1 ----------------
    c1_start = time.monotonic()
    try:
        c1_callable = get_c1()
        report = await asyncio.wait_for(
            asyncio.to_thread(c1_callable, company_input), timeout=settings.C1_TIMEOUT_S
        )
    except TimeoutError:
        c1_ms = _ms(c1_start)
        logger.warning(
            "pipeline stage=c1 job_id=%s outcome=timeout duration_ms=%s error=%s "
            "thread_abandoned=true",
            job_id,
            c1_ms,
            ErrorCode.C1_TIMEOUT.value,
        )
        return _finish_failed(job_id, t0, c1_ms, ErrorCode.C1_TIMEOUT)
    except Exception:
        c1_ms = _ms(c1_start)
        logger.exception(
            "pipeline stage=c1 job_id=%s outcome=failed duration_ms=%s error=%s",
            job_id,
            c1_ms,
            ErrorCode.C1_FAILED.value,
        )
        return _finish_failed(job_id, t0, c1_ms, ErrorCode.C1_FAILED)

    c1_ms = _ms(c1_start)
    logger.info("pipeline stage=c1 job_id=%s outcome=ok duration_ms=%s", job_id, c1_ms)

    # ---------------- Refusal short-circuit (Contract §3) ----------------
    if report.refusal is not None:
        logger.info("pipeline stage=c3 job_id=%s outcome=skipped reason=refusal", job_id)
        total_ms = _ms(t0)
        logger.info(
            "pipeline stage=complete job_id=%s status=refused duration_ms=%s", job_id, total_ms
        )
        return ApiResponse(
            job_id=job_id,
            status="refused",
            result=wrap_bare_report(report, degraded=False, reason=None),
            timings=Timings(c1_ms=c1_ms, c3_ms=None, total_ms=total_ms),
        )

    # ---------------- Stage 2: C3 ----------------
    c3_start = time.monotonic()
    try:
        c3_callable = get_c3()
        raw = await asyncio.wait_for(
            asyncio.to_thread(c3_callable, report), timeout=settings.C3_TIMEOUT_S
        )
        enriched = adapt_c3_output(raw, original=report)
        c3_ms = _ms(c3_start)
        logger.info("pipeline stage=c3 job_id=%s outcome=ok duration_ms=%s", job_id, c3_ms)
    except TimeoutError:
        c3_ms = _ms(c3_start)
        logger.warning(
            "pipeline stage=c3 job_id=%s outcome=timeout duration_ms=%s error=%s "
            "thread_abandoned=true",
            job_id,
            c3_ms,
            ErrorCode.C3_TIMEOUT.value,
        )
        enriched = wrap_bare_report(report, degraded=True, reason="c3_timeout")
    except C3ContractViolation:
        c3_ms = _ms(c3_start)
        logger.exception(
            "pipeline stage=c3 job_id=%s outcome=contract_violation duration_ms=%s error=%s",
            job_id,
            c3_ms,
            ErrorCode.C3_CONTRACT_VIOLATION.value,
        )
        enriched = wrap_bare_report(report, degraded=True, reason="c3_contract_violation")
    except Exception:
        c3_ms = _ms(c3_start)
        logger.exception(
            "pipeline stage=c3 job_id=%s outcome=failed duration_ms=%s error=%s",
            job_id,
            c3_ms,
            ErrorCode.C3_FAILED.value,
        )
        enriched = wrap_bare_report(report, degraded=True, reason="c3_failed")

    total_ms = _ms(t0)
    logger.info(
        "pipeline stage=complete job_id=%s status=complete degraded=%s duration_ms=%s",
        job_id,
        enriched.metadata.degraded,
        total_ms,
    )
    return ApiResponse(
        job_id=job_id,
        status="complete",
        result=enriched,
        timings=Timings(c1_ms=c1_ms, c3_ms=c3_ms, total_ms=total_ms),
    )


def _finish_failed(job_id: str, t0: float, c1_ms: int, error: ErrorCode) -> ApiResponse:
    total_ms = _ms(t0)
    logger.info(
        "pipeline stage=complete job_id=%s status=failed duration_ms=%s", job_id, total_ms
    )
    return ApiResponse(
        job_id=job_id,
        status="failed",
        error=error,
        timings=Timings(c1_ms=c1_ms, c3_ms=None, total_ms=total_ms),
    )
