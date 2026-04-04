from fastapi import APIRouter, Depends
from redis.exceptions import ConnectionError as RedisConnectionError

from app.schemas.telemetry import TelemetryPayload
from app.models.telemetry import TelemetryRecord
from app.core.redis import get_redis
from app.core.database import get_db

router = APIRouter()


@router.post("/api/v1/ingest/telemetry")
async def ingest_telemetry(payload: TelemetryPayload, r=Depends(get_redis), db=Depends(get_db)):

    data = payload.model_dump_json()
    record = TelemetryRecord(**payload.model_dump())
    try:
        await r.set(f"drone:{payload.drone_id}:telemetry", data, ex=10)
        await r.publish(f"drone:{payload.drone_id}:telemetry", data)

    except RedisConnectionError:
        pass
    
    db.add(record)
    await db.commit()
        

    return {"status": "ok"}
