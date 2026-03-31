from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from app.schemas.telemetry import TelemetryPayload
from app.core.redis import get_redis, close_redis
from redis.exceptions import ConnectionError as RedisConnectionError
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    redis = await get_redis()
    print(f"Redis Connected: {settings.REDIS_URL}")    

    yield

    # --- Shutdown ---
    await close_redis()
    print("Redis connection closed.")

app = FastAPI(title="specter-cloud", version="0.1.0", lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/api/v1/ingest/telemetry")
async def ingest_telemetry(
    payload: TelemetryPayload, 
    r = Depends(get_redis)
):

    data = payload.model_dump_json()

    try:
        await r.set(
            f"drone:{payload.drone_id}:telemetry",
            data,
            ex=10
        )
        await r.publish(
            f"drone:{payload.drone_id}:telemetry", 
            data
        )
    except RedisConnectionError:
        pass

    return {"status": "ok"}


