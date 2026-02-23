"""API dependencies for authentication and authorization."""

from src.api.dependencies.auth import (
    resolve_principal,
    optional_principal,
    require_scopes,
    security,
)

__all__ = ["resolve_principal", "optional_principal", "require_scopes", "security"]
