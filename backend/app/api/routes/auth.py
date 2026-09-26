from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Security, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, admin_only, any_user, client_ip, oauth2_scheme, user_actor
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)
from app.models import ApiClient, Department, User
from app.models.enums import ActorType
from app.schemas.auth import (
    ApiClientCreate,
    ApiClientCreated,
    ApiClientOut,
    LoginRequest,
    TokenResponse,
    UserCreate,
    UserOut,
)
from app.schemas.camera import DepartmentOut
from app.services import audit, ratelimit, sessions

router = APIRouter(tags=["auth & users"])

# Constant-time-ish defence against username enumeration via timing
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")


async def _authenticate(db: AsyncSession, request: Request, username: str, password: str) -> TokenResponse:
    ip = client_ip(request) or "unknown"
    username = username.strip().lower()
    await ratelimit.hit(f"login:{ip}", get_settings().rate_limit_login_per_min)
    if await sessions.is_locked(username):
        audit.record(db, audit.Actor(ActorType.USER, None, username[:64], ip), "LOGIN_LOCKED", "user", None)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. The account is locked for 15 minutes.",
        )
    user = await db.scalar(select(User).where(User.username == username))
    ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok or not user.is_active:
        failures = await sessions.record_failure(username)
        audit.record(
            db,
            audit.Actor(ActorType.USER, None, username[:64], ip),
            "LOGIN_FAILED",
            "user",
            None,
            {"consecutive_failures": failures},
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    await sessions.clear_failures(username)
    user.last_login_at = datetime.now(UTC)
    audit.record(db, user_actor(user, request), "LOGIN_SUCCESS", "user", user.id)
    await db.commit()
    token, exp = create_access_token(str(user.id), user.role)
    return TokenResponse(access_token=token, expires_at=exp, user=UserOut.model_validate(user))


@router.post("/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = DB):
    """Exchange username/password for a JWT bearer token."""
    return await _authenticate(db, request, body.username, body.password)


@router.post("/auth/token", response_model=TokenResponse, include_in_schema=True)
async def token_form(form: Annotated[OAuth2PasswordRequestForm, Depends()], request: Request, db: AsyncSession = DB):
    """OAuth2 password flow (used by the Swagger UI *Authorize* button)."""
    return await _authenticate(db, request, form.username, form.password)


@router.post("/auth/logout", status_code=204)
async def logout(
    request: Request,
    token: str | None = Security(oauth2_scheme),
    db: AsyncSession = DB,
    user: User = Depends(any_user),
):
    """Revoke the presented token server-side (it stops working immediately, on every replica)."""
    payload = decode_token(token or "", "access")
    await sessions.revoke_token(payload["jti"], payload["exp"])
    audit.record(db, user_actor(user, request), "LOGOUT", "user", user.id)
    await db.commit()


@router.get("/auth/me", response_model=UserOut)
async def me(user: User = Depends(any_user)):
    return user


@router.get("/departments", response_model=list[DepartmentOut])
async def departments(db: AsyncSession = DB, _: User = Depends(any_user)):
    return (await db.execute(select(Department).order_by(Department.name))).scalars().all()


@router.get("/users", response_model=list[UserOut])
async def list_users(db: AsyncSession = DB, _: User = Depends(admin_only)):
    return (await db.execute(select(User).order_by(User.username))).scalars().all()


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(body: UserCreate, request: Request, db: AsyncSession = DB, admin: User = Depends(admin_only)):
    if await db.scalar(select(User.id).where(User.username == body.username)):
        raise HTTPException(status_code=409, detail="Username already exists")
    user = User(
        username=body.username,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role=body.role,
        department_id=body.department_id,
    )
    db.add(user)
    await db.flush()
    audit.record(db, user_actor(admin, request), "USER_CREATED", "user", user.id, {"role": body.role})
    await db.commit()
    return user


@router.get("/api-clients", response_model=list[ApiClientOut])
async def list_clients(db: AsyncSession = DB, _: User = Depends(admin_only)):
    return (await db.execute(select(ApiClient).order_by(ApiClient.created_at.desc()))).scalars().all()


@router.post("/api-clients", response_model=ApiClientCreated, status_code=201)
async def create_client(
    body: ApiClientCreate, request: Request, db: AsyncSession = DB, admin: User = Depends(admin_only)
):
    """Issue an API key for an analytics engine / edge gateway. The key is returned **once**; only
    its keyed hash is stored."""
    key = generate_api_key()
    client = ApiClient(name=body.name, key_prefix=key[:10], key_hash=hash_api_key(key), scopes=body.scopes)
    db.add(client)
    await db.flush()
    audit.record(db, user_actor(admin, request), "API_CLIENT_CREATED", "api_client", client.id, {"scopes": body.scopes})
    await db.commit()
    return ApiClientCreated(**ApiClientOut.model_validate(client).model_dump(), api_key=key)


@router.post("/api-clients/{client_id}/revoke", response_model=ApiClientOut)
async def revoke_client(client_id: int, request: Request, db: AsyncSession = DB, admin: User = Depends(admin_only)):
    client = await db.get(ApiClient, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="API client not found")
    client.is_active = False
    audit.record(db, user_actor(admin, request), "API_CLIENT_REVOKED", "api_client", client.id)
    await db.commit()
    return client
