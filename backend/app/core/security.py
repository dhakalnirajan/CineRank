"""Password hashing, access JWTs, and opaque refresh-token primitives."""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from jwt import InvalidTokenError
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings

ALGORITHM = settings.JWT_ALGORITHM
REFRESH_TOKEN_BYTES = 48
# OWASP-recommended Argon2id baseline: 19 MiB, t=2, p=1.
_password_hasher = PasswordHasher(time_cost=2, memory_cost=19_456, parallelism=1, hash_len=32, salt_len=16)
logger = logging.getLogger("cinerank.security")


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: int
    session_id: str
    jti: str


def _password_limits() -> tuple[int, int]:
    return settings.PASSWORD_MIN_LENGTH, settings.PASSWORD_MAX_LENGTH


def _scrypt_parameters() -> tuple[int, int, int]:
    return settings.PASSWORD_SCRYPT_N, settings.PASSWORD_SCRYPT_R, settings.PASSWORD_SCRYPT_P


def _scrypt_maxmem(n: int, r: int, p: int) -> int:
    """Return a memory cap above the configured work factor.

    OpenSSL defaults to a 32 MiB cap, which is below the 33.5 MiB required by
    scrypt n=32768, r=8. Deriving the cap from the parameters keeps the
    configured work factor intact on every OpenSSL build.
    """
    return max(64 * 1024 * 1024, 256 * n * r * p)


def hash_password(password: str) -> str:
    minimum, maximum = _password_limits()
    if len(password) < minimum:
        raise ValueError(f"Password must be at least {minimum} characters")
    if len(password) > maximum:
        raise ValueError(f"Password must be at most {maximum} characters")
    return _password_hasher.hash(password)


def _parse_password_hash(encoded: str) -> tuple[str, int, int, int, bytes, bytes] | None:
    """Parse the legacy scrypt format so existing accounts can migrate at login."""
    try:
        scheme, n, r, p, salt_b64, digest_b64 = encoded.split("$", 5)
        if scheme != "scrypt":
            return None
        decode = base64.urlsafe_b64decode
        salt = decode(salt_b64.encode())
        digest = decode(digest_b64.encode())
        parsed_n, parsed_r, parsed_p = int(n), int(r), int(p)
        if (parsed_n <= 1 or parsed_r <= 0 or parsed_p <= 0 or parsed_n > 2**20
                or parsed_r > 32 or parsed_p > 16 or not salt or not digest):
            return None
        return scheme, parsed_n, parsed_r, parsed_p, salt, digest
    except (ValueError, TypeError):
        return None


def verify_password(password: str, encoded: str | None) -> bool:
    _minimum, maximum = _password_limits()
    if not encoded or len(password) > maximum:
        return False
    if encoded.startswith("$argon2id$"):
        try:
            return bool(_password_hasher.verify(encoded, password))
        except (VerifyMismatchError, VerificationError, InvalidHashError, ValueError):
            return False
    parsed = _parse_password_hash(encoded)
    if parsed is None:
        return False
    _scheme, n, r, p, salt, expected = parsed
    try:
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                                dklen=len(expected), maxmem=_scrypt_maxmem(n, r, p))
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(actual, expected)


def password_needs_rehash(encoded: str | None) -> bool:
    if not encoded:
        return False
    if encoded.startswith("$argon2id$"):
        try:
            return _password_hasher.check_needs_rehash(encoded)
        except (InvalidHashError, ValueError):
            return True
    # Every valid legacy scrypt hash is upgraded after successful verification.
    return _parse_password_hash(encoded) is not None


def verify_password_and_update(password: str, encoded: str | None) -> tuple[bool, str | None]:
    """Verify and transparently upgrade legacy/weaker hashes to Argon2id."""
    if not verify_password(password, encoded):
        return False, None
    if password_needs_rehash(encoded):
        return True, hash_password(password)
    return True, None


def create_access_token(subject: str, session_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": secrets.token_urlsafe(24),
        "sid": session_id,
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> AccessTokenClaims | None:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
            leeway=timedelta(seconds=settings.JWT_LEEWAY_SECONDS),
            options={
                "require": ["sub", "iss", "aud", "iat", "nbf", "exp", "jti", "sid", "type"]
            },
        )
    except (InvalidTokenError, ValueError, TypeError):
        logger.info("security_event", extra={"event": "invalid_access_token"})
        return None

    subject = payload.get("sub")
    session_id = payload.get("sid")
    jti = payload.get("jti")
    token_type = payload.get("type")
    if (
        not isinstance(subject, str)
        or not subject.isdigit()
        or not isinstance(session_id, str)
        or not session_id
        or not isinstance(jti, str)
        or not jti
        or token_type != "access"
    ):
        logger.info("security_event", extra={"event": "invalid_access_token_claims"})
        return None
    return AccessTokenClaims(user_id=int(subject), session_id=session_id, jti=jti)


def generate_refresh_token(session_id: str) -> str:
    return f"{session_id}.{secrets.token_urlsafe(REFRESH_TOKEN_BYTES)}"


def parse_refresh_token(raw_token: str | None) -> tuple[str, str] | None:
    if not raw_token or "." not in raw_token:
        return None
    session_id, secret = raw_token.split(".", 1)
    if not session_id or not secret:
        return None
    try:
        parsed = uuid.UUID(session_id)
    except (ValueError, AttributeError):
        return None
    if parsed.version != 4:
        return None
    return session_id, secret


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
