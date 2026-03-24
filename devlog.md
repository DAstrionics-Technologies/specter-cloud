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
