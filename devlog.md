# Dev Log

Chronological record of development decisions, progress, and open questions.

---

## 2025-03-21 — FastAPI boilerplate + CI

- Scaffolded project: FastAPI with `/health` endpoint, Dockerfile (python:3.12-slim + uv), docker-compose.yml, .env.example
- Package management via uv with `pyproject.toml`
- Added GitHub Actions CI: lint (ruff), health check (start server + curl /health), Docker build
- Fixed CI: needed `actions/setup-python` before uv can install packages
- Fixed CI: dev deps must go in `[dependency-groups]` not `[project.optional-dependencies]` for uv `--dev` to work
- CI passing

## 2026-03-24 — TimescaleDB + project restructure

- Added TimescaleDB (timescale/timescaledb-ha:pg17) as a Docker Compose service with healthcheck, named volume, and depends_on for the API
- Renamed `src/` → `app/` directory; updated Dockerfile, CI workflow, and all import paths
- Added `app/core/config.py` with Pydantic `BaseSettings` for typed, validated configuration (DATABASE_URL, ENVIRONMENT)
- Added `pydantic-settings` dependency
- Updated `.env.example` with DATABASE_URL and ENVIRONMENT, plus setup instructions
- CI does not need changes yet — health check runs without DB; will add service container when integration tests land
- Added `app/core/database.py` — async SQLAlchemy engine with `asyncpg` driver, connection pooling (`pool_size=5`, `max_overflow=10`), `pool_pre_ping` for container restarts, and `get_db()` FastAPI dependency
- Added `sqlalchemy[asyncio]` and `asyncpg` dependencies
- Documented decisions in specter-docs: ADR-05 (TimescaleDB), ADR-06 (Pydantic Settings), ADR-07 (Async SQLAlchemy)

## 2026-03-31 — Redis telemetry ingest + env fixes

- Added async Redis client singleton (`app/core/redis.py`) with connection lifecycle in FastAPI lifespan
- Added telemetry ingest endpoint (`POST /api/v1/ingest/telemetry`) — caches per-drone state with 10s TTL and broadcasts via Redis pub/sub
- Added `TelemetryPayload` Pydantic schema (drone_id, lat, lon, alt, speed, battery)
- Added Redis 7 Alpine service to Docker Compose with healthcheck
- Added `redis[asyncio]` dependency
- Updated CI: added Redis service container so health check passes with required `REDIS_URL`
- Fixed env config consistency: added `REDIS_URL` default in config.py, added to `.env.example`, fixed `ENV` → `ENVIRONMENT` typo in `.env`
- Architecture decision: WebSocket over SSE/MQTT for V1 real-time streaming — bidirectional needed for command & control, Redis pub/sub bridges naturally
- Architecture principle: transport-agnostic interfaces — all services (cloud, dashboard, onboard, link) code against stable API contracts, transport is an implementation detail

## 2026-04-01 — SSE telemetry streaming + API router refactor

- Added SSE streaming endpoint (`GET /api/v1/stream/telemetry?drone_id=X`) — subscribes to Redis pub/sub and streams telemetry to dashboard clients
- Refactored routes into `app/api/v1/` directory using FastAPI APIRouter — `ingest.py` and `stream.py` as separate modules
- `main.py` slimmed to app setup + router includes, `/health` stays app-level
- Architecture decision: SSE over WebSocket for dashboard streaming — unidirectional server→client, auto-reconnect, plain HTTP. WebSocket deferred until bidirectional need arises (command & control)
- Each data flow picks its own transport independently: HTTP POST for telemetry ingest, SSE for dashboard streaming, command & control TBD
