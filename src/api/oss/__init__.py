"""OSS operator endpoints for Minerva server.

These endpoints are exposed at the root level (without /api/v1 prefix)
for k8s-native health/readiness/metrics checks.
"""

from src.api.oss.router import oss_router

__all__ = ["oss_router"]
