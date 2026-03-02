"""OSS router configuration for operator endpoints.

These endpoints are mounted at the root level without /api/v1 prefix:
- /health - Component health status (always 200)
- /ready - Readiness check (200 if ready, 503 if not)
- /metrics - Prometheus metrics
"""

from fastapi import APIRouter

from src.api.oss.routes import health, metrics

# OSS router - no prefix, mounted at root
oss_router = APIRouter()

# Register OSS routes
oss_router.include_router(health.router)
oss_router.include_router(metrics.router)
