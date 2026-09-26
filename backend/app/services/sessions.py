"""Session security: token revocation and brute-force lockout.

* Every access token carries a unique `jti`. Logging out revokes that jti until it would have
  expired anyway, so a stolen token stops working the moment its owner signs out.
* A password reset revokes every token issued to that user before the reset.
* After LOCKOUT_THRESHOLD failed logins for one username within LOCKOUT_SECONDS the account is
  locked for LOCKOUT_SECONDS, whichever IP the attempts come from (defeats distributed guessing
  that per-IP rate limits miss). Locks apply to unknown usernames too, so they reveal nothing.

State lives in Redis so it holds across API replicas; an in-process fallback serves tests.
"""

import time

from app.core.config import get_settings
from app.services.redis_client import get_redis

LOCKOUT_THRESHOLD = 5
LOCKOUT_SECONDS = 15 * 60

_local: dict[str, tuple[str, float]] = {}


async def _set(key: str, value: str, ttl: int) -> None:
    r = get_redis()
    if r is not None:
        await r.set(key, value, ex=max(1, ttl))
    else:
        _local[key] = (value, time.time() + ttl)


async def _get(key: str) -> str | None:
    r = get_redis()
    if r is not None:
        return await r.get(key)
    item = _local.get(key)
    if not item or item[1] < time.time():
        _local.pop(key, None)
        return None
    return item[0]


async def _delete(key: str) -> None:
    r = get_redis()
    if r is not None:
        await r.delete(key)
    else:
        _local.pop(key, None)


# --- token revocation ------------------------------------------------------------------------


async def revoke_token(jti: str, exp: float) -> None:
    await _set(f"netra:revoked:{jti}", "1", int(exp - time.time()) + 1)


async def revoke_user_tokens(user_id: int) -> None:
    ttl = get_settings().access_token_minutes * 60
    await _set(f"netra:revoked-before:{user_id}", str(time.time()), ttl)


async def is_revoked(payload: dict) -> bool:
    jti = payload.get("jti")
    if not jti or await _get(f"netra:revoked:{jti}"):
        return True
    cutoff = await _get(f"netra:revoked-before:{payload.get('sub')}")
    return cutoff is not None and float(payload.get("iat", 0)) < float(cutoff)


# --- brute-force lockout ---------------------------------------------------------------------


def _fail_key(username: str) -> str:
    return f"netra:login-fail:{username.lower()[:64]}"


async def is_locked(username: str) -> bool:
    count = await _get(_fail_key(username))
    return count is not None and int(count) >= LOCKOUT_THRESHOLD


async def record_failure(username: str) -> int:
    key = _fail_key(username)
    r = get_redis()
    if r is not None:
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, LOCKOUT_SECONDS)
        count, _ = await pipe.execute()
        return int(count)
    count = int((await _get(key)) or 0) + 1
    await _set(key, str(count), LOCKOUT_SECONDS)
    return count


async def clear_failures(username: str) -> None:
    await _delete(_fail_key(username))


def reset_local() -> None:
    _local.clear()
