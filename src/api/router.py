"""API router configuration."""

from fastapi import APIRouter

from src.api.routes import (
    api_keys,
    whoami,
    workspace_resources,
    runs,
    workspaces,
    agent_packs,
)

# Main API router
api_router = APIRouter(prefix="/api/v1")

# Register routes
api_router.include_router(api_keys.router)
api_router.include_router(whoami.router)
api_router.include_router(workspace_resources.router)
api_router.include_router(workspaces.router)
api_router.include_router(agent_packs.router)
api_router.include_router(runs.router)


@api_router.get("/")
async def api_root() -> dict:
    """API root endpoint."""
    return {
        "message": "Picoclaw API v1",
        "endpoints": {"api_keys": "/api/v1/api-keys", "whoami": "/api/v1/whoami"},
    }
