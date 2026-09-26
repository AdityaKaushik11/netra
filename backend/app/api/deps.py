from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decode_token, hash_api_key
from app.db import get_db
from app.models import ApiClient, User
from app.models.enums import ActorType, Role
from app.services import ratelimit, sessions
from app.services.audit import Actor

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

DB = Depends(get_db)


def client_ip(request: Request) -> str | None:
    # uvicorn --proxy-headers already resolved X-Forwarded-For from the edge proxy (Caddy
    # overwrites any client-supplied value), so request.client is the real caller.
    return request.client.host if request.client else None


@dataclass
class Principal:
    """Authenticated caller: either a human user (JWT) or a machine client (API key)."""

    user: User | None = None
    client: ApiClient | None = None
    ip: str | None = None

    @property
    def actor(self) -> Actor:
        if self.user:
            return Actor(ActorType.USER, str(self.user.id), self.user.username, self.ip)
        assert self.client
        return Actor(ActorType.API_CLIENT, str(self.client.id), self.client.name, self.ip)

    @property
    def name(self) -> str:
        return self.user.username if self.user else f"client:{self.client.name}"  # type: ignore[union-attr]


UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


async def _user_from_token(db: AsyncSession, token: str) -> User:
    try:
        payload = decode_token(token, "access")
    except jwt.PyJWTError:
        raise UNAUTHORIZED from None
    if await sessions.is_revoked(payload):
        raise UNAUTHORIZED
    user = await db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise UNAUTHORIZED
    return user


async def _client_from_key(db: AsyncSession, key: str) -> ApiClient:
    client = await db.scalar(select(ApiClient).where(ApiClient.key_hash == hash_api_key(key)))
    if client is None or not client.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    now = datetime.now(UTC)
    # Throttled: avoid a write on every event / heartbeat from high-rate producers
    if client.last_used_at is None or now - client.last_used_at > timedelta(seconds=60):
        await db.execute(update(ApiClient).where(ApiClient.id == client.id).values(last_used_at=now))
    return client


async def get_current_user(
    token: str | None = Security(oauth2_scheme),
    db: AsyncSession = DB,
) -> User:
    if not token:
        raise UNAUTHORIZED
    user = await _user_from_token(db, token)
    await ratelimit.hit(f"user:{user.id}", get_settings().rate_limit_api_per_min)
    return user


def require_roles(*roles: Role):
    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return checker


any_user = require_roles(Role.ADMIN, Role.OPERATOR, Role.VIEWER)
operator_or_admin = require_roles(Role.ADMIN, Role.OPERATOR)
admin_only = require_roles(Role.ADMIN)


def principal_with(scope: str, *roles: Role):
    """Accept either a user JWT with one of `roles`, or an API key carrying `scope`."""

    async def dep(
        request: Request,
        token: str | None = Security(oauth2_scheme),
        api_key: str | None = Security(api_key_header),
        db: AsyncSession = DB,
    ) -> Principal:
        ip = client_ip(request)
        if api_key:
            client = await _client_from_key(db, api_key)
            if scope not in (client.scopes or []):
                raise HTTPException(status_code=403, detail=f"API key lacks scope '{scope}'")
            limit = get_settings().rate_limit_ingest_per_min
            await ratelimit.hit(f"client:{client.id}", limit)
            return Principal(client=client, ip=ip)
        if token:
            user = await _user_from_token(db, token)
            if user.role not in roles:
                raise HTTPException(status_code=403, detail="Insufficient role")
            await ratelimit.hit(f"user:{user.id}", get_settings().rate_limit_api_per_min)
            return Principal(user=user, ip=ip)
        raise UNAUTHORIZED

    return dep


def user_actor(user: User, request: Request) -> Actor:
    return Actor(ActorType.USER, str(user.id), user.username, client_ip(request))
