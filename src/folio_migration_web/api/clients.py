"""Client management API endpoints."""

from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.database import get_db
from ..db.models import Client as ClientModel
from ..models.client import ClientCreate, ClientResponse, ClientListItem
from ..services.project_service import get_project_service, ProjectService
from ..services.folder_service import get_iteration_folders, get_source_data_folders

router = APIRouter(prefix="/api/clients", tags=["clients"])
settings = get_settings()


@router.get("", response_model=List[ClientListItem])
async def list_clients(db: Session = Depends(get_db)):
    """List all client projects."""
    clients = db.query(ClientModel).order_by(ClientModel.created_at.desc()).all()
    return clients


@router.get("/{client_code}", response_model=ClientResponse)
async def get_client(client_code: str, db: Session = Depends(get_db)):
    """Get a specific client project."""
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")
    return client


@router.post("", response_model=ClientResponse)
async def create_client(
    client: ClientCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
):
    """
    Create a new client migration project.

    This will:
    1. Create a database record
    2. Clone the migration template
    3. Initialize the project structure
    4. Set up virtual environment and install tools
    """
    # Check if client already exists in DB
    existing = db.query(ClientModel).filter(ClientModel.client_code == client.client_code).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Client '{client.client_code}' already exists",
        )

    # Check if directory already exists
    if project_service.client_exists(client.client_code):
        raise HTTPException(
            status_code=400,
            detail=f"Client directory '{client.client_code}' already exists on disk",
        )

    # Create database record first
    db_client = ClientModel(
        client_code=client.client_code,
        client_name=client.client_name,
        client_type=client.client_type.value,
        folio_url=client.folio_url,
        tenant_id=client.tenant_id,
        pm_name=client.pm_name,
        start_date=client.start_date or date.today(),
        status="initializing",
    )
    db.add(db_client)
    db.commit()
    db.refresh(db_client)

    # Create project in background
    background_tasks.add_task(
        _create_project_async,
        client,
        db_client.client_code,
    )

    return db_client


async def _create_project_async(client: ClientCreate, client_code: str):
    """Background task to create project."""
    from ..db.database import SessionLocal

    db = SessionLocal()
    project_service = get_project_service()

    try:
        # Create the project (this may take a while due to venv creation)
        result = project_service.create_project(client, skip_venv=False, skip_git_clone=False)

        # Update database record
        db_client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
        if db_client:
            if result["status"] == "success":
                db_client.status = "ready"
                db_client.tool_version = result.get("tool_version")
                db_client.python_version = result.get("python_version")
            else:
                db_client.status = "error"
                db_client.status_message = result.get("error", "Unknown error")
            db.commit()

    except Exception as e:
        # Update status to error
        db_client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
        if db_client:
            db_client.status = "error"
            db_client.status_message = str(e)
            db.commit()
    finally:
        db.close()


@router.delete("/{client_code}")
async def delete_client(
    client_code: str,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
):
    """Delete a client project."""
    # Check if exists
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    # Delete from filesystem
    project_service.delete_project(client_code)

    # Delete from database
    db.delete(client)
    db.commit()

    return {"status": "deleted", "client_code": client_code}


@router.get("/{client_code}/iterations")
async def get_iterations(
    client_code: str,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
):
    """Get iterations for a client project."""
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    client_path = project_service.get_client_path(client_code)
    if not client_path.exists():
        raise HTTPException(status_code=404, detail="Client directory not found")

    iterations = get_iteration_folders(client_path)

    return {
        "client_code": client_code,
        "iterations": iterations,
    }


@router.get("/{client_code}/iterations/{iteration}/source_data")
async def get_source_data_info(
    client_code: str,
    iteration: str,
    project_service: ProjectService = Depends(get_project_service),
):
    """Get source data folder information for an iteration."""
    client_path = project_service.get_client_path(client_code)
    if not client_path.exists():
        raise HTTPException(status_code=404, detail="Client directory not found")

    folders = get_source_data_folders(client_path, iteration)

    return {
        "client_code": client_code,
        "iteration": iteration,
        "folders": folders,
    }
