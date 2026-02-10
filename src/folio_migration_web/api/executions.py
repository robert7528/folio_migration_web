"""Task execution API endpoints."""

import json
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.database import get_db
from ..db.models import Client as ClientModel, Execution as ExecutionModel
from ..services.project_service import get_project_service, ProjectService
from ..services.execution_service import get_execution_service, _running_executions
from ..services.validation_service import FolioApiClient, RecordType
from ..utils.encryption import decrypt_value

router = APIRouter(prefix="/api/clients/{client_code}/executions", tags=["executions"])
settings = get_settings()


# ============================================================
# Pydantic Models
# ============================================================

class TaskInfo(BaseModel):
    """Available task information."""
    name: str
    type: str
    files: list


class StartExecutionRequest(BaseModel):
    """Request to start task execution."""
    task_name: str
    iteration: str
    use_stored_password: bool = True
    password: Optional[str] = None


class ExecutionResponse(BaseModel):
    """Execution record response."""
    id: int
    client_code: str
    task_name: str
    task_type: str
    iteration: str
    status: str
    total_records: int
    processed_records: int
    success_count: int
    error_count: int
    merged_count: int = 0  # Records merged/deduplicated
    progress_percent: float
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    log_file: Optional[str]
    error_message: Optional[str]
    pre_execution_count: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ExecutionListResponse(BaseModel):
    """List of executions response."""
    executions: List[ExecutionResponse]
    total: int


# ============================================================
# API Endpoints
# ============================================================

@router.get("/tasks")
async def get_available_tasks(
    client_code: str,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
):
    """Get list of tasks that can be executed."""
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    client_path = project_service.get_client_path(client_code)
    if not client_path.exists():
        raise HTTPException(status_code=404, detail="Client directory not found")

    execution_service = get_execution_service(client_path, db)
    tasks = execution_service.get_available_tasks()

    return {"tasks": tasks}


@router.post("", response_model=ExecutionResponse)
async def start_execution(
    client_code: str,
    request: StartExecutionRequest,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
):
    """Start a new task execution."""
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    client_path = project_service.get_client_path(client_code)
    if not client_path.exists():
        raise HTTPException(status_code=404, detail="Client directory not found")

    # Get password
    if request.use_stored_password:
        if not client.credentials_set or not client.encrypted_password:
            raise HTTPException(
                status_code=400,
                detail="No stored credentials. Please set credentials first or provide password."
            )
        password = decrypt_value(client.encrypted_password)
    else:
        if not request.password:
            raise HTTPException(status_code=400, detail="Password is required")
        password = request.password

    # Get execution service
    execution_service = get_execution_service(client_path, db)

    # Verify task exists
    available_tasks = execution_service.get_available_tasks()
    task = next((t for t in available_tasks if t["name"] == request.task_name), None)
    if not task:
        raise HTTPException(
            status_code=400,
            detail=f"Task '{request.task_name}' not found in migration_config.json"
        )

    # Create execution record
    execution = execution_service.create_execution(
        client_code=client_code,
        task_name=request.task_name,
        task_type=task["type"],
        iteration=request.iteration,
    )

    # For BatchPoster tasks, capture pre-execution FOLIO record count
    if task["type"] == "BatchPoster" and client.credentials_set:
        try:
            username = decrypt_value(client.encrypted_username)
            folio_client = await FolioApiClient.create(
                client.folio_url, client.tenant_id, username, password,
            )
            # Determine record type from task name
            record_type = _get_record_type_from_task_name(request.task_name)
            if record_type:
                pre_count = await folio_client.get_record_count(record_type)
                execution.pre_execution_count = pre_count
                db.commit()
        except Exception:
            pass  # Non-critical: count validation will be unavailable

    # Start execution
    success = execution_service.start_execution(execution, password)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to start execution")

    return execution


def _get_record_type_from_task_name(task_name: str) -> Optional[RecordType]:
    """Determine FOLIO record type from BatchPoster task name."""
    name_lower = task_name.lower()
    if "instance" in name_lower or "bib" in name_lower:
        return RecordType.INSTANCES
    elif "holding" in name_lower:
        return RecordType.HOLDINGS
    elif "item" in name_lower:
        return RecordType.ITEMS
    elif "user" in name_lower:
        return RecordType.USERS
    return None


@router.get("", response_model=ExecutionListResponse)
async def list_executions(
    client_code: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List execution history for a client."""
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    query = db.query(ExecutionModel).filter(ExecutionModel.client_code == client_code)

    if status:
        query = query.filter(ExecutionModel.status == status)

    total = query.count()
    executions = query.order_by(ExecutionModel.created_at.desc()).offset(offset).limit(limit).all()

    return ExecutionListResponse(
        executions=[ExecutionResponse.model_validate(e) for e in executions],
        total=total,
    )


@router.get("/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    client_code: str,
    execution_id: int,
    db: Session = Depends(get_db),
):
    """Get execution details."""
    execution = db.query(ExecutionModel).filter(
        ExecutionModel.id == execution_id,
        ExecutionModel.client_code == client_code,
    ).first()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    return execution


@router.get("/{execution_id}/logs")
async def get_execution_logs(
    client_code: str,
    execution_id: int,
    offset: int = Query(0, ge=0, description="Line offset"),
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
):
    """Get logs for an execution."""
    execution = db.query(ExecutionModel).filter(
        ExecutionModel.id == execution_id,
        ExecutionModel.client_code == client_code,
    ).first()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    client_path = project_service.get_client_path(client_code)
    execution_service = get_execution_service(client_path, db)

    # If running, get live logs
    if execution_service.is_running(execution_id):
        lines = execution_service.get_execution_logs(execution_id, offset)
        return {
            "lines": lines,
            "total": offset + len(lines),
            "is_running": True,
        }

    # Otherwise, read from log file
    if execution.log_file:
        log_path = client_path / execution.log_file
        if log_path.exists():
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    all_lines = f.readlines()
                    lines = [line.rstrip() for line in all_lines[offset:]]
                    return {
                        "lines": lines,
                        "total": len(all_lines),
                        "is_running": False,
                    }
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error reading log file: {e}")

    return {"lines": [], "total": 0, "is_running": False}


@router.post("/{execution_id}/cancel")
async def cancel_execution(
    client_code: str,
    execution_id: int,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
):
    """Cancel a running execution."""
    execution = db.query(ExecutionModel).filter(
        ExecutionModel.id == execution_id,
        ExecutionModel.client_code == client_code,
    ).first()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    if execution.status != "running":
        raise HTTPException(status_code=400, detail="Execution is not running")

    client_path = project_service.get_client_path(client_code)
    execution_service = get_execution_service(client_path, db)

    success = execution_service.cancel_execution(execution_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to cancel execution")

    return {"status": "success", "message": "Execution cancelled"}


@router.get("/{execution_id}/results")
async def get_execution_results(
    client_code: str,
    execution_id: int,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
):
    """Get execution results including output files."""
    execution = db.query(ExecutionModel).filter(
        ExecutionModel.id == execution_id,
        ExecutionModel.client_code == client_code,
    ).first()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    if execution.status not in ("completed", "failed"):
        return {
            "status": execution.status,
            "message": "Execution not yet completed",
            "results": None,
        }

    client_path = project_service.get_client_path(client_code)
    iteration_path = client_path / "iterations" / execution.iteration

    output_files = []

    # Find result files in results folder
    results_path = iteration_path / "results"
    if results_path.exists():
        for f in results_path.iterdir():
            if f.is_file() and execution.task_name in f.name:
                output_files.append({
                    "name": f.name,
                    "path": str(f.relative_to(client_path)),
                    "size": f.stat().st_size,
                    "type": "result",
                })

    # Find report files in reports folder
    reports_path = iteration_path / "reports"
    if reports_path.exists():
        for f in reports_path.iterdir():
            if f.is_file() and execution.task_name in f.name:
                output_files.append({
                    "name": f.name,
                    "path": str(f.relative_to(client_path)),
                    "size": f.stat().st_size,
                    "type": "report",
                })

    # Sort by type (reports first) then name
    output_files.sort(key=lambda x: (x["type"] != "report", x["name"]))

    # Parse result summary if available
    summary = None
    if execution.result_summary:
        try:
            summary = json.loads(execution.result_summary)
        except Exception:
            pass

    return {
        "status": execution.status,
        "task_name": execution.task_name,
        "task_type": execution.task_type,
        "statistics": {
            "total_records": execution.total_records,
            "processed_records": execution.processed_records,
            "success_count": execution.success_count,
            "error_count": execution.error_count,
            "merged_count": execution.merged_count or 0,
            "duration_seconds": execution.duration_seconds,
        },
        "summary": summary,
        "output_files": output_files,
        "error_message": execution.error_message,
    }
