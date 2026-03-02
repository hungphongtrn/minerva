"""Prometheus metrics endpoint for OSS operator monitoring.

Exposes /metrics at root level using prometheus-fastapi-instrumentator.
"""

from fastapi import APIRouter
from prometheus_fastapi_instrumentator import Instrumentator

router = APIRouter()


def setup_metrics(app) -> None:
    """Setup Prometheus metrics instrumentation on the FastAPI app.

    This should be called during app initialization to enable metrics collection.
    The /metrics endpoint will be exposed at the root level.

    Args:
        app: FastAPI application instance
    """
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@router.get("/metrics/info")
async def metrics_info() -> dict:
    """Info endpoint about metrics availability.

    The actual metrics are exposed at /metrics via the instrumentator.
    This endpoint exists to provide documentation.
    """
    return {
        "endpoint": "/metrics",
        "format": "prometheus",
        "description": "Prometheus metrics for Minerva OSS runtime",
    }
