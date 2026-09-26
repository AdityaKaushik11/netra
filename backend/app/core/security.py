"""Password hashing, JWTs, API keys, stream tokens and credential encryption."""

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

MAX_PASSWORD_BYTES = 72  # bcrypt limit; longer input is rejected rather than silently truncated


def hash_password(password: str) -> str:
    if len(password.encode()) > MAX_PASSWORD_BYTES:
        raise ValueError(f"password longer than {MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_access_token(subject: str, role: str) -> tuple[str, datetime]:
    s = get_settings()
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=s.access_token_minutes)
    token = jwt.encode(
        {"sub": subject, "role": role, "typ": "access", "exp": exp, "iat": now, "jti": uuid.uuid4().hex},
        s.jwt_secret,
        algorithm=s.jwt_algorithm,
    )
    return token, exp


def create_stream_token(subject: str, camera_id: str) -> tuple[str, datetime]:
    """Short-lived token scoped to a single camera; verified by the video gateway auth hook."""
    s = get_settings()
    exp = datetime.now(UTC) + timedelta(seconds=s.stream_token_seconds)
    token = jwt.encode(
        {"sub": subject, "cam": camera_id, "typ": "stream", "exp": exp},
        s.jwt_secret,
        algorithm=s.jwt_algorithm,
    )
    return token, exp


def decode_token(token: str, expected_type: str) -> dict:
    s = get_settings()
    payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm], options={"require": ["exp", "sub", "typ"]})
    if payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    return payload


# --- API keys for machine clients (analytics engines, edge gateways) -----------------------

API_KEY_PREFIX = "ntr_"


def generate_api_key() -> str:
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    # Keys are high-entropy random strings, so a fast keyed hash is appropriate (unlike passwords).
    return hmac.new(get_settings().jwt_secret.encode(), key.encode(), hashlib.sha256).hexdigest()


# --- Stream credential encryption at rest --------------------------------------------------


def _fernet() -> Fernet:
    s = get_settings()
    key = s.credentials_key
    if not key:
        # Derive a deterministic key from the JWT secret for dev; production must set CREDENTIALS_KEY.
        key = base64.urlsafe_b64encode(hashlib.sha256(s.jwt_secret.encode()).digest()).decode()
    return Fernet(key.encode())


def encrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None
