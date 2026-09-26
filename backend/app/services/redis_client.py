"""Shared Redis connection. When REDIS_URL is empty the platform falls back to in-process
implementations (single node only) so tests and quick local runs need no infrastructure."""

import redis.asyncio as redis

from app.core.config import get_settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis | None:
    global _client
    url = get_settings().redis_url
    if not url:
        return None
    if _client is None:
        _client = redis.from_url(url, decode_responses=True, health_check_interval=30)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
