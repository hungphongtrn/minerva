"""Picoclaw FastAPI application entry point."""

from fastapi import FastAPI

from src.api.router import api_router
from src.config.settings import settings


def create_app() -> FastAPI:
    """Application factory for Picoclaw API."""
    app = FastAPI(
        title="Picoclaw API",
        description="Multi-tenant OSS runtime for agent packs",
        version="0.1.0",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )

    # Register API routes
    app.include_router(api_router)

    @app.get("/health")
    async def health_check() -> dict:
        """Health check endpoint."""
        return {"status": "healthy"}

    return app


# Global app instance for ASGI servers
app = create_app()
