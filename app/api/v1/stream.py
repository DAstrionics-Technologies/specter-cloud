from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from app.core.redis import get_redis

router = APIRouter()

async def telemetry_generator(drone_id: str):
    r = await get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(f"drone:{drone_id}:telemetry")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                yield f"data: {message['data']}\n\n"
    finally:
        await pubsub.unsubscribe(f"drone:{drone_id}:telemetry")
        await pubsub.close()

@router.get("/api/v1/stream/telemetry")
async def stream_telemetry(drone_id: str = Query(...)):
    return StreamingResponse(
        telemetry_generator(drone_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )