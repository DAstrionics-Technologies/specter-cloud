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

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/health` | Health check | — |
| POST | `/api/v1/ingest/telemetry` | Ingest drone telemetry | `X-API-Key` |
| GET | `/api/v1/stream/telemetry?drone_id=X` | SSE telemetry stream | — |

## Auth (drone-side)

Drones authenticate to `/ingest/telemetry` with a per-drone API key in the
`X-API-Key` header. Keys are vendor-managed — minted and revoked via CLIs:

```bash
# Mint a key for a drone (must already exist as a DB row)
uv run python -m scripts.mint_key --org-slug <org> --drone-slug <drone> --label "<purpose>"

# Revoke a single key by its 8-hex prefix
uv run python -m scripts.revoke_key --prefix <prefix>

# Revoke every active key on a drone (break-glass)
uv run python -m scripts.revoke_key --org-slug <org> --drone-slug <drone>
```

Output of `mint_key` is the raw key (`sk_drone_<prefix>_<secret>`). Copy once;
only the prefix and SHA-256 hash are stored. `verify_api_key` logs a distinct
reason per failure path (`bad_format`, `unknown_prefix`, `hash_mismatch`,
`revoked_key`, `inactive_drone`) — `revoked_key` is the high-priority signal.

## Project structure

```
app/
├── api/v1/
│   ├── ingest.py      # Telemetry ingest endpoint (X-API-Key required)
│   └── stream.py      # SSE streaming endpoint
├── auth/
│   ├── api_key.py     # Key generation, parsing, verification (with granular logging)
│   └── dependencies.py# FastAPI dep: get_current_drone via X-API-Key
├── core/
│   ├── config.py      # Pydantic settings
│   ├── database.py    # Async SQLAlchemy engine
│   └── redis.py       # Async Redis client
├── models/
│   ├── base.py        # SQLAlchemy declarative base
│   ├── org.py         # Org (tenant)
│   ├── drone.py       # Drone (org-scoped)
│   └── drone_api_key.py # Hashed API key (prefix + hash, never plaintext)
├── schemas/
│   └── telemetry.py   # Pydantic request models
└── main.py            # FastAPI app setup + router includes
alembic/
├── env.py             # Async migration runner
└── versions/          # Migration files
scripts/
├── mint_key.py        # Operator CLI: issue a drone API key
├── revoke_key.py      # Operator CLI: revoke a key (by prefix or by drone)
└── simulate_drone.py  # Dev telemetry simulator
```
