"""Single-use, hashed tokens for email verification and password reset."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.entities import EmailActionToken, User

PURPOSE_VERIFY_EMAIL = "verify_email"
PURPOSE_RESET_PASSWORD = "reset_password"


class InvalidEmailToken(ValueError):
    """Raised when a token is unknown, expired, or already used."""


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def issue_token(
    db: Session,
    user: User,
    purpose: str,
    ttl: timedelta,
) -> str:
    """Invalidate older outstanding links and return a new raw token once."""
    now = datetime.now(timezone.utc)
    db.query(EmailActionToken).filter(
        EmailActionToken.user_id == user.id,
        EmailActionToken.purpose == purpose,
        EmailActionToken.used_at.is_(None),
    ).update({EmailActionToken.used_at: now}, synchronize_session=False)

    raw_token = secrets.token_urlsafe(32)
    db.add(
        EmailActionToken(
            user_id=user.id,
            purpose=purpose,
            email=(user.email or "").strip().lower(),
            token_hash=_hash_token(raw_token),
            expires_at=now + ttl,
        )
    )
    db.commit()
    return raw_token


def consume_token(db: Session, raw_token: str, purpose: str) -> tuple[EmailActionToken, User]:
    """Lock, validate, and mark one token as used. Caller commits the action."""
    now = datetime.now(timezone.utc)
    token = (
        db.query(EmailActionToken)
        .filter(
            EmailActionToken.token_hash == _hash_token(raw_token),
            EmailActionToken.purpose == purpose,
        )
        .with_for_update()
        .first()
    )
    if token is None or token.used_at is not None or _as_utc(token.expires_at) <= now:
        raise InvalidEmailToken

    owner = db.query(User).filter(User.id == token.user_id).first()
    if owner is None or not owner.is_active:
        raise InvalidEmailToken

    token.used_at = now
    return token, owner
