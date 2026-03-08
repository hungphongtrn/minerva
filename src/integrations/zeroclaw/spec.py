"""Zeroclaw spec loader and validator.

Provides Pydantic v2 models and loader for Zeroclaw gateway integration specs.
"""

import json
from pathlib import Path
from typing import Literal, Any
from pydantic import BaseModel, Field, field_validator


class GatewaySpec(BaseModel):
    """Gateway endpoint configuration."""

    port: int = Field(..., ge=1, le=65535, description="Gateway port (1-65535)")
    health_path: str = Field(..., description="Health check endpoint path (must start with /)")
    execute_path: str = Field(..., description="Execute endpoint path (must start with /)")
    stream_mode: Literal["none", "sse", "ws"] = Field(..., description="Streaming mode")

    @field_validator("health_path", "execute_path")
    @classmethod
    def _validate_path_starts_with_slash(cls, v: str) -> str:
        if not v.startswith("/"):
            raise ValueError(f"Path must start with '/': {v}")
        return v


class AuthSpec(BaseModel):
    """Authentication configuration."""

    mode: Literal["bearer", "none"] = Field(..., description="Authentication mode")


class RuntimeSpec(BaseModel):
    """Runtime configuration."""

    config_path: str = Field(
        ...,
        description="Absolute path to runtime config in sandbox (must start with /)",
    )
    start_command: str = Field(..., description="Shell command to start the gateway runtime")

    @field_validator("config_path")
    @classmethod
    def _validate_config_path(cls, v: str) -> str:
        if not v.startswith("/"):
            raise ValueError(f"Config path must start with '/': {v}")
        # Check for pack mount isolation violation
        if v.startswith("/workspace/pack"):
            raise ValueError(
                f"Config path cannot live under /workspace/pack (mount isolation): {v}"
            )
        return v


class ExamplesSpec(BaseModel):
    """Example request/response payloads."""

    execute_request: dict[str, Any] = Field(..., description="Example execute request payload")
    execute_response: dict[str, Any] = Field(..., description="Example execute response payload")


class ZeroclawSpec(BaseModel):
    """Complete Zeroclaw gateway integration specification."""

    version: str = Field(..., description="Spec version (semver)")
    gateway: GatewaySpec = Field(..., description="Gateway endpoint configuration")
    auth: AuthSpec = Field(..., description="Authentication configuration")
    runtime: RuntimeSpec = Field(..., description="Runtime configuration")
    examples: ExamplesSpec = Field(..., description="Example request/response payloads")


def load_zeroclaw_spec(
    path: str = "src/integrations/zeroclaw/spec.json",
) -> ZeroclawSpec:
    """Load and validate a Zeroclaw spec file.

    Args:
        path: Path to the spec JSON file. Defaults to "src/integrations/zeroclaw/spec.json"

    Returns:
        Validated ZeroclawSpec instance

    Raises:
        FileNotFoundError: If the spec file doesn't exist
        json.JSONDecodeError: If the file contains invalid JSON
        ValueError: If the spec fails validation
    """
    spec_path = Path(path)

    if not spec_path.exists():
        raise FileNotFoundError(f"Zeroclaw spec not found: {path}")

    with open(spec_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return ZeroclawSpec.model_validate(data)
