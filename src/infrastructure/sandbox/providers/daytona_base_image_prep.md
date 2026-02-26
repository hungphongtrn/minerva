# Daytona Base Image Preparation Runbook

Progressive disclosure guide for building, publishing, and validating Picoclaw base images for Daytona sandboxes.

---

## Quick Start

Validate a candidate base image before production rollout:

```bash
# 1. Set your Daytona API key
export DAYTONA_API_KEY="your-api-key"

# 2. Run preflight validation
uv run python src/scripts/daytona_base_image_preflight.py \
    --image registry.example.com/picoclaw@sha256:abc123def456... \
    --json

# 3. Check exit code
if [ $? -eq 0 ]; then
    echo "✓ Image passed validation - ready for rollout"
else
    echo "✗ Image failed validation - see errors above"
fi
```

**Exit codes:**
- `0`: Preflight passed - image is valid
- `1`: Preflight failed - contract violation
- `2`: Configuration error - missing DAYTONA_API_KEY
- `3`: Unexpected error

---

## Prerequisites

### Required Credentials

1. **Daytona API Key** (from Daytona dashboard)
   ```bash
   export DAYTONA_API_KEY="dtn_..."
   ```

2. **Container Registry Access** (for private images)
   - Configure pull credentials in Daytona dashboard
   - Or use public registry

3. **Target Region** (optional, defaults to `us`)
   ```bash
   export DAYTONA_TARGET="us"  # or eu, ap
   ```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DAYTONA_API_KEY` | Yes | Daytona API authentication |
| `DAYTONA_API_URL` | No | Self-hosted Daytona URL (defaults to Cloud) |
| `DAYTONA_TARGET` | No | Target region: `us`, `eu`, `ap` |

---

## Base Image Contract

### Required Files

Picoclaw sandboxes require these identity files:

| File | Purpose |
|------|---------|
| `AGENT.md` | Agent personality and behavior definition |
| `SOUL.md` | Agent consciousness and values |
| `IDENTITY.md` | Agent identity metadata |
| `skills/` | Directory containing agent skills |

### Required Services

The base image must expose:

| Service | Port | Description |
|---------|------|-------------|
| Picoclaw Gateway | `18790` | HTTP API for bridge communication |

### Dockerfile Example

```dockerfile
FROM daytonaio/workspace-picoclaw:latest

# Copy identity files
COPY AGENT.md SOUL.md IDENTITY.md /workspace/
COPY skills/ /workspace/skills/

# Install Picoclaw gateway (if not in base)
# ... gateway installation commands ...

# Expose gateway port
EXPOSE 18790

# Default command starts gateway
CMD ["picoclaw-gateway", "--port", "18790"]
```

---

## Build Workflow

### Step 1: Create Dockerfile

Create a `Dockerfile` that includes Picoclaw identity files and gateway:

```dockerfile
# Use official Daytona workspace base
FROM daytonaio/workspace-picoclaw:latest

# Install Picoclaw runtime dependencies
RUN pip install picoclaw-gateway

# Copy agent identity
COPY AGENT.md /workspace/AGENT.md
COPY SOUL.md /workspace/SOUL.md
COPY IDENTITY.md /workspace/IDENTITY.md

# Copy skills
COPY skills/ /workspace/skills/

# Configure gateway
ENV GATEWAY_PORT=18790
EXPOSE 18790

WORKDIR /workspace
```

### Step 2: Build Image

```bash
# Build with explicit tag (mutable - for development)
docker build -t registry.example.com/picoclaw:dev .

# Tag with version (mutable - for staging)
docker tag registry.example.com/picoclaw:dev \
    registry.example.com/picoclaw:v1.0.0

# Push to registry
docker push registry.example.com/picoclaw:v1.0.0
```

### Step 3: Get Digest for Production

```bash
# Get the immutable digest
digest=$(docker inspect --format='{{index .RepoDigests 0}}' \
    registry.example.com/picoclaw:v1.0.0)

# Output: registry.example.com/picoclaw@sha256:abc123...
echo "Digest: $digest"
```

---

## Preflight Validation

### Basic Validation

```bash
uv run python src/scripts/daytona_base_image_preflight.py \
    --image registry.example.com/picoclaw@sha256:abc123...
```

### Verbose Mode (detailed progress)

```bash
uv run python src/scripts/daytona_base_image_preflight.py \
    --image registry.example.com/picoclaw@sha256:abc123... \
    --verbose
```

### JSON Output (CI integration)

```bash
uv run python src/scripts/daytona_base_image_preflight.py \
    --image registry.example.com/picoclaw@sha256:abc123... \
    --json > preflight-result.json

cat preflight-result.json | jq '.success'
```

**Example JSON output:**
```json
{
  "success": true,
  "image": "registry.example.com/picoclaw@sha256:abc123...",
  "sandbox_id": "preflight-a1b2c3d4e5f6",
  "checks": {
    "provision": {"status": "passed"},
    "sandbox_state": {"status": "passed", "state": "running"},
    "identity_files": {
      "status": "passed",
      "required_files": ["AGENT.md", "SOUL.md", "IDENTITY.md"],
      "required_dirs": ["skills"]
    },
    "gateway": {
      "status": "passed",
      "url": "https://gateway-abc123.us.daytona.run:18790"
    }
  },
  "errors": [],
  "remediation": null,
  "duration_seconds": 45.23
}
```

### Custom Timeout

For slower registries or large images:

```bash
uv run python src/scripts/daytona_base_image_preflight.py \
    --image registry.example.com/picoclaw@sha256:abc123... \
    --timeout 300  # 5 minutes
```

### Specific Region

```bash
uv run python src/scripts/daytona_base_image_preflight.py \
    --image registry.example.com/picoclaw@sha256:abc123... \
    --target eu
```

---

## Rollout Workflow

### CI/CD Integration

**GitHub Actions example:**

```yaml
name: Validate Base Image
on:
  push:
    tags:
      - 'base-image-v*'

jobs:
  preflight:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          
      - name: Install dependencies
        run: uv sync
        
      - name: Run preflight
        env:
          DAYTONA_API_KEY: ${{ secrets.DAYTONA_API_KEY }}
        run: |
          uv run python src/scripts/daytona_base_image_preflight.py \
            --image ${{ vars.PICOCLAW_BASE_IMAGE }} \
            --json
```

### Production Promotion

1. **Build and tag with digest**
   ```bash
   docker build -t registry.example.com/picoclaw:$VERSION .
   docker push registry.example.com/picoclaw:$VERSION
   DIGEST=$(docker inspect --format='{{index .RepoDigests 0}}' \
       registry.example.com/picoclaw:$VERSION)
   ```

2. **Run preflight validation**
   ```bash
   uv run python src/scripts/daytona_base_image_preflight.py \
       --image $DIGEST \
       --json > validation.json
   ```

3. **Check validation result**
   ```bash
   if [ $(jq -r '.success' validation.json) = "true" ]; then
       echo "Validation passed"
       # Update production config
       echo "DAYTONA_BASE_IMAGE=$DIGEST" >> .env.production
   else
       echo "Validation failed:"
       jq '.errors' validation.json
       exit 1
   fi
   ```

4. **Enable strict mode (production)**
   ```bash
   # In production environment
   export DAYTONA_BASE_IMAGE_STRICT_MODE=true
   export DAYTONA_BASE_IMAGE=$DIGEST
   ```

---

## Rollback Workflow

### Immediate Rollback

If issues are detected after rollout:

```bash
# 1. Identify previous digest from git history
PREVIOUS_DIGEST=$(git show HEAD~1:.env.production | grep DAYTONA_BASE_IMAGE | cut -d= -f2)

# 2. Update production config
echo "DAYTONA_BASE_IMAGE=$PREVIOUS_DIGEST" > .env.production

# 3. Restart services (depending on your deployment)
# kubectl rollout restart deployment/picoclaw
# or
# systemctl restart picoclaw
```

### Pin Previous Version

```bash
# Set explicit previous version
export DAYTONA_BASE_IMAGE="registry.example.com/picoclaw@sha256:previous_digest"
```

---

## Troubleshooting

### Preflight Failures

#### "DAYTONA_API_KEY environment variable is required"

**Cause:** API key not set
**Fix:**
```bash
export DAYTONA_API_KEY="dtn_..."
```

#### "Sandbox provisioning timed out"

**Cause:** Daytona infrastructure slow or image too large
**Fix:**
```bash
# Increase timeout
uv run python src/scripts/daytona_base_image_preflight.py \
    --image $IMAGE --timeout 300
```

#### "Sandbox is not running"

**Cause:** Image fails to start or crashes
**Fix:**
1. Check image runs locally: `docker run -it $IMAGE`
2. Verify entrypoint/command in Dockerfile
3. Check for missing dependencies

#### "Missing identity files"

**Cause:** Required files not in image
**Fix:**
1. Verify Dockerfile includes:
   ```dockerfile
   COPY AGENT.md SOUL.md IDENTITY.md /workspace/
   COPY skills/ /workspace/skills/
   ```
2. Check files exist in build context
3. Rebuild and push

#### "Gateway resolution failed"

**Cause:** Gateway not running or port not exposed
**Fix:**
1. Verify Dockerfile: `EXPOSE 18790`
2. Check gateway process starts correctly
3. Validate gateway health endpoint: `curl localhost:18790/health`

### Strict Mode Violations

If you see:
```
DAYTONA_BASE_IMAGE must use digest-pinned format for production safety
```

**Fix:**
```bash
# Get digest for your tag
digest=$(docker inspect --format='{{index .RepoDigests 0}}' $IMAGE)

# Update config to use digest
export DAYTONA_BASE_IMAGE=$digest
```

---

## Advanced Configuration

### Custom Sandbox ID

For tracking specific validation runs:

```bash
uv run python src/scripts/daytona_base_image_preflight.py \
    --image $IMAGE \
    --sandbox-id "preflight-$(date +%Y%m%d)"
```

### Self-Hosted Daytona

```bash
export DAYTONA_API_URL="https://daytona.example.com"
export DAYTONA_API_KEY="your-key"

uv run python src/scripts/daytona_base_image_preflight.py \
    --image $IMAGE \
    --target ""  # Self-hosted ignores target
```

### Multiple Region Validation

```bash
for region in us eu ap; do
    echo "Validating in $region..."
    uv run python src/scripts/daytona_base_image_preflight.py \
        --image $IMAGE \
        --target $region \
        --json > "validation-$region.json"
done
```

---

## Security Considerations

### Image Digest Pinning

**Always use digest-pinned images in production:**

```bash
# Good: Immutable reference
registry.example.com/picoclaw@sha256:abc123...

# Bad: Mutable tag (can drift)
registry.example.com/picoclaw:latest
```

### Strict Mode Enforcement

Enable strict mode to reject mutable tags:

```bash
export DAYTONA_BASE_IMAGE_STRICT_MODE=true
```

This ensures:
- Only digest-pinned images can be used
- Clear error messages for violations
- No silent rollout drift

### Registry Credentials

- Use short-lived tokens when possible
- Store credentials in secrets manager (not in repo)
- Rotate credentials regularly
- Use read-only tokens for Daytona pull

---

## Reference

### CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--image` | (required) | Base image reference |
| `--json` | false | Output JSON instead of text |
| `--verbose` | false | Enable verbose logging |
| `--sandbox-id` | auto-generated | Custom sandbox ID |
| `--timeout` | 120 | Provision timeout (seconds) |
| `--target` | us | Target region |
| `--version` | - | Show version |

### Validation Checks

| Check | Purpose | Failure Indication |
|-------|---------|-------------------|
| `provision` | Sandbox creates successfully | Daytona/infrastructure issue |
| `sandbox_state` | Sandbox reaches running state | Image startup failure |
| `identity_files` | Required files present | Missing identity files |
| `gateway` | Gateway endpoint resolvable | Missing gateway service |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success - image is valid |
| 1 | Failure - validation failed |
| 2 | Configuration error |
| 3 | Unexpected error |
| 130 | Cancelled by user (Ctrl+C) |

---

## Related Documentation

- [Daytona Python SDK](https://www.daytona.io/docs/en/python-sdk/)
- [Picoclaw Runtime Contract](../daytona.py)
- [Provider Configuration](../../../../config/settings.py)
