"""Password hashing (Argon2id) and access-token (JWT, HS256) handling."""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings

# OWASP-recommended Argon2id parameters (19 MiB, 2 iterations, 1 lane).
_hasher = PasswordHasher(time_cost=2, memory_cost=19 * 1024, parallelism=1)
ALGORITHM = "HS256"
ISSUER = "fabtrack"
REFRESH_COOKIE = "fabtrack_refresh"
REFRESH_COOKIE_PATH = "/api/auth"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


# A real hash of a random value: verifying against it costs the same time as a real user,
# so login timing does not reveal whether a username exists.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID
    must_change_password: bool
    expires_at: datetime


def create_access_token(
    settings: Settings, *, user_id: uuid.UUID, session_id: uuid.UUID, must_change_password: bool
) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.access_token_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "sid": str(session_id),
        "pwc": must_change_password,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "iss": ISSUER,
        "typ": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM), expires


def decode_access_token(settings: Settings, token: str) -> AccessClaims:
    """Raises jwt.PyJWTError for any invalid, expired or tampered token."""
    data = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[ALGORITHM],
        issuer=ISSUER,
        options={"require": ["sub", "sid", "exp", "iat", "iss", "typ"]},
    )
    if data.get("typ") != "access":
        raise jwt.InvalidTokenError("not an access token")
    return AccessClaims(
        user_id=uuid.UUID(data["sub"]),
        session_id=uuid.UUID(data["sid"]),
        must_change_password=bool(data.get("pwc", False)),
        expires_at=datetime.fromtimestamp(data["exp"], tz=UTC),
    )


def new_refresh_secret() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_temporary_password() -> str:
    """Readable one-time password for admin resets (forced change on first login)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4))
