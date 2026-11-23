"""Database-backed refresh sessions and rotation."""
from __future__ import annotations

import hmac
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    generate_refresh_token,
    hash_refresh_token,
    parse_refresh_token,
)
from app.models.entities import User, UserSession

logger = logging.getLogger("cinerank.security")


class AuthenticationSessionError(Exception):
    """Base error for refresh-session failures."""


class InvalidRefreshToken(AuthenticationSessionError):
    pass


class RefreshReuseDetected(AuthenticationSessionError):
    pass


class RefreshConcurrencyConflict(AuthenticationSessionError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def security_log(event: str, **fields: object) -> None:
    # Structured fields keep terminal and JSON logs searchable without parsing
    # free-form text. Values are bounded here as well as in the formatter.
    clean_fields = {
        key: str(value)[:120] for key, value in fields.items() if value is not None
    }
    logger.info("security_event", extra={"event": event, **clean_fields})


def clean_user_agent(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    return cleaned[:255] or None


def session_is_active(session: UserSession, now: datetime | None = None) -> bool:
    current = now or utcnow()
    return session.revoked_at is None and as_utc(session.expires_at) > current


def create_session(db: Session, user: User, user_agent: str | None) -> tuple[UserSession, str]:
    now = utcnow()
    session_id = str(uuid.uuid4())
    raw_token = generate_refresh_token(session_id)
    session = UserSession(
        id=session_id,
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(raw_token),
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=clean_user_agent(user_agent),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    security_log("session_created", user_id=user.id, session_id=session.id)
    return session, raw_token


def rotate_refresh_token(
    db: Session, raw_token: str, user_agent: str | None
) -> tuple[UserSession, str, User]:
    parsed = parse_refresh_token(raw_token)
    if parsed is None:
        security_log("refresh_invalid_format")
        raise InvalidRefreshToken
    session_id, _secret = parsed
    now = utcnow()

    session = (
        db.query(UserSession)
        .filter(UserSession.id == session_id)
        .with_for_update()
        .first()
    )
    if session is None:
        security_log("refresh_unknown_session")
        raise InvalidRefreshToken

    if session.revoked_at is not None:
        security_log(
            "refresh_reuse_revoked_session",
            user_id=session.user_id,
            session_id=session.id,
        )
        raise RefreshReuseDetected

    if as_utc(session.expires_at) <= now:
        security_log("refresh_expired", user_id=session.user_id, session_id=session.id)
        raise InvalidRefreshToken

    user = db.query(User).filter(User.id == session.user_id).first()
    if user is None or not user.is_active:
        session.revoked_at = now
        db.commit()
        security_log("refresh_inactive_user", user_id=session.user_id, session_id=session.id)
        raise InvalidRefreshToken

    supplied_hash = hash_refresh_token(raw_token)
    if not hmac.compare_digest(session.refresh_token_hash, supplied_hash):
        last_used = as_utc(session.last_used_at)
        within_grace = (now - last_used).total_seconds() <= max(
            0, settings.AUTH_REFRESH_REUSE_GRACE_SECONDS
        )
        if within_grace:
            db.rollback()
            security_log(
                "refresh_concurrent_retry",
                user_id=session.user_id,
                session_id=session.id,
            )
            raise RefreshConcurrencyConflict
        session.revoked_at = now
        db.commit()
        security_log(
            "refresh_reuse_detected",
            user_id=session.user_id,
            session_id=session.id,
        )
        raise RefreshReuseDetected

    replacement_token = generate_refresh_token(session.id)
    replacement_hash = hash_refresh_token(replacement_token)
    updated = (
        db.query(UserSession)
        .filter(
            UserSession.id == session.id,
            UserSession.refresh_token_hash == supplied_hash,
            UserSession.revoked_at.is_(None),
        )
        .update(
            {
                UserSession.refresh_token_hash: replacement_hash,
                UserSession.last_used_at: now,
                UserSession.expires_at: now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
                UserSession.user_agent: clean_user_agent(user_agent) or session.user_agent,
            },
            synchronize_session=False,
        )
    )
    if updated != 1:
        db.rollback()
        fresh = db.query(UserSession).filter(UserSession.id == session.id).first()
        if fresh is not None and fresh.revoked_at is None:
            last_used = as_utc(fresh.last_used_at)
            if (now - last_used).total_seconds() <= max(
                0, settings.AUTH_REFRESH_REUSE_GRACE_SECONDS
            ):
                security_log(
                    "refresh_concurrent_retry",
                    user_id=fresh.user_id,
                    session_id=fresh.id,
                )
                raise RefreshConcurrencyConflict
            fresh.revoked_at = now
            db.commit()
            security_log(
                "refresh_reuse_detected",
                user_id=fresh.user_id,
                session_id=fresh.id,
            )
            raise RefreshReuseDetected
        security_log("refresh_rotation_conflict", session_id=session.id)
        raise InvalidRefreshToken

    db.commit()
    db.refresh(session)
    security_log("refresh_rotated", user_id=user.id, session_id=session.id)
    return session, replacement_token, user


def find_session_for_logout(db: Session, raw_token: str | None) -> UserSession | None:
    parsed = parse_refresh_token(raw_token)
    if parsed is None:
        return None
    return db.query(UserSession).filter(UserSession.id == parsed[0]).first()


def revoke_session(db: Session, session: UserSession, event: str = "session_revoked") -> None:
    if session.revoked_at is None:
        session.revoked_at = utcnow()
        db.commit()
        security_log(event, user_id=session.user_id, session_id=session.id)


def revoke_all_sessions(db: Session, user_id: int) -> int:
    now = utcnow()
    count = (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .update({UserSession.revoked_at: now}, synchronize_session=False)
    )
    db.commit()
    security_log("all_sessions_revoked", user_id=user_id, revoked_count=count)
    return int(count)


def active_sessions(db: Session, user_id: int) -> list[UserSession]:
    now = utcnow()
    return (
        db.query(UserSession)
        .filter(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
        .order_by(UserSession.last_used_at.desc())
        .all()
    )


def revoke_other_sessions(db: Session, user_id: int, keep_session_id: str) -> int:
    """Revoke all refresh sessions except the session performing the change."""
    now = utcnow()
    count = (
        db.query(UserSession)
        .filter(
            UserSession.user_id == user_id,
            UserSession.id != keep_session_id,
            UserSession.revoked_at.is_(None),
        )
        .update({UserSession.revoked_at: now}, synchronize_session=False)
    )
    db.commit()
    security_log(
        "other_sessions_revoked", user_id=user_id,
        keep_session_id=keep_session_id, revoked_count=int(count),
    )
    return int(count)
