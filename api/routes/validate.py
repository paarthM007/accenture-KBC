"""POST /validate (Phase2-Plan T2.6). The dry run: parses, validates, and
stops — no pipeline, no C1, no C3. Everything here is deterministic and
free, so the user can iterate on their file as many times as they like.
"""

from pydantic import ValidationError

from fastapi import APIRouter, File, Form, UploadFile

from api.models.internal import FormMetadata, InferredMetadata, ValidateResponse
from api.parsing.builder import build_company_input
from api.parsing.ingest import IngestError, ingest_csv

router = APIRouter()


@router.post("/validate", response_model=ValidateResponse)
async def validate(file: UploadFile = File(...), metadata: str = Form(...)) -> ValidateResponse:
    try:
        form_metadata = FormMetadata.model_validate_json(metadata)
    except ValidationError as exc:
        return ValidateResponse(blocking_errors=[f"Invalid company metadata: {exc}"], ready=False)

    file_bytes = await file.read()
    try:
        raw_table = ingest_csv(file_bytes, file.filename or "upload.csv")
    except IngestError as exc:
        return ValidateResponse(blocking_errors=[str(exc)], ready=False)

    result = build_company_input(raw_table, form_metadata)
    company_input = result.company_input

    periods: set[str] = set()
    for metric in company_input.metrics:
        periods.update(dp.period for dp in metric.values)

    ready = (
        not result.blocking_errors
        and all(p.match_type != "unresolved" for p in result.proposals)
        and len(company_input.metrics) > 0
    )

    return ValidateResponse(
        proposals=result.proposals,
        warnings=result.warnings,
        blocking_errors=result.blocking_errors,
        inferred=InferredMetadata(
            granularity=company_input.reporting_period.type.value if company_input.metrics else None,
            periods=len(periods),
            shape=raw_table.detected_shape,
            revenue_band=company_input.company_metadata.revenue_band.value,
        ),
        ready=ready,
    )
