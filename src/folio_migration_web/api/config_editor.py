"""Configuration file editor API."""

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError

from ..models.config import MigrationConfig, ConfigValidationResult
from ..services.project_service import get_project_service, ProjectService

router = APIRouter(prefix="/api/clients/{client_code}/config", tags=["config"])


class ConfigFileInfo(BaseModel):
    """Configuration file information."""

    filename: str
    path: str
    size: int


class ConfigContent(BaseModel):
    """Configuration file content."""

    filename: str
    content: Dict[str, Any]


class ConfigListResponse(BaseModel):
    """Response model for listing config files."""

    client_code: str
    files: List[ConfigFileInfo]


@router.get("", response_model=ConfigListResponse)
async def list_config_files(
    client_code: str,
    project_service: ProjectService = Depends(get_project_service),
):
    """List configuration files in the mapping_files directory."""
    client_path = project_service.get_client_path(client_code)
    mapping_path = client_path / "mapping_files"

    if not mapping_path.exists():
        raise HTTPException(status_code=404, detail="mapping_files directory not found")

    files = []
    for item in mapping_path.iterdir():
        if item.is_file() and item.suffix == ".json":
            stat = item.stat()
            files.append(
                ConfigFileInfo(
                    filename=item.name,
                    path=str(item.relative_to(client_path)),
                    size=stat.st_size,
                )
            )

    files.sort(key=lambda f: f.filename)

    return ConfigListResponse(client_code=client_code, files=files)


@router.get("/{filename}", response_model=ConfigContent)
async def get_config(
    client_code: str,
    filename: str,
    project_service: ProjectService = Depends(get_project_service),
):
    """Get configuration file content."""
    client_path = project_service.get_client_path(client_code)
    config_path = client_path / "mapping_files" / filename

    # Security check
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=403, detail="Invalid filename")

    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"Config file '{filename}' not found")

    if config_path.suffix != ".json":
        raise HTTPException(status_code=400, detail="Only JSON files are supported")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = json.load(f)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")

    return ConfigContent(filename=filename, content=content)


@router.put("/{filename}")
async def update_config(
    client_code: str,
    filename: str,
    content: Dict[str, Any],
    project_service: ProjectService = Depends(get_project_service),
):
    """Update configuration file."""
    client_path = project_service.get_client_path(client_code)
    config_path = client_path / "mapping_files" / filename

    # Security check
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=403, detail="Invalid filename")

    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"Config file '{filename}' not found")

    # Validate the content if it's a migration config
    if "libraryInformation" in content and "migrationTasks" in content:
        try:
            MigrationConfig(**content)
        except ValidationError as e:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Configuration validation failed",
                    "errors": e.errors(),
                },
            )

    # Write the file
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=4, ensure_ascii=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write file: {str(e)}")

    return {"status": "updated", "filename": filename}


@router.post("/{filename}")
async def create_config(
    client_code: str,
    filename: str,
    content: Dict[str, Any],
    project_service: ProjectService = Depends(get_project_service),
):
    """Create a new configuration file."""
    client_path = project_service.get_client_path(client_code)
    mapping_path = client_path / "mapping_files"
    config_path = mapping_path / filename

    # Security check
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=403, detail="Invalid filename")

    if not filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Filename must end with .json")

    if config_path.exists():
        raise HTTPException(status_code=400, detail=f"Config file '{filename}' already exists")

    # Ensure directory exists
    mapping_path.mkdir(parents=True, exist_ok=True)

    # Write the file
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=4, ensure_ascii=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create file: {str(e)}")

    return {"status": "created", "filename": filename}


@router.post("/validate", response_model=ConfigValidationResult)
async def validate_config(content: Dict[str, Any]):
    """Validate configuration content without saving."""
    try:
        config = MigrationConfig(**content)
        return ConfigValidationResult(
            valid=True,
            parsed=config.model_dump(by_alias=True),
        )
    except ValidationError as e:
        return ConfigValidationResult(
            valid=False,
            errors=e.errors(),
        )


@router.delete("/{filename}")
async def delete_config(
    client_code: str,
    filename: str,
    project_service: ProjectService = Depends(get_project_service),
):
    """Delete a configuration file."""
    client_path = project_service.get_client_path(client_code)
    config_path = client_path / "mapping_files" / filename

    # Security check
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=403, detail="Invalid filename")

    # Protect the main config file
    if filename == "marc_config.json":
        raise HTTPException(status_code=403, detail="Cannot delete the main configuration file")

    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"Config file '{filename}' not found")

    config_path.unlink()

    return {"status": "deleted", "filename": filename}
