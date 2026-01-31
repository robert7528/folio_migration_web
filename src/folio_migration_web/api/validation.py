"""FOLIO data validation API endpoints."""

import json
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.database import get_db
from ..db.models import Client as ClientModel, Execution as ExecutionModel
from ..services.project_service import get_project_service, ProjectService
from ..services.validation_service import (
    FolioApiClient,
    ValidationService,
    ValidationSummary,
    RecordType,
)
from ..utils.encryption import decrypt_value

router = APIRouter(prefix="/api/clients/{client_code}/validation", tags=["validation"])
settings = get_settings()


# Store validation results in memory (for demo; production should use DB/cache)
_validation_results: dict[str, ValidationSummary] = {}
_validation_status: dict[str, str] = {}  # pending, running, completed, failed


# ============================================================
# Pydantic Models
# ============================================================

class StartValidationRequest(BaseModel):
    """Request to start validation."""
    execution_id: int
    sample_size: Optional[int] = None  # Validate only a sample


class ValidationStatusResponse(BaseModel):
    """Validation status response."""
    validation_id: str
    status: str
    execution_id: int
    record_type: Optional[str] = None
    total_local_records: int = 0
    total_found_in_folio: int = 0
    total_not_found: int = 0
    total_mismatches: int = 0
    total_errors: int = 0
    progress_percent: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None


class ValidationResultItem(BaseModel):
    """Single validation result item."""
    legacy_id: str
    folio_id: Optional[str] = None
    hrid: Optional[str] = None
    status: str
    differences: List[dict] = []
    error_message: Optional[str] = None


class ValidationDetailResponse(BaseModel):
    """Detailed validation results."""
    validation_id: str
    status: str
    record_type: str
    summary: dict
    results: List[ValidationResultItem]


class FolioStatsResponse(BaseModel):
    """FOLIO record count statistics."""
    instances: int = 0
    holdings: int = 0
    items: int = 0
    users: int = 0


# ============================================================
# API Endpoints
# ============================================================

@router.get("/folio-stats")
async def get_folio_stats(
    client_code: str,
    db: Session = Depends(get_db),
) -> FolioStatsResponse:
    """Get record counts from FOLIO platform."""
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    if not client.credentials_set:
        raise HTTPException(status_code=400, detail="FOLIO credentials not configured")

    try:
        # Get credentials
        username = decrypt_value(client.encrypted_username)
        password = decrypt_value(client.encrypted_password)

        # Connect to FOLIO
        folio_client = await FolioApiClient.create(
            client.folio_url,
            client.tenant_id,
            username,
            password,
        )

        # Get counts
        stats = FolioStatsResponse(
            instances=await folio_client.get_record_count(RecordType.INSTANCES),
            holdings=await folio_client.get_record_count(RecordType.HOLDINGS),
            items=await folio_client.get_record_count(RecordType.ITEMS),
            users=await folio_client.get_record_count(RecordType.USERS),
        )

        return stats

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to FOLIO: {str(e)}")


@router.post("/start")
async def start_validation(
    client_code: str,
    request: StartValidationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
):
    """Start validation for an execution."""
    # Verify client
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    if not client.credentials_set:
        raise HTTPException(status_code=400, detail="FOLIO credentials not configured")

    # Verify execution
    execution = db.query(ExecutionModel).filter(
        ExecutionModel.id == request.execution_id,
        ExecutionModel.client_code == client_code,
    ).first()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    if execution.status != "completed":
        raise HTTPException(status_code=400, detail="Can only validate completed executions")

    # Create validation ID
    validation_id = f"{client_code}_{request.execution_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Mark as pending
    _validation_status[validation_id] = "pending"

    # Start validation in background
    background_tasks.add_task(
        run_validation,
        validation_id,
        client_code,
        client.folio_url,
        client.tenant_id,
        client.encrypted_username,
        client.encrypted_password,
        request.execution_id,
        request.sample_size,
        project_service,
    )

    return {
        "validation_id": validation_id,
        "status": "pending",
        "message": "Validation started",
    }


async def run_validation(
    validation_id: str,
    client_code: str,
    folio_url: str,
    tenant_id: str,
    encrypted_username: str,
    encrypted_password: str,
    execution_id: int,
    sample_size: Optional[int],
    project_service: ProjectService,
):
    """Run validation in background."""
    from ..db.database import SessionLocal

    db = SessionLocal()
    try:
        _validation_status[validation_id] = "running"

        # Get credentials
        username = decrypt_value(encrypted_username)
        password = decrypt_value(encrypted_password)

        # Connect to FOLIO
        folio_client = await FolioApiClient.create(folio_url, tenant_id, username, password)

        # Get execution
        execution = db.query(ExecutionModel).filter(ExecutionModel.id == execution_id).first()
        if not execution:
            raise Exception("Execution not found")

        # Get client path
        client_path = project_service.get_client_path(client_code)

        # Run validation
        validation_service = ValidationService(client_path, db)
        summary = await validation_service.validate_execution(
            execution,
            folio_client,
            sample_size,
        )

        # Store results
        _validation_results[validation_id] = summary
        _validation_status[validation_id] = "completed"

    except Exception as e:
        _validation_status[validation_id] = "failed"
        # Store error as empty summary
        _validation_results[validation_id] = ValidationSummary(
            record_type="unknown",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        _validation_results[validation_id].total_errors = 1
        print(f"Validation error: {e}")

    finally:
        db.close()


@router.get("/status/{validation_id}")
async def get_validation_status(
    client_code: str,
    validation_id: str,
) -> ValidationStatusResponse:
    """Get validation status and summary."""
    status = _validation_status.get(validation_id)
    if not status:
        raise HTTPException(status_code=404, detail="Validation not found")

    # Extract execution_id from validation_id
    parts = validation_id.split("_")
    execution_id = int(parts[1]) if len(parts) > 1 else 0

    response = ValidationStatusResponse(
        validation_id=validation_id,
        status=status,
        execution_id=execution_id,
    )

    # Add summary if available
    summary = _validation_results.get(validation_id)
    if summary:
        response.record_type = summary.record_type
        response.total_local_records = summary.total_local_records
        response.total_found_in_folio = summary.total_found_in_folio
        response.total_not_found = summary.total_not_found
        response.total_mismatches = summary.total_mismatches
        response.total_errors = summary.total_errors
        response.started_at = summary.started_at
        response.completed_at = summary.completed_at
        response.duration_seconds = summary.duration_seconds

        if summary.total_local_records > 0:
            response.progress_percent = (
                (summary.total_found_in_folio + summary.total_not_found +
                 summary.total_mismatches + summary.total_errors)
                / summary.total_local_records * 100
            )

    return response


@router.get("/results/{validation_id}")
async def get_validation_results(
    client_code: str,
    validation_id: str,
    status_filter: Optional[str] = Query(None, description="Filter by status: found, not_found, mismatch, error"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> ValidationDetailResponse:
    """Get detailed validation results."""
    validation_status = _validation_status.get(validation_id)
    if not validation_status:
        raise HTTPException(status_code=404, detail="Validation not found")

    summary = _validation_results.get(validation_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Validation results not available")

    # Filter results
    results = summary.results
    if status_filter:
        results = [r for r in results if r.status == status_filter]

    # Paginate
    total = len(results)
    results = results[offset:offset + limit]

    return ValidationDetailResponse(
        validation_id=validation_id,
        status=validation_status,
        record_type=summary.record_type,
        summary={
            "total_local_records": summary.total_local_records,
            "total_found_in_folio": summary.total_found_in_folio,
            "total_not_found": summary.total_not_found,
            "total_mismatches": summary.total_mismatches,
            "total_errors": summary.total_errors,
            "duration_seconds": summary.duration_seconds,
            "filtered_count": total,
        },
        results=[
            ValidationResultItem(
                legacy_id=r.legacy_id,
                folio_id=r.folio_id,
                hrid=r.hrid,
                status=r.status,
                differences=r.differences,
                error_message=r.error_message,
            )
            for r in results
        ],
    )


@router.get("/results/{validation_id}/export")
async def export_validation_report(
    client_code: str,
    validation_id: str,
    format: str = Query("json", description="Export format: json, csv"),
):
    """Export validation report."""
    summary = _validation_results.get(validation_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Validation results not available")

    if format == "json":
        content = json.dumps(summary.to_dict(), indent=2, ensure_ascii=False)
        return StreamingResponse(
            iter([content]),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=validation_{validation_id}.json"
            },
        )

    elif format == "csv":
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "legacy_id", "folio_id", "hrid", "status",
            "differences", "error_message"
        ])

        # Data
        for result in summary.results:
            writer.writerow([
                result.legacy_id,
                result.folio_id or "",
                result.hrid or "",
                result.status,
                json.dumps(result.differences) if result.differences else "",
                result.error_message or "",
            ])

        content = output.getvalue()
        return StreamingResponse(
            iter([content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=validation_{validation_id}.csv"
            },
        )

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")


@router.get("/record/{validation_id}/{index}")
async def get_validation_record_detail(
    client_code: str,
    validation_id: str,
    index: int,
):
    """Get detailed comparison for a specific record."""
    summary = _validation_results.get(validation_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Validation results not available")

    if index < 0 or index >= len(summary.results):
        raise HTTPException(status_code=404, detail="Record index out of range")

    result = summary.results[index]

    return {
        "index": index,
        "legacy_id": result.legacy_id,
        "folio_id": result.folio_id,
        "hrid": result.hrid,
        "status": result.status,
        "local_data": result.local_data,
        "folio_data": result.folio_data,
        "differences": result.differences,
        "error_message": result.error_message,
    }
