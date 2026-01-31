"""File management API endpoints."""

import os
from pathlib import Path
from typing import List, Optional

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..config import get_settings
from ..services.project_service import get_project_service, ProjectService

router = APIRouter(prefix="/api/clients/{client_code}/files", tags=["files"])
settings = get_settings()


class FileInfo(BaseModel):
    """File information model."""

    name: str
    path: str
    size: int
    modified: float
    is_dir: bool = False


class FileListResponse(BaseModel):
    """Response model for file listing."""

    client_code: str
    folder: Optional[str]
    files: List[FileInfo]
    total_count: int


class UploadResponse(BaseModel):
    """Response model for file upload."""

    filename: str
    path: str
    size: int


@router.get("", response_model=FileListResponse)
async def list_files(
    client_code: str,
    folder: Optional[str] = None,
    project_service: ProjectService = Depends(get_project_service),
):
    """
    List files in the client project.

    Args:
        folder: Optional subfolder path (e.g., "mapping_files", "iterations/thu_migration/source_data/instances")
    """
    client_path = project_service.get_client_path(client_code)
    if not client_path.exists():
        raise HTTPException(status_code=404, detail="Client directory not found")

    search_path = client_path
    if folder:
        search_path = client_path / folder
        if not search_path.exists():
            raise HTTPException(status_code=404, detail=f"Folder '{folder}' not found")

    files = []
    for item in search_path.iterdir():
        if item.name.startswith("."):
            continue

        stat = item.stat()
        files.append(
            FileInfo(
                name=item.name,
                path=str(item.relative_to(client_path)),
                size=stat.st_size if item.is_file() else 0,
                modified=stat.st_mtime,
                is_dir=item.is_dir(),
            )
        )

    # Sort: directories first, then by name
    files.sort(key=lambda f: (not f.is_dir, f.name.lower()))

    return FileListResponse(
        client_code=client_code,
        folder=folder,
        files=files,
        total_count=len(files),
    )


@router.get("/{file_path:path}")
async def download_file(
    client_code: str,
    file_path: str,
    project_service: ProjectService = Depends(get_project_service),
):
    """Download a file from the client project."""
    client_path = project_service.get_client_path(client_code)
    full_path = client_path / file_path

    # Security check: ensure path is within client directory
    try:
        full_path.resolve().relative_to(client_path.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if not full_path.is_file():
        raise HTTPException(status_code=400, detail="Not a file")

    return FileResponse(
        path=full_path,
        filename=full_path.name,
        media_type="application/octet-stream",
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    client_code: str,
    file: UploadFile = File(...),
    target_folder: str = Form(default="instances"),
    iteration: Optional[str] = Form(default=None),
    project_service: ProjectService = Depends(get_project_service),
):
    """
    Upload a source data file.

    Files are uploaded to: iterations/{iteration}/source_data/{target_folder}/

    Args:
        file: The file to upload
        target_folder: Target subfolder (instances, holdings, items, users, loans, courses, authorities, orders, organizations, requests, reserves, feefines)
        iteration: Iteration name (defaults to {client_code}_migration)
    """
    client_path = project_service.get_client_path(client_code)
    if not client_path.exists():
        raise HTTPException(status_code=404, detail="Client directory not found")

    # Validate file extension
    ext = Path(file.filename).suffix.lower()
    if ext not in settings.allowed_extensions_list:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Allowed types: {settings.allowed_extensions}",
        )

    # Determine target path
    iteration = iteration or f"{client_code}_migration"
    target_path = client_path / "iterations" / iteration / "source_data" / target_folder
    target_path.mkdir(parents=True, exist_ok=True)

    file_path = target_path / file.filename

    # Check file size while streaming
    total_size = 0
    max_size = settings.max_upload_size_bytes

    # Stream upload to disk
    try:
        async with aiofiles.open(file_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                total_size += len(chunk)
                if total_size > max_size:
                    # Clean up and raise error
                    await f.close()
                    os.unlink(file_path)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum size is {settings.max_upload_size_mb}MB",
                    )
                await f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    return UploadResponse(
        filename=file.filename,
        path=str(file_path.relative_to(client_path)),
        size=total_size,
    )


@router.post("/upload-mapping", response_model=UploadResponse)
async def upload_mapping_file(
    client_code: str,
    file: UploadFile = File(...),
    project_service: ProjectService = Depends(get_project_service),
):
    """
    Upload a mapping file.

    Files are uploaded to: mapping_files/
    """
    client_path = project_service.get_client_path(client_code)
    if not client_path.exists():
        raise HTTPException(status_code=404, detail="Client directory not found")

    # Only allow specific extensions for mapping files
    ext = Path(file.filename).suffix.lower()
    if ext not in [".json", ".tsv", ".csv", ".txt"]:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed for mapping files. Use .json, .tsv, .csv, or .txt",
        )

    target_path = client_path / "mapping_files"
    target_path.mkdir(parents=True, exist_ok=True)

    file_path = target_path / file.filename

    # Stream upload
    total_size = 0
    async with aiofiles.open(file_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            total_size += len(chunk)
            await f.write(chunk)

    return UploadResponse(
        filename=file.filename,
        path=str(file_path.relative_to(client_path)),
        size=total_size,
    )


@router.delete("/{file_path:path}")
async def delete_file(
    client_code: str,
    file_path: str,
    project_service: ProjectService = Depends(get_project_service),
):
    """Delete a file from the client project."""
    client_path = project_service.get_client_path(client_code)
    full_path = client_path / file_path

    # Security check
    try:
        full_path.resolve().relative_to(client_path.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Prevent deleting critical files
    protected_files = [".env", "CLIENT_INFO.md", "mapping_files/marc_config.json"]
    rel_path = str(full_path.relative_to(client_path))
    if rel_path in protected_files:
        raise HTTPException(status_code=403, detail="Cannot delete protected file")

    if full_path.is_file():
        os.unlink(full_path)
    else:
        import shutil
        shutil.rmtree(full_path)

    return {"status": "deleted", "path": file_path}
