# Picoclaw Multi-Tenant OSS Runtime

## Local Postgres

Start a local PostgreSQL instance for development:

```bash
# Start Postgres (detached mode)
docker compose up -d postgres

# Check status/logs
docker compose ps postgres
docker compose logs -f postgres

# Stop Postgres (keeps data)
docker compose down

# Reset database (removes all data)
docker compose down -v
```

### Connection Details

- **Host:** localhost
- **Port:** 5432 (configurable via POSTGRES_PORT env var)
- **Database:** picoclaw
- **User:** picoclaw
- **Password:** picoclaw_dev

### Configuration

Copy `.env.example` to `.env` and customize values:

```bash
cp .env.example .env
```

The `.env` file controls both the Docker Compose service and the application connection string via `DATABASE_URL`.

### Quick Start

1. Copy environment defaults: `cp .env.example .env`
2. Start Postgres: `docker compose up -d postgres`
3. Wait for healthcheck (10-15 seconds)
4. Database is ready at `postgresql+psycopg://picoclaw:picoclaw_dev@localhost:5432/picoclaw`
