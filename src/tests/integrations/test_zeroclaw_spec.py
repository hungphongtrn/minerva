"""Tests for Zeroclaw spec loader.

Validates the spec loader and validation rules are enforced correctly.
"""

import json
import pytest
from pathlib import Path

from src.integrations.zeroclaw.spec import load_zeroclaw_spec, ZeroclawSpec


class TestLoadZeroclawSpec:
    """Tests for load_zeroclaw_spec() function."""

    def test_load_template_succeeds(self):
        """Loading the spec.template.json should succeed."""
        spec = load_zeroclaw_spec("src/integrations/zeroclaw/spec.template.json")

        assert isinstance(spec, ZeroclawSpec)
        assert spec.version == "1.0.0"
        assert spec.gateway.port == 18790
        assert spec.gateway.health_path == "/health"
        assert spec.gateway.execute_path == "/webhook"
        assert spec.gateway.stream_mode == "none"
        assert spec.auth.mode == "bearer"
        assert spec.runtime.config_path == "/workspace/.zeroclaw/config.json"
        assert (
            spec.runtime.start_command
            == "zeroclaw-gateway --config /workspace/.zeroclaw/config.json"
        )

    def test_load_nonexistent_file_raises(self):
        """Loading a non-existent file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError) as exc_info:
            load_zeroclaw_spec("src/integrations/zeroclaw/nonexistent.json")

        assert "nonexistent.json" in str(exc_info.value)

    def test_load_invalid_json_raises(self, tmp_path: Path):
        """Loading invalid JSON should raise JSONDecodeError."""
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text("not valid json")

        with pytest.raises(json.JSONDecodeError):
            load_zeroclaw_spec(str(invalid_file))


class TestSpecValidation:
    """Tests for spec validation rules."""

    @pytest.fixture
    def valid_spec_dict(self):
        """Returns a valid spec dict for modification in tests."""
        return {
            "version": "1.0.0",
            "gateway": {
                "port": 18790,
                "health_path": "/health",
                "execute_path": "/webhook",
                "stream_mode": "none",
            },
            "auth": {"mode": "bearer"},
            "runtime": {
                "config_path": "/workspace/.zeroclaw/config.json",
                "start_command": "zeroclaw-gateway --config /workspace/.zeroclaw/config.json",
            },
            "examples": {
                "execute_request": {"message": "test"},
                "execute_response": {"success": True},
            },
        }

    def test_invalid_gateway_port_too_low(self, valid_spec_dict, tmp_path: Path):
        """Gateway port below 1 should fail validation."""
        valid_spec_dict["gateway"]["port"] = 0

        spec_file = tmp_path / "invalid_port.json"
        spec_file.write_text(json.dumps(valid_spec_dict))

        with pytest.raises(ValueError) as exc_info:
            load_zeroclaw_spec(str(spec_file))

        assert "port" in str(exc_info.value).lower()

    def test_invalid_gateway_port_too_high(self, valid_spec_dict, tmp_path: Path):
        """Gateway port above 65535 should fail validation."""
        valid_spec_dict["gateway"]["port"] = 70000

        spec_file = tmp_path / "invalid_port.json"
        spec_file.write_text(json.dumps(valid_spec_dict))

        with pytest.raises(ValueError) as exc_info:
            load_zeroclaw_spec(str(spec_file))

        assert "port" in str(exc_info.value).lower()

    def test_invalid_health_path_no_slash(self, valid_spec_dict, tmp_path: Path):
        """Health path not starting with / should fail validation."""
        valid_spec_dict["gateway"]["health_path"] = "health"

        spec_file = tmp_path / "invalid_path.json"
        spec_file.write_text(json.dumps(valid_spec_dict))

        with pytest.raises(ValueError) as exc_info:
            load_zeroclaw_spec(str(spec_file))

        assert "must start with '/'" in str(exc_info.value)

    def test_invalid_execute_path_no_slash(self, valid_spec_dict, tmp_path: Path):
        """Execute path not starting with / should fail validation."""
        valid_spec_dict["gateway"]["execute_path"] = "execute"

        spec_file = tmp_path / "invalid_path.json"
        spec_file.write_text(json.dumps(valid_spec_dict))

        with pytest.raises(ValueError) as exc_info:
            load_zeroclaw_spec(str(spec_file))

        assert "must start with '/'" in str(exc_info.value)

    def test_invalid_config_path_in_pack(self, valid_spec_dict, tmp_path: Path):
        """Runtime config path under /workspace/pack should fail validation."""
        valid_spec_dict["runtime"]["config_path"] = "/workspace/pack/config.json"

        spec_file = tmp_path / "invalid_config.json"
        spec_file.write_text(json.dumps(valid_spec_dict))

        with pytest.raises(ValueError) as exc_info:
            load_zeroclaw_spec(str(spec_file))

        assert "/workspace/pack" in str(exc_info.value)
        assert "mount isolation" in str(exc_info.value).lower()

    def test_invalid_config_path_no_slash(self, valid_spec_dict, tmp_path: Path):
        """Runtime config path not starting with / should fail validation."""
        valid_spec_dict["runtime"]["config_path"] = "workspace/config.json"

        spec_file = tmp_path / "invalid_path.json"
        spec_file.write_text(json.dumps(valid_spec_dict))

        with pytest.raises(ValueError) as exc_info:
            load_zeroclaw_spec(str(spec_file))

        assert "must start with '/'" in str(exc_info.value)

    def test_invalid_stream_mode(self, valid_spec_dict, tmp_path: Path):
        """Invalid stream_mode should fail validation."""
        valid_spec_dict["gateway"]["stream_mode"] = "invalid"

        spec_file = tmp_path / "invalid_mode.json"
        spec_file.write_text(json.dumps(valid_spec_dict))

        with pytest.raises(ValueError) as exc_info:
            load_zeroclaw_spec(str(spec_file))

    def test_invalid_auth_mode(self, valid_spec_dict, tmp_path: Path):
        """Invalid auth mode should fail validation."""
        valid_spec_dict["auth"]["mode"] = "invalid"

        spec_file = tmp_path / "invalid_auth.json"
        spec_file.write_text(json.dumps(valid_spec_dict))

        with pytest.raises(ValueError) as exc_info:
            load_zeroclaw_spec(str(spec_file))


class TestSpecSchema:
    """Tests that spec JSON matches the schema."""

    def test_template_loads_successfully(self):
        """The spec.template.json should load and validate via Pydantic models.

        Pydantic validation enforces the same rules as the JSON Schema,
        so successful loading proves schema compatibility.
        """
        spec = load_zeroclaw_spec("src/integrations/zeroclaw/spec.template.json")

        # Verify all required fields are present with correct types
        assert spec.version
        assert isinstance(spec.gateway.port, int)
        assert spec.gateway.health_path.startswith("/")
        assert spec.gateway.execute_path.startswith("/")
        assert spec.gateway.stream_mode in ("none", "sse", "ws")
        assert spec.auth.mode in ("bearer", "none")
        assert spec.runtime.config_path.startswith("/")
        assert spec.runtime.start_command
        assert isinstance(spec.examples.execute_request, dict)
        assert isinstance(spec.examples.execute_response, dict)
