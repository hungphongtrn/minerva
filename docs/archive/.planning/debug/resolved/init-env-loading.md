---
status: resolved
trigger: "uv run minerva init shows LLM API key not configured and Picoclaw snapshot name not configured even though they are set in .env file"
created: 2025-03-02
updated: 2025-03-02
---

# Debug Session: init env loading issue

## Issue
`uv run minerva init` shows LLM API key and Picoclaw snapshot name not configured even though they are set in .env file.

## Expected
Preflight checks should read from .env file via settings object.

## Actual
Preflight checks use os.getenv() directly which doesn't read .env file.

## Root Cause Analysis

Looking at the code:

1. `src/config/settings.py` uses pydantic_settings with `env_file=".env"` - this properly loads .env
2. `src/services/preflight_service.py` has methods that use `os.getenv()` directly:
   - `_check_llm_config()` (line 333): `os.getenv("LLM_API_KEY")` 
   - `_get_picoclaw_snapshot_name()` (line 414): `os.getenv("DAYTONA_PICOCLAW_SNAPSHOT_NAME")`

These bypass the settings object and only read actual environment variables, not the .env file.

## Fix Applied

### Changes to `src/services/preflight_service.py`:

1. **`_check_llm_config()`** (line 335-340):
   - Changed from: `os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")`
   - Changed to: `settings.LLM_API_KEY or settings.OPENAI_API_KEY`
   - Same for API_BASE and MODEL variables

2. **`_get_picoclaw_snapshot_name()`** (line 421-423):
   - Changed from: `os.getenv("DAYTONA_PICOCLAW_SNAPSHOT_NAME")`
   - Changed to: `settings.DAYTONA_PICOCLAW_SNAPSHOT_NAME or None`

### Changes to `src/config/settings.py`:

Added LLM configuration fields (lines 112-129):
- `LLM_API_KEY`
- `OPENAI_API_KEY`  
- `LLM_API_BASE`
- `OPENAI_API_BASE`
- `LLM_MODEL`
- `OPENAI_MODEL`

All with default values of empty string and appropriate docstrings.

## Evidence
- settings.py line 10: `env_file=".env"` configured
- preflight_service.py line 14: `settings` already imported
- preflight_service.py line 109: `settings.DAYTONA_PICOCLAW_SNAPSHOT_NAME` exists

## Verification

Verified that settings now load from .env file:
```
✓ Imports successful
  DAYTONA_PICOCLAW_SNAPSHOT_NAME: picoclaw-base
  LLM_API_KEY: sk-***
```

The preflight checks will now correctly detect values set in `.env` file.

