"""Data conversion API endpoints."""

import os
import tempfile
from pathlib import Path

import aiofiles
from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from ..services.conversion_service import ConversionService, CONVERSION_TYPES

router = APIRouter(
    prefix="/api/clients/{client_code}/convert",
    tags=["conversion"],
)


@router.get("/types")
async def get_conversion_types(client_code: str):
    """Get available conversion types and their status."""
    service = ConversionService(client_code)
    keepsite_info = service.check_keepsite_mapping()

    types = []
    for key, type_def in CONVERSION_TYPES.items():
        info = {
            "key": key,
            "label": type_def["label"],
            "accept": type_def["accept"],
            "needs_keepsite": type_def["needs_keepsite"],
            "multi_file": type_def.get("multi_file", False),
        }
        if type_def["needs_keepsite"]:
            info["keepsite_available"] = keepsite_info["exists"]
            info["keepsite_count"] = keepsite_info["count"]
        types.append(info)

    return {"types": types, "keepsite": keepsite_info}


@router.get("/iterations")
async def get_iterations(client_code: str):
    """Get available iterations for this client."""
    service = ConversionService(client_code)
    iterations = service.get_iterations()
    return {"iterations": iterations}


@router.post("")
async def convert_file(
    client_code: str,
    conversion_type: str = Form(...),
    iteration: str = Form(...),
    files: list[UploadFile] = File(...),
):
    """Convert one or more uploaded source files.

    Accepts HyLib CSV or MARC file(s), runs the appropriate conversion tool, and
    saves the output to the correct source_data subdirectory. Most conversion
    types take a single file; multi-file types (e.g. holdings_csv) merge all
    uploaded files into one output set.
    """
    if conversion_type not in CONVERSION_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown conversion type: {conversion_type}")

    if not files:
        raise HTTPException(status_code=400, detail="No file uploaded")

    service = ConversionService(client_code)

    # Verify iteration exists
    iterations = service.get_iterations()
    if iteration not in iterations:
        raise HTTPException(status_code=404, detail=f"Iteration '{iteration}' not found")

    # Save uploaded files to temp locations
    tmp_paths: list[str] = []
    total_size = 0
    try:
        for upload in files:
            suffix = Path(upload.filename).suffix if upload.filename else ".csv"
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
            os.close(tmp_fd)
            async with aiofiles.open(tmp_path, "wb") as f:
                content = await upload.read()
                await f.write(content)
            tmp_paths.append(tmp_path)
            total_size += len(content)

        # Run conversion (pass a list; single-file types use the first path)
        result = service.convert(iteration, conversion_type, tmp_paths)

        # Add source file info
        result["source_filename"] = ", ".join(u.filename or "" for u in files)
        result["source_size"] = total_size

        return result
    finally:
        # Clean up temp files
        for p in tmp_paths:
            try:
                os.unlink(p)
            except OSError:
                pass
