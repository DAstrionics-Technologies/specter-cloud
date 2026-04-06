import structlog
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from app.core.redis import get_redis


log = structlog.get_logger()

router = APIRouter()


async def telemetry_generator(drone_id: str):
    r = await get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(f"drone:{drone_id}:telemetry")
    log.info("sse_client_connected", drone_id=drone_id)

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                yield f"data: {message['data']}\n\n"
    finally:
        await pubsub.unsubscribe(f"drone:{drone_id}:telemetry")
        await pubsub.close()
        log.info("sse_client_disconnected", drone_id=drone_id)


@router.get("/api/v1/stream/telemetry")
async def stream_telemetry(drone_id: str = Query(...)):
    
    return StreamingResponse(
        telemetry_generator(drone_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
