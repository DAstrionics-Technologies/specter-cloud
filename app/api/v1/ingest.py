import structlog

from fastapi import APIRouter, Depends
from redis.exceptions import RedisError

from app.schemas.telemetry import TelemetryPayload
from app.auth.dependencies import get_current_drone
from app.core.redis import get_redis


log = structlog.get_logger()

router = APIRouter()


@router.post("/api/v1/ingest/telemetry")
async def ingest_telemetry(
    payload: TelemetryPayload,
    r=Depends(get_redis),
    drone=Depends(get_current_drone)
):
    # Fire-and-forget: onboard does not retry, so Redis failures are logged
    # and dropped, not surfaced as 5xx. Critical events must not ride this
    # channel — they need their own at-least-once endpoint.
    data = payload.model_dump_json()

    try:
        await r.set(f"drone:{drone.id}:telemetry", data, ex=10)
        await r.publish(f"drone:{drone.id}:telemetry", data)
    except RedisError as e:
        log.warning("telemetry_dropped", drone_id=drone.id, reason="redis", error=str(e))
        return {"status": "ok"}

    log.debug("telemetry_ingested", drone_id=drone.id)
    return {"status": "ok"}
