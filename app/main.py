from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.config import settings
from app.core.redis import get_redis, close_redis
from app.api.v1.ingest import router as ingest_router
from app.api.v1.stream import router as stream_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    await get_redis()
    print(f"Redis Connected: {settings.REDIS_URL}")

    yield

    # --- Shutdown ---
    await close_redis()
    print("Redis connection closed.")


app = FastAPI(title="specter-cloud", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(ingest_router)
app.include_router(stream_router)
