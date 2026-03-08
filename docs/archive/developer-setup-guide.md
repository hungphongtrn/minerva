# Developer Setup Guide: End-to-End Agent Workflow

Complete guide for setting up a working Minerva agent from scratch.

## Prerequisites

- Python 3.11+ with `uv` installed
- Docker and Docker Compose
- Daytona API key (for cloud deployment) or local Daytona setup
- Git

---

## Step 1: Initial Setup

### 1.1 Clone and Install

```bash
git clone <your-repo>
cd minerva
uv sync
```

### 1.2 Initialize Environment

```bash
# Generate .env.example and run preflight checks
uv run minerva init
```

**What this does:**
- Creates `.env.example` with all configuration options
- Checks database connectivity
- Validates Daytona credentials
- Shows preflight checklist with ✓/✗ status

**Expected output:**
```
============================================================
MINERVA PREFLIGHT CHECKLIST
============================================================

✓ DB_CONNECT               [BLOCKING]     [PASS]
  Database connection successful
✓ DAYTONA_AUTH             [BLOCKING]     [PASS]
  Daytona API key configured
✗ WORKSPACE_CONFIGURED     [BLOCKING]     [FAIL]
  MINERVA_WORKSPACE_ID is set to 'auto' - workspace not yet created
  → Run `minerva register <path-to-pack>` to create workspace and update .env
```

---

## Step 2: Configure Environment

### 2.1 Edit .env File

```bash
# Copy example to actual .env
cp .env.example .env

# Edit with your settings
nano .env  # or your preferred editor
```

### 2.2 Required Settings

```bash
# Database (defaults work with docker-compose)
DATABASE_URL=postgresql+psycopg://picoclaw:picoclaw_dev@localhost:5432/picoclaw

# Sandbox provider (required for full /runs execution)
SANDBOX_PROFILE=daytona

# Daytona credentials
DAYTONA_API_KEY=your-api-key-here
DAYTONA_TARGET=us

# OSS Mode - Set to 'auto' for automatic workspace creation
MINERVA_WORKSPACE_ID=auto
GUEST_ID=guest

# Snapshot (will be built in Step 3)
DAYTONA_PICOCLAW_SNAPSHOT_NAME=

# Optional: S3 for checkpoints
CHECKPOINT_ENABLED=false
```

### 2.3 Start PostgreSQL

```bash
# Start postgres in background
docker-compose up -d postgres

# Verify it's running
docker-compose ps
```

---

## Step 3: Build Picoclaw Snapshot

The snapshot is a Daytona image containing the Picoclaw runtime.

### 3.1 Configure Picoclaw Source

```bash
# Add to .env
PICOCLAW_REPO_URL=https://github.com/your-org/picoclaw.git
PICOCLAW_REPO_REF=main
```

### 3.2 Build Snapshot

```bash
# This clones Picoclaw repo and creates a Daytona snapshot
uv run minerva snapshot build
```

**What this does:**
- Clones Picoclaw repository
- Builds Docker image with Picoclaw runtime
- Creates Daytona snapshot with idempotent naming
- Takes ~15-30 minutes first time

**Expected output:**
```
Building Picoclaw Daytona snapshot...
Repository: https://github.com/your-org/picoclaw.git
Ref: main

✓ Cloned repository
✓ Built image
✓ Created snapshot: picoclaw-main-abc123

Add to your .env:
  DAYTONA_PICOCLAW_SNAPSHOT_NAME=picoclaw-main-abc123
```

### 3.3 Update .env with Snapshot Name

```bash
# Add the snapshot name to .env
DAYTONA_PICOCLAW_SNAPSHOT_NAME=picoclaw-main-abc123
```

---

## Step 4: Create Agent Pack

An agent pack defines your agent's identity, behavior, and skills.

### 4.1 Scaffold New Pack

```bash
# Create a new agent pack template
uv run minerva scaffold --out ./my-agent
```

**What this creates:**
```
my-agent/
├── AGENT.md      # Agent identity and capabilities
├── SOUL.md       # Personality and behavior
├── IDENTITY.md   # Identity metadata
└── skills/       # Skill implementations
    └── README.md
```

### 4.2 Customize Your Agent

Edit the files to define your agent:

**AGENT.md** - Core identity:
```markdown
# Agent: Assistant

## Role
Helpful AI assistant for software development tasks.

## Capabilities
- Code review and suggestions
- Documentation writing
- Debugging assistance
```

**SOUL.md** - Personality:
```markdown
# Soul Configuration

## Personality
Friendly, professional, and concise.

## Communication Style
- Use clear, simple language
- Provide code examples when helpful
- Ask clarifying questions when needed
```

**IDENTITY.md** - Metadata:
```markdown
# Identity

## Name
DevAssistant

## Version
1.0.0

## Author
Your Name
```

### 4.3 Add Skills (Optional)

Create skill files in `my-agent/skills/`:

```bash
mkdir -p my-agent/skills/code-review

# Create skill definition
cat > my-agent/skills/code-review/SKILL.md << 'EOF'
# Code Review Skill

## Purpose
Review code for bugs, style issues, and improvements.

## Usage
@code-review analyze <file-path>
EOF
```

---

## Step 5: Register Agent Pack

### 5.1 Run Registration

```bash
# Register the pack (creates workspace if MINERVA_WORKSPACE_ID=auto)
uv run minerva register ./my-agent
```

**What this does:**
- Validates pack structure (AGENT.md, SOUL.md, IDENTITY.md required)
- Creates workspace (if using 'auto')
- Registers pack in database
- Syncs files to Daytona Volume
- **Auto-updates .env with workspace ID**

**Expected output:**
```
Validating pack at /path/to/my-agent...
✓ Pack structure is valid

Creating default OSS workspace...
Created default workspace: a1b2c3d4-e5f6-7890-abcd-ef1234567890

Registering pack 'my-agent' in workspace a1b2c3d4-e5f6-7890-abcd-ef1234567890...
✓ Pack registered with ID: pack-uuid-here

Syncing pack files to Daytona Volume...
✓ Pack files synced to volume

============================================================
Pack registered successfully!
============================================================
  Workspace ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
  Pack ID: pack-uuid-here
  Name: my-agent

✓ Updated .env file with MINERVA_WORKSPACE_ID
============================================================
```

### 5.2 Verify .env Updated

```bash
# Check that workspace ID was auto-added
grep MINERVA_WORKSPACE_ID .env

# Should show:
# MINERVA_WORKSPACE_ID=a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## Step 6: Start Server

### 6.1 Run Preflight Check

```bash
# Verify everything is configured
uv run minerva init
```

**All checks should pass now:**
```
============================================================
MINERVA PREFLIGHT CHECKLIST
============================================================

✓ DB_CONNECT               [BLOCKING]     [PASS]
✓ DAYTONA_AUTH             [BLOCKING]     [PASS]
✓ WORKSPACE_CONFIGURED     [BLOCKING]     [PASS]
  Workspace 'Default OSS Workspace' configured with 1 agent pack(s)
✓ PICOCLAW_SNAPSHOT_CONFIG [WARNING]      [PASS]

SUMMARY: 0 blocking, 0 warnings
============================================================

✅ Preflight passed: Environment ready
```

### 6.2 Start Server

```bash
# Start the API server
uv run minerva serve
```

**Expected output:**
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## Step 7: Test Your Agent

### 7.1 Health Check

```bash
# Test server is running
curl http://localhost:8000/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "components": {
    "database": "healthy",
    "daytona": "healthy"
  }
}
```

### 7.2 Send a Message

```bash
# Start a conversation with your agent
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -H "X-User-ID: developer-001" \
  -H "X-Session-ID: session-abc-123" \
  -d '{
    "message": "Hello! Can you help me with Python?"
  }'
```

**What happens:**
1. Server validates X-User-ID and creates external_identity entry
2. Provisions Daytona sandbox (cold start ~30-60s)
3. Streams events back (provisioning → running → message)
4. Sandbox stays warm for session continuity

**Expected output (SSE stream):**
```
event: provisioning
data: {"status": "creating_sandbox", "message": "Creating Daytona sandbox..."}

event: provisioning
data: {"status": "identity_verification", "message": "Verifying identity files..."}

event: running
data: {"status": "active", "message": "Agent ready"}

event: message
data: {"role": "assistant", "content": "Hello! I'd be happy to help you with Python..."}
```

### 7.3 Test Session Continuity

Send another request with same headers:

```bash
# Same session = warm start (no provisioning delay)
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -H "X-User-ID: developer-001" \
  -H "X-Session-ID: session-abc-123" \
  -d '{
    "message": "What about list comprehensions?"
  }'
```

**Expected:** Immediate response (no provisioning events)

---

## Step 8: Multi-User Testing

Test that different users get isolated sandboxes:

```bash
# User A
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -H "X-User-ID: user-alice" \
  -H "X-Session-ID: alice-session" \
  -d '{"message": "Hello from Alice"}'

# User B (different sandbox)
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -H "X-User-ID: user-bob" \
  -H "X-Session-ID: bob-session" \
  -d '{"message": "Hello from Bob"}'
```

Both users get separate sandboxes despite same workspace.

---

## Troubleshooting

### Issue: "MINERVA_WORKSPACE_ID not configured"

**Solution:**
```bash
# Run register to auto-create and configure workspace
uv run minerva register ./my-agent
```

### Issue: "Workspace has no registered agent packs"

**Solution:**
```bash
# Register your agent pack
uv run minerva register ./my-agent
```

### Issue: "Picoclaw snapshot not found"

**Solution:**
```bash
# Build the snapshot
uv run minerva snapshot build

# Copy snapshot name from output and add to .env
```

### Issue: `/runs` fails and mentions local sandbox/gateway

**Cause:** `SANDBOX_PROFILE` is set to `local_compose`, which simulates lifecycle only.

**Solution:**
```bash
# Use real Daytona sandboxes for bridge execution
SANDBOX_PROFILE=daytona
```

### Issue: Database connection failed

**Solution:**
```bash
# Start postgres
docker-compose up -d postgres

# Run migrations if needed
uv run alembic upgrade head
```

### Issue: Sandbox provisioning timeout

**Check:**
```bash
# Verify Daytona credentials
echo $DAYTONA_API_KEY

# Check Daytona API connectivity
curl -H "Authorization: Bearer $DAYTONA_API_KEY" \
  https://api.daytona.io/v1/workspaces
```

---

## Quick Reference

### Common Commands

```bash
# Initialize and check environment
uv run minerva init

# Start server
uv run minerva serve

# Register/update agent pack
uv run minerva register ./my-agent

# Build Picoclaw snapshot
uv run minerva snapshot build

# View metrics
open http://localhost:8000/metrics

# API docs (in debug mode)
open http://localhost:8000/docs
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `DAYTONA_API_KEY` | Yes | Daytona API authentication |
| `MINERVA_WORKSPACE_ID` | Yes | Set to `auto` for automatic setup |
| `DAYTONA_PICOCLAW_SNAPSHOT_NAME` | Yes | After building snapshot |
| `GUEST_ID` | No | Guest user identifier |
| `CHECKPOINT_ENABLED` | No | Enable S3 checkpoint storage |

---

## Next Steps

- **Production deployment**: Use digest-pinned base images (`DAYTONA_BASE_IMAGE_STRICT_MODE=true`)
- **Monitoring**: Enable Prometheus metrics (`PROMETHEUS_ENABLED=true`)
- **Checkpoints**: Configure S3 for session persistence
- **Multiple packs**: Register additional agent packs for different use cases

---

**Need help?** Run `uv run minerva --help` or check the logs at `LOG_LEVEL=DEBUG`.
