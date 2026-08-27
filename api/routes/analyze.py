"""POST /analyze (Phase1-Plan T1.5) and POST /analyze/upload (Phase2-Plan T2.7).

Architectural boundary, do not breach: run_pipeline() takes a CompanyInput and
nothing else. POST /analyze stays exactly as it is — that's what keeps
Phase 1's 77 tests green and keeps the parser swappable. /analyze/upload only
parses, then calls the same unchanged run_pipeline().
"""

import json
import uuid
from typing import Optional

from pydantic import ValidationError

from fastapi import APIRouter, File, Form, UploadFile

from api.models.internal import ApiResponse, ErrorCode, FormMetadata, ParseWarning, ParseWarningCode
from api.models.shared import CompanyInput
from api.orchestration.pipeline import run_pipeline
from api.parsing.builder import build_company_input
from api.parsing.ingest import IngestError, ingest_csv

router = APIRouter()


@router.post("/analyze", response_model=ApiResponse)
async def analyze(company_input: CompanyInput) -> ApiResponse:
    return await run_pipeline(company_input)


def _failed_before_pipeline(message: str) -> ApiResponse:
    return ApiResponse(
        job_id=str(uuid.uuid4()),
        status="failed",
        error=ErrorCode.VALIDATION_ERROR,
        warnings=[ParseWarning(code=ParseWarningCode.SCHEMA_VALIDATION_ERROR, message=message)],
    )


@router.post("/analyze/upload", response_model=ApiResponse)
async def analyze_upload(
    file: UploadFile = File(...),
    metadata: str = Form(...),
    mapping_overrides: Optional[str] = Form(None),
) -> ApiResponse:
    try:
        form_metadata = FormMetadata.model_validate_json(metadata)
    except ValidationError as exc:
        return _failed_before_pipeline(f"Invalid company metadata: {exc}")

    overrides: dict[str, str] = {}
    if mapping_overrides:
        try:
            overrides = json.loads(mapping_overrides)
        except json.JSONDecodeError as exc:
            return _failed_before_pipeline(f"mapping_overrides was not valid JSON: {exc}")

    file_bytes = await file.read()
    try:
        raw_table = ingest_csv(file_bytes, file.filename or "upload.csv")
    except IngestError as exc:
        return _failed_before_pipeline(str(exc))

    result = build_company_input(raw_table, form_metadata, overrides)
    if result.blocking_errors:
        return ApiResponse(
            job_id=str(uuid.uuid4()),
            status="failed",
            error=ErrorCode.VALIDATION_ERROR,
            warnings=result.warnings
            + [ParseWarning(code=ParseWarningCode.SCHEMA_VALIDATION_ERROR, message=e) for e in result.blocking_errors],
        )

    response = await run_pipeline(result.company_input)
    # Parse warnings must survive the pipeline, not be dropped at the handoff.
    return response.model_copy(update={"warnings": result.warnings + response.warnings})
