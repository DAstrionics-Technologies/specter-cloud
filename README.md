# specter-cloud

Backend API for the Specter drone operations platform. Receives telemetry from drones, provides real-time streaming, and manages fleet state.

Part of the **Specter ecosystem**: `specter-cloud` (backend) · `specter-dashboard` (frontend) · `specter-onboard` (RPi) · `specter-link` (comms manager)

## Stack

- **FastAPI** — async Python API framework
- **TimescaleDB** — time-series database (Postgres + hypertables)
- **Redis** — real-time telemetry cache and pub/sub
- **SQLAlchemy** (async) — ORM with asyncpg driver
- **Docker Compose** — local dev environment
- **GitHub Actions** — CI (lint, health check, Docker build)

## Quick start

```bash
# Clone and setup
cp .env.example .env
docker compose up --build
```

API available at `http://localhost:8000`

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/v1/ingest/telemetry` | Ingest drone telemetry |

## Project structure

```
app/
├── core/
│   ├── config.py      # Pydantic settings
│   ├── database.py    # Async SQLAlchemy engine
│   └── redis.py       # Async Redis client
├── schemas/
│   └── telemetry.py   # Pydantic models
└── main.py            # FastAPI app + routes
```
