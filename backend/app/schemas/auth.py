from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import Role
from app.schemas import ORMModel


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=72)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: "UserOut"


class UserOut(ORMModel):
    id: int
    username: str
    full_name: str
    role: Role
    department_id: int | None
    is_active: bool
    last_login_at: datetime | None


class UserCreate(BaseModel):
    username: str = Field(pattern=r"^[a-zA-Z0-9_.-]{3,64}$")
    full_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=10, max_length=72)
    role: Role
    department_id: int | None = None


Scope = Literal["events:write", "cameras:heartbeat", "cameras:write"]


class ApiClientCreate(BaseModel):
    name: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9_. -]+$")
    scopes: list[Scope] = Field(default_factory=lambda: ["events:write", "cameras:heartbeat"], min_length=1)


class ApiClientOut(ORMModel):
    id: int
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None


class ApiClientCreated(ApiClientOut):
    api_key: str  # shown exactly once


TokenResponse.model_rebuild()
