"""API router configuration."""

from fastapi import APIRouter

# Main API router
api_router = APIRouter(prefix="/api/v1")


@api_router.get("/")
async def api_root() -> dict:
    """API root endpoint."""
    return {"message": "Picoclaw API v1"}
