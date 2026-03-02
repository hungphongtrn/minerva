"""Picoclaw FastAPI application entry point."""

from fastapi import FastAPI

from src.api.router import api_router
from src.api.oss.router import oss_router
from src.api.oss.routes.metrics import setup_metrics
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

    # Register OSS operator endpoints (root level, no /api/v1 prefix)
    # These include /health, /ready, and /metrics/info
    app.include_router(oss_router)

    # Register API routes (with /api/v1 prefix)
    app.include_router(api_router)

    # Setup Prometheus metrics instrumentation
    # This exposes /metrics endpoint at root level
    setup_metrics(app)

    return app


# Global app instance for ASGI servers
app = create_app()
