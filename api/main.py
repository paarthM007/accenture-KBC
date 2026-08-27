"""FastAPI app (Phase0-Plan T0.8, Phase1-Plan T1.5).

Exception handlers override FastAPI's default error shapes so every response
— success, validation failure, or crash — comes back as an ApiResponse. A
demo that shows partial results survives; one that returns a bare 500
traceback on the projector doesn't.
"""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.models.internal import ApiResponse, ErrorCode, ParseWarning, ParseWarningCode, ValidateResponse
from api.orchestration.adapters import C3ContractViolation
from api.routes import analyze, health, validate

# Root logger has no handler by default, so api.orchestration.pipeline's
# structured stage logs (T1.6) would be silently dropped without this.
# basicConfig() is a no-op if a handler is already attached (e.g. pytest's
# own log capture), so it's safe to call unconditionally at import time.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

logger = logging.getLogger(__name__)

app = FastAPI(title="businessintelligence.ai — C2 API", version="0.1.0")

# Registered now so Phase 3 (frontend) doesn't stall on it. Tighten
# allow_origins before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(analyze.router)
app.include_router(validate.router)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    warnings = [
        ParseWarning(
            code=ParseWarningCode.SCHEMA_VALIDATION_ERROR,
            message=f"{'.'.join(str(p) for p in error['loc'])}: {error['msg']}",
        )
        for error in exc.errors()
    ]

    if request.url.path == "/validate":
        # /validate's contract is ValidateResponse, not ApiResponse — this
        # fires when FastAPI rejects the multipart request itself (e.g. a
        # missing `file` or `metadata` field) before our route body runs.
        response = ValidateResponse(
            warnings=warnings,
            blocking_errors=[w.message for w in warnings],
            ready=False,
        )
        return JSONResponse(status_code=422, content=response.model_dump(mode="json"))

    response = ApiResponse(
        job_id=str(uuid.uuid4()),
        status="failed",
        error=ErrorCode.VALIDATION_ERROR,
        warnings=warnings,
    )
    return JSONResponse(status_code=422, content=response.model_dump(mode="json", by_alias=True))


@app.exception_handler(C3ContractViolation)
async def c3_contract_violation_handler(request: Request, exc: C3ContractViolation) -> JSONResponse:
    # Documented in Phase1-Plan T1.5 as "caught upstream, shouldn't reach
    # here" — run_pipeline() catches C3ContractViolation itself and degrades
    # in place (it has the original AnomalyReport to fall back to). This
    # handler only fires if that guarantee is ever broken by a bug, and at
    # that point we have no original report to substitute — so unlike the
    # documented "200, degraded" outcome, the honest response here is a loud
    # internal error, not a fabricated partial result.
    logger.error("C3ContractViolation escaped the orchestrator's own handling — this is a bug: %s", exc)
    response = ApiResponse(
        job_id=str(uuid.uuid4()), status="failed", error=ErrorCode.C3_CONTRACT_VIOLATION
    )
    return JSONResponse(status_code=500, content=response.model_dump(mode="json", by_alias=True))


@app.exception_handler(Exception)
async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception")
    response = ApiResponse(job_id=str(uuid.uuid4()), status="failed", error=ErrorCode.INTERNAL_ERROR)
    return JSONResponse(status_code=500, content=response.model_dump(mode="json", by_alias=True))
