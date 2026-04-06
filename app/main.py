import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.middleware import RequestIDMiddleware
from app.core.redis import get_redis, close_redis
from app.api.v1.ingest import router as ingest_router
from app.api.v1.stream import router as stream_router
from app.api.v1.health import router as health_router


log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    setup_logging()
    await get_redis()
    log.info("redis_connected", url=settings.REDIS_URL)

    yield

    # --- Shutdown ---
    await close_redis()
    log.info("redis_disconnected")


app = FastAPI(title="specter-cloud", version="0.1.0", lifespan=lifespan)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error("unhandled_exception", path=request.url.path, error=str(exc), exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"}
    )


# Middlewares
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)


# Routes
app.include_router(health_router)
app.include_router(ingest_router)
app.include_router(stream_router)
