---
created: 2026-03-02T16:12:16.553Z
title: Fix workspace/pack mount mixing static and dynamic data
area: infrastructure
files:
  - src/infrastructure/sandbox/providers/daytona.py
  - reference_repos/picoclaw/pkg/agent/context.go:152-154
  - reference_repos/picoclaw/pkg/config/config.go:170
---

## Problem

Current plan mounts agent pack volume at `/workspace/pack` and configures picoclaw workspace to `/workspace/pack`. This causes a critical issue:

Picoclaw creates dynamic runtime directories inside the workspace:
- `/workspace/pack/memory/`
- `/workspace/pack/sessions/`
- `/workspace/pack/cron/`

Since the pack volume is shared across sandboxes (same digest = same volume), this means:
1. Dynamic session data mixes with static identity files
2. Different users' session data conflicts on the shared volume
3. Runtime state pollutes the immutable pack content
4. The volume-per-digest isolation breaks down

## Context

From picoclaw code (`pkg/agent/context.go:152-154`):
```go
filePath := filepath.Join(cb.workspace, filename)  // Loads AGENT.md from workspace root
```

Picoclaw only has ONE `workspace` config (no separate identity_path), so:
- If workspace = `/workspace/pack` → dynamic data goes in pack volume (BAD)
- If workspace = `/workspace/` → identity files not found (can't load AGENT.md)

## Solution

**Option 1: Copy/Symlink at Provision Time** (Recommended for Phase 3.2)
- Mount pack at `/opt/pack/` (read-only)
- At sandbox startup, copy or symlink identity files from `/opt/pack/` to `/workspace/`
- Set picoclaw workspace to `/workspace/` (normal, isolated per-sandbox)

**Option 2: Modify Daytona Provider**
- Update `verify_identity_files()` to check `/opt/pack/` instead of `/workspace/pack/`
- Update config upload to point picoclaw to `/workspace/` for dynamic data
- Update volume mount from `/workspace/pack` to `/opt/pack`

**Option 3: Long-term - Modify Picoclaw**
- Add `identity_path` config separate from `workspace`
- Load static files from identity_path
- Write dynamic data to workspace

## References

- Current volume naming: `agent-pack-{agent_pack_id}-{source_digest}`
- Mount location in plan: `/workspace/pack`
- Picoclaw expects: identity files at workspace root, creates subdirs for runtime data
