"""Health check API endpoint."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str


@router.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for monitoring."""
    from .. import __version__

    return HealthResponse(
        status="healthy",
        version=__version__,
    )
