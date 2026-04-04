# db/redis_client.py — Redis client for quick_parse temporary storage
import redis.asyncio as aioredis

from core.config import settings

redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
