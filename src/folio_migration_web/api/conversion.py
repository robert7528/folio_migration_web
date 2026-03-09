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
    file: UploadFile = File(...),
):
    """Convert an uploaded source file.

    Accepts a HyLib CSV or MARC file, runs the appropriate conversion tool,
    and saves the output to the correct source_data subdirectory.
    """
    if conversion_type not in CONVERSION_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown conversion type: {conversion_type}")

    service = ConversionService(client_code)

    # Verify iteration exists
    iterations = service.get_iterations()
    if iteration not in iterations:
        raise HTTPException(status_code=404, detail=f"Iteration '{iteration}' not found")

    # Save uploaded file to temp location
    suffix = Path(file.filename).suffix if file.filename else ".csv"
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        async with aiofiles.open(tmp_path, "wb") as f:
            content = await file.read()
            await f.write(content)

        # Run conversion
        result = service.convert(iteration, conversion_type, tmp_path)

        # Add source file info
        result["source_filename"] = file.filename
        result["source_size"] = len(content)

        return result
    finally:
        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
