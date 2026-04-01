import redis.asyncio as aioredis
from app.core.config import settings

_redis = None


async def get_redis():
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.REDIS_URL, encoding="utf-8", decode_responses=True
        )

    return _redis


async def close_redis():
    global _redis
    if _redis:
        await _redis.close()
        _redis = None
