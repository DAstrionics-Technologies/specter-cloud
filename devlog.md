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
