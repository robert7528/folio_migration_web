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
from ..db.models import Client as ClientModel, Execution as ExecutionModel, Validation as ValidationModel
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


class ValidationListItem(BaseModel):
    """Validation list item."""
    id: str
    execution_id: int
    record_type: Optional[str]
    status: str
    total_found: int
    total_not_found: int
    total_mismatches: int
    created_at: datetime


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


@router.get("/list")
async def list_validations(
    client_code: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """List all validations for a client."""
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    query = db.query(ValidationModel).filter(ValidationModel.client_code == client_code)
    total = query.count()
    validations = query.order_by(ValidationModel.created_at.desc()).offset(offset).limit(limit).all()

    def get_error_message(v):
        if v.status == "failed" and v.results_json:
            try:
                data = json.loads(v.results_json)
                if isinstance(data, dict) and "error" in data:
                    return data["error"]
            except:
                pass
        return None

    return {
        "validations": [
            {
                "id": v.id,
                "execution_id": v.execution_id,
                "record_type": v.record_type,
                "status": v.status,
                "total_found": v.total_found_in_folio,
                "total_not_found": v.total_not_found,
                "total_mismatches": v.total_mismatches,
                "created_at": v.created_at,
                "error_message": get_error_message(v),
            }
            for v in validations
        ],
        "total": total,
    }


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

    # Create validation record in database
    validation = ValidationModel(
        id=validation_id,
        client_code=client_code,
        execution_id=request.execution_id,
        status="pending",
        started_at=datetime.now(),
    )
    db.add(validation)
    db.commit()

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
        # Update status to running
        validation = db.query(ValidationModel).filter(ValidationModel.id == validation_id).first()
        if validation:
            validation.status = "running"
            db.commit()

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

        # Save results to database
        validation = db.query(ValidationModel).filter(ValidationModel.id == validation_id).first()
        if validation:
            validation.status = "completed"
            validation.record_type = summary.record_type
            validation.total_local_records = summary.total_local_records
            validation.total_found_in_folio = summary.total_found_in_folio
            validation.total_not_found = summary.total_not_found
            validation.total_mismatches = summary.total_mismatches
            validation.total_errors = summary.total_errors
            validation.completed_at = datetime.now()
            if summary.started_at:
                validation.duration_seconds = (validation.completed_at - summary.started_at).total_seconds()

            # Store results as JSON (only essential fields to save space)
            results_data = [
                {
                    "legacy_id": r.legacy_id,
                    "folio_id": r.folio_id,
                    "hrid": r.hrid,
                    "status": r.status,
                    "differences": r.differences,
                    "error_message": r.error_message,
                }
                for r in summary.results
            ]
            validation.results_json = json.dumps(results_data, ensure_ascii=False)
            db.commit()

    except Exception as e:
        # Update validation with error
        validation = db.query(ValidationModel).filter(ValidationModel.id == validation_id).first()
        if validation:
            validation.status = "failed"
            validation.completed_at = datetime.now()
            validation.total_errors = 1
            # Store error message in results_json
            validation.results_json = json.dumps({"error": str(e)}, ensure_ascii=False)
            db.commit()
        print(f"Validation error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()


@router.get("/status/{validation_id}")
async def get_validation_status(
    client_code: str,
    validation_id: str,
    db: Session = Depends(get_db),
) -> ValidationStatusResponse:
    """Get validation status and summary."""
    validation = db.query(ValidationModel).filter(
        ValidationModel.id == validation_id,
        ValidationModel.client_code == client_code,
    ).first()

    if not validation:
        raise HTTPException(status_code=404, detail="Validation not found")

    progress_percent = 0.0
    if validation.total_local_records > 0:
        progress_percent = (
            (validation.total_found_in_folio + validation.total_not_found +
             validation.total_mismatches + validation.total_errors)
            / validation.total_local_records * 100
        )

    return ValidationStatusResponse(
        validation_id=validation.id,
        status=validation.status,
        execution_id=validation.execution_id,
        record_type=validation.record_type,
        total_local_records=validation.total_local_records,
        total_found_in_folio=validation.total_found_in_folio,
        total_not_found=validation.total_not_found,
        total_mismatches=validation.total_mismatches,
        total_errors=validation.total_errors,
        progress_percent=progress_percent,
        started_at=validation.started_at,
        completed_at=validation.completed_at,
        duration_seconds=validation.duration_seconds,
    )


@router.get("/results/{validation_id}")
async def get_validation_results(
    client_code: str,
    validation_id: str,
    status_filter: Optional[str] = Query(None, description="Filter by status: found, not_found, mismatch, error"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ValidationDetailResponse:
    """Get detailed validation results."""
    validation = db.query(ValidationModel).filter(
        ValidationModel.id == validation_id,
        ValidationModel.client_code == client_code,
    ).first()

    if not validation:
        raise HTTPException(status_code=404, detail="Validation not found")

    # Parse results from JSON
    results = []
    if validation.results_json:
        try:
            results = json.loads(validation.results_json)
        except json.JSONDecodeError:
            pass

    # Filter results
    if status_filter:
        results = [r for r in results if r.get("status") == status_filter]

    # Paginate
    total = len(results)
    results = results[offset:offset + limit]

    return ValidationDetailResponse(
        validation_id=validation.id,
        status=validation.status,
        record_type=validation.record_type or "unknown",
        summary={
            "total_local_records": validation.total_local_records,
            "total_found_in_folio": validation.total_found_in_folio,
            "total_not_found": validation.total_not_found,
            "total_mismatches": validation.total_mismatches,
            "total_errors": validation.total_errors,
            "duration_seconds": validation.duration_seconds,
            "filtered_count": total,
        },
        results=[
            ValidationResultItem(
                legacy_id=r.get("legacy_id", "unknown"),
                folio_id=r.get("folio_id"),
                hrid=r.get("hrid"),
                status=r.get("status", "unknown"),
                differences=r.get("differences", []),
                error_message=r.get("error_message"),
            )
            for r in results
        ],
    )


@router.get("/results/{validation_id}/export")
async def export_validation_report(
    client_code: str,
    validation_id: str,
    format: str = Query("json", description="Export format: json, csv"),
    db: Session = Depends(get_db),
):
    """Export validation report."""
    validation = db.query(ValidationModel).filter(
        ValidationModel.id == validation_id,
        ValidationModel.client_code == client_code,
    ).first()

    if not validation:
        raise HTTPException(status_code=404, detail="Validation not found")

    # Parse results
    results = []
    if validation.results_json:
        try:
            results = json.loads(validation.results_json)
        except json.JSONDecodeError:
            pass

    if format == "json":
        export_data = {
            "validation_id": validation.id,
            "client_code": validation.client_code,
            "execution_id": validation.execution_id,
            "record_type": validation.record_type,
            "status": validation.status,
            "summary": {
                "total_local_records": validation.total_local_records,
                "total_found_in_folio": validation.total_found_in_folio,
                "total_not_found": validation.total_not_found,
                "total_mismatches": validation.total_mismatches,
                "total_errors": validation.total_errors,
                "duration_seconds": validation.duration_seconds,
            },
            "started_at": validation.started_at.isoformat() if validation.started_at else None,
            "completed_at": validation.completed_at.isoformat() if validation.completed_at else None,
            "results": results,
        }
        content = json.dumps(export_data, indent=2, ensure_ascii=False)
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
        for result in results:
            writer.writerow([
                result.get("legacy_id", ""),
                result.get("folio_id", ""),
                result.get("hrid", ""),
                result.get("status", ""),
                json.dumps(result.get("differences", [])) if result.get("differences") else "",
                result.get("error_message", ""),
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
    db: Session = Depends(get_db),
):
    """Get detailed comparison for a specific record."""
    validation = db.query(ValidationModel).filter(
        ValidationModel.id == validation_id,
        ValidationModel.client_code == client_code,
    ).first()

    if not validation:
        raise HTTPException(status_code=404, detail="Validation not found")

    # Parse results
    results = []
    if validation.results_json:
        try:
            results = json.loads(validation.results_json)
        except json.JSONDecodeError:
            pass

    if index < 0 or index >= len(results):
        raise HTTPException(status_code=404, detail="Record index out of range")

    result = results[index]

    return {
        "index": index,
        "legacy_id": result.get("legacy_id"),
        "folio_id": result.get("folio_id"),
        "hrid": result.get("hrid"),
        "status": result.get("status"),
        "local_data": result.get("local_data"),
        "folio_data": result.get("folio_data"),
        "differences": result.get("differences", []),
        "error_message": result.get("error_message"),
    }


@router.delete("/{validation_id}")
async def delete_validation(
    client_code: str,
    validation_id: str,
    db: Session = Depends(get_db),
):
    """Delete a validation record."""
    validation = db.query(ValidationModel).filter(
        ValidationModel.id == validation_id,
        ValidationModel.client_code == client_code,
    ).first()

    if not validation:
        raise HTTPException(status_code=404, detail="Validation not found")

    # Don't allow deleting running validations
    if validation.status == "running":
        raise HTTPException(status_code=400, detail="Cannot delete a running validation")

    db.delete(validation)
    db.commit()

    return {
        "status": "success",
        "message": f"Validation {validation_id} deleted",
    }
