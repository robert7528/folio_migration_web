"""Task configuration management API."""

from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.database import get_db
from ..db.models import Client as ClientModel
from ..services.project_service import get_project_service, ProjectService
from ..services.config_service import get_config_service, TASK_DEFINITIONS

router = APIRouter(prefix="/api/clients/{client_code}/tasks", tags=["tasks"])
settings = get_settings()


class TaskInfo(BaseModel):
    """Task type information."""
    task_type: str
    name: str
    enabled: bool
    has_config: bool
    required_mappings: List[str]
    optional_mappings: List[str]


class TaskConfigUpdate(BaseModel):
    """Task configuration update."""
    enabled: Optional[bool] = None
    config: Optional[dict] = None


# ============================================================
# Static routes MUST come before dynamic /{task_type} routes
# ============================================================

@router.get("")
async def list_tasks(
    client_code: str,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
):
    """List all available task types and their status."""
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    client_path = project_service.get_client_path(client_code)
    if not client_path.exists():
        raise HTTPException(status_code=404, detail="Client directory not found")

    config_service = get_config_service(client_path)
    tasks = {}

    for task_type, task_def in TASK_DEFINITIONS.items():
        task_config = config_service.get_task_config(task_type)
        # Get transformer or migrator name
        handler = task_def.get("transformer") or task_def.get("migrator", "")
        tasks[task_type] = {
            "name": task_def["name"],
            "transformer": handler,
            "enabled": task_config.get("enabled", False) if task_config else False,
            "has_config": task_config is not None,
            "required_mappings": task_def.get("required_mappings", []),
            "optional_mappings": task_def.get("optional_mappings", []),
        }

    return {"tasks": tasks}


@router.get("/mappings/list")
async def list_mapping_files(
    client_code: str,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
):
    """List all mapping files for a client."""
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    client_path = project_service.get_client_path(client_code)
    if not client_path.exists():
        raise HTTPException(status_code=404, detail="Client directory not found")

    mapping_dir = client_path / "mapping_files"
    mappings = []

    if mapping_dir.exists():
        # List mapping files from mapping_files/ directly
        for f in mapping_dir.iterdir():
            if f.is_file() and f.suffix in [".json", ".tsv", ".csv", ".txt"]:
                # Skip config files (task configs, library_config, migration_config)
                if (f.name.endswith("_config.json") or
                    f.name == "library_config.json" or
                    f.name == "migration_config.json"):
                    continue
                mappings.append({
                    "filename": f.name,
                    "size": f.stat().st_size,
                })

    return {
        "client_code": client_code,
        "mappings": sorted(mappings, key=lambda x: x["filename"]),
    }


@router.post("/generate-combined")
async def generate_combined_config(
    client_code: str,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
):
    """Generate the combined migration configuration file."""
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    client_path = project_service.get_client_path(client_code)
    if not client_path.exists():
        raise HTTPException(status_code=404, detail="Client directory not found")

    config_service = get_config_service(client_path)
    combined = config_service.generate_combined_config()

    enabled_tasks = [t["name"] for t in combined.get("migrationTasks", [])]

    return {
        "status": "success",
        "message": "Combined configuration generated",
        "filename": "migration_config.json",
        "enabled_tasks": enabled_tasks,
    }


# ============================================================
# Dynamic /{task_type} routes come AFTER static routes
# ============================================================

@router.get("/{task_type}")
async def get_task_config(
    client_code: str,
    task_type: str,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
):
    """Get configuration for a specific task type."""
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    if task_type not in TASK_DEFINITIONS:
        raise HTTPException(status_code=400, detail=f"Unknown task type: {task_type}")

    client_path = project_service.get_client_path(client_code)
    if not client_path.exists():
        raise HTTPException(status_code=404, detail="Client directory not found")

    config_service = get_config_service(client_path)
    config = config_service.get_task_config(task_type)

    if not config:
        # Generate the config if it doesn't exist
        config = config_service.generate_task_config(task_type)

    return {
        "task_type": task_type,
        "name": TASK_DEFINITIONS[task_type]["name"],
        "config": config,
    }


@router.put("/{task_type}")
async def update_task_config(
    client_code: str,
    task_type: str,
    update: TaskConfigUpdate,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
):
    """Update configuration for a specific task type."""
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    if task_type not in TASK_DEFINITIONS:
        raise HTTPException(status_code=400, detail=f"Unknown task type: {task_type}")

    client_path = project_service.get_client_path(client_code)
    if not client_path.exists():
        raise HTTPException(status_code=404, detail="Client directory not found")

    config_service = get_config_service(client_path)

    if update.enabled is not None:
        config_service.enable_task(task_type, update.enabled)

    if update.config is not None:
        config_service.update_task_config(task_type, update.config)

    config = config_service.get_task_config(task_type)

    return {
        "status": "success",
        "message": f"Task '{task_type}' updated",
        "config": config,
    }


@router.post("/{task_type}/enable")
async def enable_task(
    client_code: str,
    task_type: str,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
):
    """Enable a task type."""
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    if task_type not in TASK_DEFINITIONS:
        raise HTTPException(status_code=400, detail=f"Unknown task type: {task_type}")

    client_path = project_service.get_client_path(client_code)
    if not client_path.exists():
        raise HTTPException(status_code=404, detail="Client directory not found")

    config_service = get_config_service(client_path)
    config_service.enable_task(task_type, True)

    return {"status": "success", "message": f"Task '{task_type}' enabled"}


@router.post("/{task_type}/disable")
async def disable_task(
    client_code: str,
    task_type: str,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
):
    """Disable a task type."""
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    if task_type not in TASK_DEFINITIONS:
        raise HTTPException(status_code=400, detail=f"Unknown task type: {task_type}")

    client_path = project_service.get_client_path(client_code)
    if not client_path.exists():
        raise HTTPException(status_code=404, detail="Client directory not found")

    config_service = get_config_service(client_path)
    config_service.enable_task(task_type, False)

    return {"status": "success", "message": f"Task '{task_type}' disabled"}
