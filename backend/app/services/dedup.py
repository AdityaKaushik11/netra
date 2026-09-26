"""Temporal de-duplication of analytics reads.

An ANPR camera typically reads the same plate 5-30 times while a vehicle passes. We keep the
first read as the canonical event and fold repeats inside DEDUP_WINDOW_SECONDS into its
repeat_count. The key lives in Redis (SET NX EX) so the guarantee holds across API replicas.
"""

import time

from app.core.config import get_settings
from app.services.redis_client import get_redis

_local: dict[str, tuple[str, float]] = {}


def dedup_key(camera_id: str, event_type: str, identifier: str) -> str:
    return f"netra:dedup:{camera_id}:{event_type}:{identifier}"


async def claim(key: str, event_ref: str) -> str | None:
    """Try to claim the key for this event. Returns None when claimed, or the existing
    event reference if a recent duplicate already holds it."""
    window = get_settings().dedup_window_seconds
    r = get_redis()
    if r is not None:
        ok = await r.set(key, event_ref, nx=True, ex=window)
        if ok:
            return None
        existing = await r.get(key)
        return existing or None
    now = time.monotonic()
    current = _local.get(key)
    if current and current[1] > now:
        return current[0]
    _local[key] = (event_ref, now + window)
    return None


async def update(key: str, event_ref: str) -> None:
    window = get_settings().dedup_window_seconds
    r = get_redis()
    if r is not None:
        await r.set(key, event_ref, ex=window)
    else:
        _local[key] = (event_ref, time.monotonic() + window)


async def release(key: str) -> None:
    r = get_redis()
    if r is not None:
        await r.delete(key)
    else:
        _local.pop(key, None)


def reset_local() -> None:
    _local.clear()
