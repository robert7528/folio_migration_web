"""FOLIO batch deletion API endpoints."""

import json
import uuid
from typing import Optional, List
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.database import get_db, SessionLocal
from ..db.models import Client as ClientModel, Execution as ExecutionModel, Deletion as DeletionModel
from ..services.project_service import get_project_service, ProjectService
from ..services.deletion_service import (
    FolioDeletionClient,
    DeletionService,
    get_deletion_service,
)
from ..utils.encryption import decrypt_value

router = APIRouter(prefix="/api/clients/{client_code}/deletion", tags=["deletion"])
settings = get_settings()


# ============================================================
# Pydantic Models
# ============================================================

class StartDeletionRequest(BaseModel):
    """Request to start batch deletion."""
    execution_id: int
    cascade: bool = True  # Delete dependent records (items, holdings) first


class DeletionStatusResponse(BaseModel):
    """Deletion status response."""
    deletion_id: str
    status: str
    execution_id: int
    record_type: Optional[str] = None
    total_records: int = 0
    deleted_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    progress_percent: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None


class DeletionPreviewResponse(BaseModel):
    """Preview of deletion operation."""
    execution_id: int
    task_name: str
    task_type: str
    record_type: str
    total_records: int
    output_file: str
    sample_ids: List[str]


class DeletionListItem(BaseModel):
    """Deletion list item."""
    id: str
    execution_id: int
    record_type: Optional[str]
    status: str
    total_records: int
    deleted_count: int
    failed_count: int
    created_at: datetime


# ============================================================
# Helper Functions
# ============================================================

def get_client_or_404(client_code: str, db: Session) -> ClientModel:
    """Get client by code or raise 404."""
    client = db.query(ClientModel).filter(
        ClientModel.client_code == client_code
    ).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client {client_code} not found")
    return client


def get_folio_credentials(client: ClientModel) -> tuple:
    """Get and decrypt FOLIO credentials."""
    if not client.credentials_set:
        raise HTTPException(
            status_code=400,
            detail="FOLIO credentials not set. Please configure credentials first."
        )

    try:
        username = decrypt_value(client.encrypted_username)
        password = decrypt_value(client.encrypted_password)
        return username, password
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to decrypt credentials: {str(e)}"
        )


# ============================================================
# Background Task
# ============================================================

async def run_deletion(
    deletion_id: str,
    client_code: str,
    execution_id: int,
    cascade: bool,
):
    """Background task to run deletion."""
    db = SessionLocal()
    try:
        # Get client
        client = db.query(ClientModel).filter(
            ClientModel.client_code == client_code
        ).first()
        if not client:
            raise Exception(f"Client {client_code} not found")

        # Get execution
        execution = db.query(ExecutionModel).filter(
            ExecutionModel.id == execution_id,
            ExecutionModel.client_code == client_code,
        ).first()
        if not execution:
            raise Exception(f"Execution {execution_id} not found")

        # Get deletion record
        deletion_record = db.query(DeletionModel).filter(
            DeletionModel.id == deletion_id
        ).first()
        if not deletion_record:
            raise Exception(f"Deletion record {deletion_id} not found")

        # Get credentials
        username = decrypt_value(client.encrypted_username)
        password = decrypt_value(client.encrypted_password)

        # Create FOLIO client
        folio_client = await FolioDeletionClient.create(
            folio_url=client.folio_url,
            tenant_id=client.tenant_id,
            username=username,
            password=password,
        )

        # Get client path
        client_path = Path(settings.clients_base_path) / client_code

        # Run deletion
        service = get_deletion_service(client_path, db)
        await service.delete_execution_records(
            execution=execution,
            folio_client=folio_client,
            deletion_record=deletion_record,
            cascade=cascade,
        )

    except Exception as e:
        # Update deletion record with error
        deletion_record = db.query(DeletionModel).filter(
            DeletionModel.id == deletion_id
        ).first()
        if deletion_record:
            deletion_record.status = "failed"
            deletion_record.error_message = str(e)
            deletion_record.completed_at = datetime.now()
            db.commit()
        raise
    finally:
        db.close()


# ============================================================
# API Endpoints
# ============================================================

@router.get("/list")
async def list_deletions(
    client_code: str,
    db: Session = Depends(get_db),
) -> dict:
    """List all deletion records for a client."""
    client = get_client_or_404(client_code, db)

    deletions = db.query(DeletionModel).filter(
        DeletionModel.client_code == client_code
    ).order_by(DeletionModel.created_at.desc()).all()

    return {
        "deletions": [
            DeletionListItem(
                id=d.id,
                execution_id=d.execution_id,
                record_type=d.record_type,
                status=d.status,
                total_records=d.total_records,
                deleted_count=d.deleted_count,
                failed_count=d.failed_count,
                created_at=d.created_at,
            ).model_dump()
            for d in deletions
        ]
    }


@router.post("/preview")
async def preview_deletion(
    client_code: str,
    request: StartDeletionRequest,
    db: Session = Depends(get_db),
) -> DeletionPreviewResponse:
    """Preview what will be deleted before actually deleting."""
    client = get_client_or_404(client_code, db)

    # Get execution
    execution = db.query(ExecutionModel).filter(
        ExecutionModel.id == request.execution_id,
        ExecutionModel.client_code == client_code,
    ).first()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    if execution.status != "completed":
        raise HTTPException(
            status_code=400,
            detail="Can only delete records from completed executions"
        )

    # Get client path
    client_path = Path(settings.clients_base_path) / client_code

    # Preview deletion
    service = get_deletion_service(client_path, db)
    try:
        preview = await service.preview_deletion(execution)
        return DeletionPreviewResponse(**preview)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/start")
async def start_deletion(
    client_code: str,
    request: StartDeletionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """Start batch deletion of records from FOLIO."""
    client = get_client_or_404(client_code, db)

    # Check credentials
    get_folio_credentials(client)

    # Get execution
    execution = db.query(ExecutionModel).filter(
        ExecutionModel.id == request.execution_id,
        ExecutionModel.client_code == client_code,
    ).first()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    if execution.status != "completed":
        raise HTTPException(
            status_code=400,
            detail="Can only delete records from completed executions"
        )

    # Check if there's already a running deletion for this execution
    existing = db.query(DeletionModel).filter(
        DeletionModel.execution_id == request.execution_id,
        DeletionModel.status == "running",
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Deletion already in progress: {existing.id}"
        )

    # Get record type
    task_type_mapping = {
        "BibsTransformer": "instances",
        "HoldingsTransformer": "holdings",
        "ItemsTransformer": "items",
        "UserTransformer": "users",
        "BibsAndItemsTransformer": "instances",
    }
    record_type = task_type_mapping.get(execution.task_type)

    # Create deletion record
    deletion_id = str(uuid.uuid4())
    deletion = DeletionModel(
        id=deletion_id,
        client_code=client_code,
        execution_id=request.execution_id,
        record_type=record_type,
        status="pending",
        created_at=datetime.now(),
    )
    db.add(deletion)
    db.commit()

    # Start background task
    background_tasks.add_task(
        run_deletion,
        deletion_id=deletion_id,
        client_code=client_code,
        execution_id=request.execution_id,
        cascade=request.cascade,
    )

    return {
        "deletion_id": deletion_id,
        "status": "started",
        "message": f"Deletion started for execution {request.execution_id}",
    }


@router.get("/status/{deletion_id}")
async def get_deletion_status(
    client_code: str,
    deletion_id: str,
    db: Session = Depends(get_db),
) -> DeletionStatusResponse:
    """Get deletion status."""
    client = get_client_or_404(client_code, db)

    deletion = db.query(DeletionModel).filter(
        DeletionModel.id == deletion_id,
        DeletionModel.client_code == client_code,
    ).first()

    if not deletion:
        raise HTTPException(status_code=404, detail="Deletion not found")

    return DeletionStatusResponse(
        deletion_id=deletion.id,
        status=deletion.status,
        execution_id=deletion.execution_id,
        record_type=deletion.record_type,
        total_records=deletion.total_records,
        deleted_count=deletion.deleted_count,
        failed_count=deletion.failed_count,
        skipped_count=deletion.skipped_count,
        progress_percent=deletion.progress_percent,
        started_at=deletion.started_at,
        completed_at=deletion.completed_at,
        duration_seconds=deletion.duration_seconds,
    )


@router.get("/failed/{deletion_id}")
async def get_failed_records(
    client_code: str,
    deletion_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Get list of failed record IDs for a deletion."""
    client = get_client_or_404(client_code, db)

    deletion = db.query(DeletionModel).filter(
        DeletionModel.id == deletion_id,
        DeletionModel.client_code == client_code,
    ).first()

    if not deletion:
        raise HTTPException(status_code=404, detail="Deletion not found")

    failed_ids = []
    if deletion.failed_ids_json:
        try:
            failed_ids = json.loads(deletion.failed_ids_json)
        except json.JSONDecodeError:
            pass

    return {
        "deletion_id": deletion_id,
        "failed_count": deletion.failed_count,
        "failed_records": failed_ids,
    }


@router.delete("/{deletion_id}")
async def delete_deletion_record(
    client_code: str,
    deletion_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Delete a deletion record from history."""
    client = get_client_or_404(client_code, db)

    deletion = db.query(DeletionModel).filter(
        DeletionModel.id == deletion_id,
        DeletionModel.client_code == client_code,
    ).first()

    if not deletion:
        raise HTTPException(status_code=404, detail="Deletion not found")

    if deletion.status == "running":
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a running deletion record"
        )

    db.delete(deletion)
    db.commit()

    return {
        "status": "success",
        "message": f"Deletion record {deletion_id} deleted",
    }
