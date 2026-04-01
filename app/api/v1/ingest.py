from fastapi import APIRouter, Depends
from app.schemas.telemetry import TelemetryPayload
from app.core.redis import get_redis
from redis.exceptions import ConnectionError as RedisConnectionError

router = APIRouter()


@router.post("/api/v1/ingest/telemetry")
async def ingest_telemetry(payload: TelemetryPayload, r=Depends(get_redis)):

    data = payload.model_dump_json()

    try:
        await r.set(f"drone:{payload.drone_id}:telemetry", data, ex=10)
        await r.publish(f"drone:{payload.drone_id}:telemetry", data)
    except RedisConnectionError:
        pass

    return {"status": "ok"}
