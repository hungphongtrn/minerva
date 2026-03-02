---
created: 2026-03-02T16:02:13.574Z
title: Resolve Identity Collision between Developer and End-User
area: auth
files:
  - src/db/models.py
  - src/api/dependencies/external_identity.py
  - src/api/oss/routes/runs.py
---

## Problem

The current architecture in Phase 3.2 shares the `users` table for two distinct roles:
1. The Developer (Owner): Registers agent packs and owns workspaces.
2. The End-User (Requester): Sends requests via `POST /runs` with `X-User-ID`.

This creates several issues:
- Semantic Collision: An end-user providing an ID matching the developer's email could gain owner rights.
- Access Gap: Auto-creating a 1:1 Workspace for every new `X-User-ID` means end-users cannot see or use agent packs registered in the developer's workspace.

## Solution

TBD. Potential approaches:
- Introduce a "Global/System Workspace" concept for OSS where end-users are granted "Guest" rights.
- Explicit mapping table (`external_identities`) to decouple opaque IDs from the main `users` table.
- Refine `resolve_external_principal` to map users to the correct existing workspace containing the desired Agent Pack.
