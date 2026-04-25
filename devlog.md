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

## 2026-04-02 — CORS + drone simulator script

- Added CORS middleware with `ALLOWED_ORIGINS` config for dashboard (localhost:3000) — needed for browser SSE connections across origins
- Added `scripts/simulate_drone.py` — dev utility that POSTs fake telemetry in a loop (circular flight path, oscillating altitude, draining battery) for manual testing
- Added `httpx` as dev dependency for the simulator
- First end-to-end real-time pipeline verified: simulator → ingest API → Redis pub/sub → SSE → dashboard

## 2026-04-03 — Expanded telemetry schema + DB persistence setup

- Expanded `TelemetryPayload` schema with fields from MAVLink: heading, battery, voltage, armed, flight_mode, gps_fix_type, satellites
- Schema designed from MAVLink message source of truth (HEARTBEAT, GLOBAL_POSITION_INT, VFR_HUD, SYS_STATUS, GPS_RAW_INT)
- Full-state payloads every message (not delta) — cellular is lossy, matches MAVLink convention, keeps server stateless
- Created SQLAlchemy 2.0 model (`TelemetryRecord`) with typed `Mapped` columns, `server_default=func.now()`, `String(64/32)` constraints
- Set up Alembic with async template — `env.py` reads DB URL from app settings (single source of truth)
- Generated and applied first migration: `create_table` + `create_hypertable('telemetry', 'time')` for TimescaleDB time-series partitioning
- Composite primary key `(time, drone_id)` — TimescaleDB auto-indexes on time DESC
- Updated Dockerfile to copy `alembic/` and `alembic.ini` into image
- Documented decisions in specter-docs: ADR-08 (SSE), ADR-09 (full-state telemetry), ADR-10 (Next.js), ADR-11 (API router structure)

## 2026-04-04 — DB write in ingest pipeline + health endpoints

- Added DB persistence to ingest endpoint — writes `TelemetryRecord` after Redis publish
- Ordering: Redis first (latency-sensitive), DB second (durable, can be batched later)
- DB write in separate try/catch — Redis failure shouldn't block persistence
- Verified rows in TimescaleDB via `psql` after POST from simulator
- Added `/health/db` readiness endpoint — runs `SELECT 1` to verify DB connectivity
- Moved `/health` from `main.py` to `app/api/v1/health.py` — all routes in api layer, main.py is setup only
- Health routes stay at root path (no `/api/v1/` prefix) — infrastructure endpoints, not business API

## 2026-04-05 — Professional test infrastructure

- Set up pytest + pytest-asyncio + httpx for async FastAPI testing
- Created `tests/conftest.py` with three fixtures:
  - `client` — lightweight, for endpoints that don't need DB/Redis
  - `db_session` — transaction-based with savepoint (`join_transaction_mode="create_savepoint"`), rolls back after each test
  - `db_client` — overrides both `get_db` and `get_redis` dependencies
- `FakeRedis` class as lightweight stand-in — no real Redis needed for tests
- `NullPool` test engine — avoids stale connections across pytest-asyncio event loops (Windows ProactorEventLoop issue)
- No-op lifespan override — prevents Redis startup during tests
- Test files: `test_schemas.py` (3), `test_health.py` (1), `test_ingest.py` (3) — all passing
- Updated CI pipeline: added TimescaleDB service container, Alembic migration step, pytest step, `/health/db` check
- Documented decisions: ADR-12 (test infra), ADR-13 (CI services), ADR-14 (health endpoints)

## 2026-04-06 — nginx-rtmp live video streaming

- Added nginx-rtmp container to docker-compose for live video streaming
- Architecture: RPi pushes RTMP on :1935, nginx auto-generates HLS segments, serves on :8080
- Config: 2s fragments, 10s playlist window, CORS headers for dashboard access
- Video and telemetry in separate containers — different resource profiles, independent failure
- Tested end-to-end: ffmpeg test source from Linux laptop → RTMP → nginx → HLS playback in browser
- Decision: RTMP→HLS over WebRTC (monitoring latency acceptable), SRT as future upgrade path
- RPi will use GStreamer `tee` to split existing camera pipeline — one RTSP connection for both GCS and cloud
- Documented decisions: ADR-15 (nginx-rtmp), ADR-16 (video/telemetry separation)

## 2026-04-06 — Structured logging + error handling

- Added `structlog` with environment-aware config: colored console in dev, JSON in production
- Shared processors: `merge_contextvars` (request ID), `add_log_level`, `TimeStamper`, `StackInfoRenderer`
- Added `RequestIDMiddleware` — generates UUID per request, binds to all logs via contextvars, returns in `X-Request-ID` header
- Added global exception handler — catches unhandled exceptions, logs full traceback, returns clean 500 JSON
- Added DB error handling in ingest — rollback on failure, log error, re-raise to global handler
- Redis failure remains a warning (degraded but functional), DB failure is an error (data loss)
- Logging conventions: snake_case event names, structured keyword args, no credentials in logs
- Replaced all `print()` with structured log calls
- Health check logging: only log failures (success checks are high-frequency noise)

## 2026-04-23 — Vendor-managed API key auth on telemetry ingest

- New tables: `orgs`, `drones`, `drone_api_keys` (consolidated migration replaces old telemetry-only table)
- `app/auth/api_key.py` — key generation (`sk_drone_<prefix>_<secret>`), prefix/hash split for O(log n) lookup with constant-time hash compare, debounced `last_used_at` update (60s) to avoid 600 UPDATE/min/drone at 10 Hz
- `app/auth/dependencies.py` — `get_current_drone` FastAPI dep reads `X-API-Key` header, returns authenticated `Drone`. Handlers never trust drone_id from request body.
- Ingest endpoint reads drone identity from the dep, removed `drone_id` from `TelemetryPayload`. Pydantic schema gained range validators (lat/lon/alt/speed/heading/battery/voltage/gps_fix_type/satellites) plus closed `Literal` flight_mode catalog.
- Auth model is **vendor-managed**: we mint/revoke, clients contact us. No HTTP admin surface — operator CLIs only (`scripts/mint_key.py`, `scripts/revoke_key.py`). Decision recorded as project memory; defers human-auth design until customer-facing self-service is needed.
- Rotation strategy: routine rotation via future `POST /auth/rotate` (drone uses current key to mint new), emergency re-key via Tailscale SSH (we have root on drones; clients don't have sudo). Bootstrap-credential separation deferred until fleet scale demands it.
- Test infra: `authed_drone` and `unkeyed_drone` fixtures. Tests verify keys actually authenticate via `verify_api_key` round-trip after mint, and stop authenticating after revoke — not just DB state changes. `expire_on_commit=False` on the test session to mirror production session config (the alternative was a `MissingGreenlet` error after `verify_api_key`'s commit expires the loaded `drone` instance).
- Granular auth-failure logging: `verify_api_key` fetches keys without filtering revoked/inactive, branches in Python, logs distinct `reason` per failure (`bad_format`, `unknown_prefix`, `hash_mismatch`, `revoked_key`, `inactive_drone`). `revoked_key` is the high-priority security signal — someone using a key we explicitly killed is now visible.
- PR #44.

## 2026-04-25 — Telemetry schema relaxation (driven by onboard integration)

- Replaced closed `Literal` flight_mode with permissive pattern: `min_length=1, max_length=32, pattern=r"^[A-Z0-9_]+$"`. Decouples cloud schema from firmware mode catalogs (ArduCopter / Plane / Rover all differ); accepts `UNKNOWN` during the boot window before first HEARTBEAT. Closed enum was creating a deploy-ordering coupling: every new firmware mode would have required a cloud redeploy.
- Relaxed `alt` lower bound from `ge=0` to `ge=-1000`. MAVLink `relative_alt` is signed (above-home displacement) — negatives are real: rooftop takeoff with ground descent, valley/mine surveys, GPS noise around home. The original `ge=0` reflected an unsigned-MSL mental model that didn't match the wire format. Lower bound is now a sanity ceiling, not a physics one.
- Test parametrize updated on both sides: rejection cases pin the new boundaries (`alt=-1001`, `flight_mode="manual"`, `flight_mode="ALT-HOLD"`, 33-char flight_mode); new acceptance parametrize covers `UNKNOWN`/`MANUAL`/`ACRO` flight modes and negative/zero/boundary altitudes — the tests now nail down both sides of the contract.
