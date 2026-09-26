"""Fixed-window rate limiter shared across replicas via Redis (in-memory fallback)."""

import time

from fastapi import HTTPException, status

from app.services.redis_client import get_redis

_local: dict[str, tuple[int, float]] = {}


async def hit(bucket: str, limit: int, window_s: int = 60) -> None:
    window = int(time.time() // window_s)
    key = f"netra:rl:{bucket}:{window}"
    r = get_redis()
    if r is not None:
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_s + 1)
        count, _ = await pipe.execute()
    else:
        count, exp = _local.get(key, (0, 0))
        count += 1
        _local[key] = (count, time.time() + window_s)
        if len(_local) > 10_000:
            now = time.time()
            for k in [k for k, (_, e) in _local.items() if e < now]:
                _local.pop(k, None)
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(window_s - int(time.time()) % window_s)},
        )


def reset_local() -> None:
    _local.clear()
