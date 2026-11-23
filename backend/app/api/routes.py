"""Public catalogue and authenticated user-facing JSON API."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Path, Query, Request, Response, UploadFile, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import and_, or_, func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_session,
    get_current_user,
    get_optional_current_user,
    require_self,
    validate_cookie_request_origin,
)
from app.core.config import settings
from app.core.metrics import DATABASE_OPERATION_ERRORS
from app.core.rate_limit import auth_rate_limiter
from app.core.redis_client import redis_health
from app.core.serial_numbers import parse_title_serial
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password_and_update,
)
from app.db.session import get_db
from app.models.entities import (
    User, UserSession, UserPreference, Movie, Rating, SearchLog, Watchlist, Interaction,
    CatalogueState, CatalogueSortIndex,
)
from app.schemas.schemas import (
    UserRegister, UserOut, UserUpdate, TokenOut, SessionOut, MovieOut, RatingCreate, RatingOut,
    RecommendationResponse, SimilarTitlesResponse, SearchResponse, UserHistoryResponse,
    HistoryItem, InteractionCreate, UserPreferencesIn, UserPreferencesOut,
    EmailVerificationIn, PasswordForgotIn, PasswordResetIn, EmailActionOut,
)
from app.services import auth_service, email_service, email_token_service
from app.services.recommendation_service import recommendation_service, InvalidPageToken
from app.services.preference_service import preference_service
from app.services.catalogue_service import sort_key_expression

router = APIRouter()
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-used-for-timing-only")


def _client_host(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _enforce_auth_rate_limit(
    request: Request, scope: str, limit: int, identity: str | None = None,
    window_seconds: int = 60,
) -> None:
    normalized_identity = identity.strip().lower()[:80] if identity else "-"
    key = f"{scope}:ip:{_client_host(request)}"
    retry_after = auth_rate_limiter.check(key, max_requests=limit, window_seconds=window_seconds)
    if retry_after is None and identity:
        # Account-level quota is independent of source IP, limiting distributed
        # credential stuffing against one username/email.
        retry_after = auth_rate_limiter.check(
            f"{scope}:identity:{normalized_identity}", max_requests=limit,
            window_seconds=window_seconds,
        )
    if retry_after is not None:
        auth_service.security_log("rate_limit_triggered", scope=scope)
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=raw_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path=settings.AUTH_COOKIE_PATH,
        domain=settings.auth_cookie_domain,
        secure=settings.AUTH_COOKIE_SECURE,
        httponly=settings.AUTH_COOKIE_HTTPONLY,
        samesite=settings.auth_cookie_samesite,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.AUTH_COOKIE_NAME,
        path=settings.AUTH_COOKIE_PATH,
        domain=settings.auth_cookie_domain,
        secure=settings.AUTH_COOKIE_SECURE,
        httponly=settings.AUTH_COOKIE_HTTPONLY,
        samesite=settings.auth_cookie_samesite,
    )


def _cookie_deletion_headers() -> dict[str, str]:
    temporary = Response()
    _clear_refresh_cookie(temporary)
    return {"Set-Cookie": temporary.headers["set-cookie"]}


def _send_password_reset_quietly(email: str, token: str) -> None:
    """Keep delivery failures out of the public forgot-password response."""
    try:
        email_service.send_password_reset_email(email, token)
    except email_service.EmailDeliveryError:
        auth_service.security_log("password_reset_delivery_failed")


def _token_response(user: User, session: UserSession) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(str(user.id), session.id),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def _sign_cursor(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    signature = hmac.new(settings.SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def _read_cursor(token: str) -> dict:
    try:
        body, signature = token.rsplit(".", 1)
        expected = hmac.new(settings.SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        return json.loads(raw)
    except Exception as exc:
        raise HTTPException(400, "Invalid catalogue cursor") from exc


@router.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        database_ok = True
    except Exception:
        DATABASE_OPERATION_ERRORS.labels("health").inc()
        database_ok = False
    redis_ok = redis_health() if settings.REDIS_URL else None
    healthy = database_ok and (redis_ok is not False)
    return {
        "status": "ok" if healthy else "degraded",
        "database": database_ok,
        "redis": redis_ok,
        "ready": recommendation_service.is_ready,
        "models_loaded": sorted(recommendation_service.registry.ready_models) if recommendation_service.registry else [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/live")
def liveness():
    return {"status": "alive", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/health/ready")
def readiness(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        DATABASE_OPERATION_ERRORS.labels("readiness").inc()
        raise HTTPException(503, "Database is unavailable") from exc
    if settings.REDIS_URL and not redis_health():
        raise HTTPException(503, "Redis is unavailable")
    if not recommendation_service.is_ready:
        raise HTTPException(503, "Model bundle is not loaded")
    return {"status": "ready", "models": sorted(recommendation_service.registry.ready_models) if recommendation_service.registry else []}


@router.get("/models")
def list_models():
    return {
        "ready": recommendation_service.is_ready,
        "available": sorted(recommendation_service.registry.ready_models) if recommendation_service.registry else [],
        "bundle": recommendation_service.registry.release_id if recommendation_service.registry else None,
        "dataset": recommendation_service.registry.manifest.get("dataset") if recommendation_service.registry else None,
    }


@router.post("/auth/register", response_model=UserOut, status_code=201)
def register(
    payload: UserRegister,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    _enforce_auth_rate_limit(request, "register", settings.AUTH_RATE_LIMIT_REGISTER_PER_HOUR, payload.username, window_seconds=3600)
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(409, "Username already exists")
    if payload.email and db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(409, "Email already exists")
    try:
        user = User(username=payload.username, email=str(payload.email) if payload.email else None,
                    password_hash=hash_password(payload.password))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Username or email already exists") from exc
    db.refresh(user)
    auth_service.security_log("registration_succeeded", user_id=user.id)
    if user.email and email_service.is_configured():
        raw_token = email_token_service.issue_token(
            db,
            user,
            email_token_service.PURPOSE_VERIFY_EMAIL,
            timedelta(hours=settings.EMAIL_VERIFICATION_TTL_HOURS),
        )
        background_tasks.add_task(email_service.send_verification_email, user.email, raw_token)
    return user


@router.post("/auth/email/verification/request", response_model=EmailActionOut, status_code=202)
def request_email_verification(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _enforce_auth_rate_limit(
        request, "email_verification", settings.AUTH_RATE_LIMIT_EMAIL_PER_HOUR,
        str(current_user.id), window_seconds=3600,
    )
    if not email_service.is_configured():
        raise HTTPException(503, "Email delivery is not available right now")
    if not current_user.email:
        raise HTTPException(400, "Add an email address before verifying it")
    if current_user.email_verified_at is not None:
        return EmailActionOut(status="already_verified")
    raw_token = email_token_service.issue_token(
        db,
        current_user,
        email_token_service.PURPOSE_VERIFY_EMAIL,
        timedelta(hours=settings.EMAIL_VERIFICATION_TTL_HOURS),
    )
    try:
        email_service.send_verification_email(current_user.email, raw_token)
    except email_service.EmailDeliveryError as exc:
        raise HTTPException(503, "Email delivery is not available right now") from exc
    auth_service.security_log("email_verification_requested", user_id=current_user.id)
    return EmailActionOut(status="verification_sent")


@router.post("/auth/email/verify", response_model=UserOut)
def verify_email(payload: EmailVerificationIn, db: Session = Depends(get_db)):
    try:
        token, user = email_token_service.consume_token(
            db, payload.token, email_token_service.PURPOSE_VERIFY_EMAIL
        )
    except email_token_service.InvalidEmailToken as exc:
        raise HTTPException(400, "This verification link is invalid or has expired") from exc
    if not user.email or token.email != user.email.strip().lower():
        raise HTTPException(400, "This verification link is invalid or has expired")
    user.email_verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    auth_service.security_log("email_verified", user_id=user.id)
    return user


@router.post("/auth/password/forgot", response_model=EmailActionOut, status_code=202)
def forgot_password(
    payload: PasswordForgotIn,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    normalized_email = str(payload.email).strip().lower()
    _enforce_auth_rate_limit(
        request, "password_forgot", settings.AUTH_RATE_LIMIT_EMAIL_PER_HOUR,
        normalized_email, window_seconds=3600,
    )
    if not email_service.is_configured():
        raise HTTPException(503, "Email delivery is not available right now")

    user = db.query(User).filter(func.lower(User.email) == normalized_email).first()
    if user is not None and user.is_active and user.email:
        raw_token = email_token_service.issue_token(
            db,
            user,
            email_token_service.PURPOSE_RESET_PASSWORD,
            timedelta(minutes=settings.PASSWORD_RESET_TTL_MINUTES),
        )
        background_tasks.add_task(_send_password_reset_quietly, user.email, raw_token)
    auth_service.security_log("password_reset_requested")
    return EmailActionOut(status="reset_link_sent")


@router.post("/auth/password/reset", response_model=EmailActionOut)
def reset_password(
    payload: PasswordResetIn,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
):
    _enforce_auth_rate_limit(
        request, "password_reset", settings.AUTH_RATE_LIMIT_EMAIL_PER_HOUR, window_seconds=3600,
    )
    try:
        _token, user = email_token_service.consume_token(
            db, payload.token, email_token_service.PURPOSE_RESET_PASSWORD
        )
    except email_token_service.InvalidEmailToken as exc:
        raise HTTPException(400, "This reset link is invalid or has expired") from exc
    try:
        user.password_hash = hash_password(payload.new_password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    auth_service.revoke_all_sessions(db, user.id)
    _clear_refresh_cookie(response)
    auth_service.security_log("password_reset_completed", user_id=user.id)
    return EmailActionOut(status="password_reset")


@router.post("/auth/token", response_model=TokenOut)
def login(
    response: Response,
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    _enforce_auth_rate_limit(request, "login", settings.AUTH_RATE_LIMIT_LOGIN_PER_MINUTE, form.username)
    user = db.query(User).filter(User.username == form.username).first()
    candidate_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_valid, upgraded_hash = verify_password_and_update(form.password, candidate_hash)
    if user is None or not password_valid or not user.is_active:
        auth_service.security_log("login_failed")
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if upgraded_hash is not None:
        user.password_hash = upgraded_hash
        db.commit()
        auth_service.security_log("password_hash_upgraded", user_id=user.id)

    session, refresh_token = auth_service.create_session(
        db, user, request.headers.get("user-agent")
    )
    _set_refresh_cookie(response, refresh_token)
    auth_service.security_log("login_succeeded", user_id=user.id, session_id=session.id)
    return _token_response(user, session)


@router.post("/auth/refresh", response_model=TokenOut)
def refresh_session(
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
):
    validate_cookie_request_origin(request)
    _enforce_auth_rate_limit(request, "refresh", settings.AUTH_RATE_LIMIT_REFRESH_PER_MINUTE)
    raw_token = request.cookies.get(settings.AUTH_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(status_code=401, detail="Refresh session is not available")
    try:
        session, replacement_token, user = auth_service.rotate_refresh_token(
            db, raw_token, request.headers.get("user-agent")
        )
    except auth_service.RefreshConcurrencyConflict as exc:
        raise HTTPException(
            status_code=401,
            detail="Refresh already completed; retry with the current session",
            headers={"Retry-After": "1"},
        ) from exc
    except auth_service.RefreshReuseDetected as exc:
        raise HTTPException(
            status_code=401,
            detail="Refresh session is no longer valid",
            headers=_cookie_deletion_headers(),
        ) from exc
    except auth_service.InvalidRefreshToken as exc:
        raise HTTPException(
            status_code=401,
            detail="Refresh session is no longer valid",
            headers=_cookie_deletion_headers(),
        ) from exc
    _set_refresh_cookie(response, replacement_token)
    return _token_response(user, session)


@router.post("/auth/logout")
def logout(response: Response, request: Request, db: Session = Depends(get_db)):
    validate_cookie_request_origin(request)
    _enforce_auth_rate_limit(request, "logout", settings.AUTH_RATE_LIMIT_LOGOUT_PER_MINUTE)
    raw_token = request.cookies.get(settings.AUTH_COOKIE_NAME)
    session = auth_service.find_session_for_logout(db, raw_token)
    if session is not None:
        auth_service.revoke_session(db, session, event="logout_session_revoked")
    _clear_refresh_cookie(response)
    return {"status": "logged_out"}


@router.post("/auth/logout-all")
def logout_all(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    revoked = auth_service.revoke_all_sessions(db, current_user.id)
    _clear_refresh_cookie(response)
    return {"status": "logged_out_all", "revoked": revoked}


@router.post("/auth/logout-others")
def logout_other_sessions(
    current_user: User = Depends(get_current_user),
    current_session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    revoked = auth_service.revoke_other_sessions(db, current_user.id, current_session.id)
    return {"status": "other_sessions_revoked", "revoked": revoked}


@router.get("/auth/sessions", response_model=list[SessionOut])
def list_sessions(
    current_user: User = Depends(get_current_user),
    current_session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    sessions = auth_service.active_sessions(db, current_user.id)
    return [
        SessionOut.model_validate(session).model_copy(
            update={"current": session.id == current_session.id}
        )
        for session in sessions
    ]


@router.delete("/auth/sessions/{session_id}", status_code=204)
def revoke_selected_session(
    session_id: str,
    response: Response,
    current_user: User = Depends(get_current_user),
    current_session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    session = (
        db.query(UserSession)
        .filter(UserSession.id == session_id, UserSession.user_id == current_user.id)
        .first()
    )
    if session is None:
        raise HTTPException(404, "Session not found")
    auth_service.revoke_session(db, session, event="selected_session_revoked")
    if session.id == current_session.id:
        _clear_refresh_cookie(response)
    return None


@router.get("/auth/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/auth/me", response_model=UserOut)
def update_me(
    payload: UserUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    current_session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    return _update_user(current_user.id, payload, request, current_user, current_session, db)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    current_session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    require_self(user_id, current_user)
    return _update_user(user_id, payload, request, current_user, current_session, db)


def _update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    current_user: User,
    current_session: UserSession,
    db: Session,
) -> User:
    _enforce_auth_rate_limit(request, "profile_update", 20)
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(404, "User not found")

    changing_email = "email" in payload.model_fields_set and (
        (str(payload.email).strip() if payload.email is not None else None) != current_user.email
    )
    changing_password = "password" in payload.model_fields_set and bool(payload.password)
    password_changed = False
    if changing_email or changing_password:
        if not payload.current_password:
            raise HTTPException(403, "Enter your current password to change email or password")
        valid_password, replacement_hash = verify_password_and_update(
            payload.current_password, current_user.password_hash
        )
        if not valid_password:
            raise HTTPException(403, "Current password is incorrect")
        if replacement_hash:
            current_user.password_hash = replacement_hash

    if "username" in payload.model_fields_set and payload.username is not None:
        existing = (
            db.query(User)
            .filter(User.username == payload.username, User.id != user.id)
            .first()
        )
        if existing is not None:
            raise HTTPException(409, "Username already exists")
        user.username = payload.username

    previous_email = user.email
    if "email" in payload.model_fields_set:
        if payload.email is None or str(payload.email).strip() == "":
            user.email = None
        else:
            existing = (
                db.query(User)
                .filter(User.email == str(payload.email), User.id != user.id)
                .first()
            )
            if existing is not None:
                raise HTTPException(409, "Email already exists")
            user.email = str(payload.email)
        if user.email != previous_email:
            user.email_verified_at = None

    if changing_password:
        user.password_hash = hash_password(payload.password)
        password_changed = True

    if "avatar_url" in payload.model_fields_set:
        avatar = payload.avatar_url
        if avatar is not None and not (
            avatar.startswith("/media/avatars/")
            or avatar.startswith("https://")
        ):
            raise HTTPException(400, "Avatar must be an uploaded avatar path or HTTPS URL")
        user.avatar_url = avatar or None

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Username or email already exists") from exc
    db.refresh(user)
    if password_changed:
        auth_service.revoke_other_sessions(db, user.id, current_session.id)
    auth_service.security_log("profile_updated", user_id=user.id)
    return user


@router.post("/users/me/avatar", response_model=UserOut)
async def upload_my_avatar(
    request: Request,
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Validate, decode and re-encode a small avatar before storing it locally."""
    _enforce_auth_rate_limit(request, "avatar_upload", 10, str(current_user.id))
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if image.content_type not in allowed_types:
        raise HTTPException(415, "Upload a JPEG, PNG or WebP image")

    max_bytes = 2 * 1024 * 1024
    raw = await image.read(max_bytes + 1)
    if not raw or len(raw) > max_bytes:
        raise HTTPException(413, "Avatar must be smaller than 2 MB")

    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
        import io
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(415, "Unsupported image format")
            if source.width < 1 or source.height < 1 or source.width > 6000 or source.height > 6000:
                raise HTTPException(400, "Image dimensions are not supported")
            source.verify()
        with Image.open(io.BytesIO(raw)) as source:
            image_data = ImageOps.exif_transpose(source).convert("RGB")
            image_data.thumbnail((512, 512), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image_data.save(output, format="WEBP", quality=86, method=6)
            encoded = output.getvalue()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, "The uploaded file is not a valid image") from exc

    avatar_dir = settings.DATA_DIR / "media" / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}.webp"
    destination = avatar_dir / filename
    destination.write_bytes(encoded)

    old_url = current_user.avatar_url
    current_user.avatar_url = f"/media/avatars/{filename}"
    try:
        db.commit()
        db.refresh(current_user)
    except Exception:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise

    # Remove only prior app-managed avatars, never arbitrary external URLs.
    if old_url and old_url.startswith("/media/avatars/"):
        old_name = os.path.basename(old_url)
        old_path = avatar_dir / old_name
        if old_path.parent == avatar_dir:
            old_path.unlink(missing_ok=True)
    auth_service.security_log("avatar_updated", user_id=current_user.id)
    return current_user


@router.get("/titles/{media_type}/{serial_number}", response_model=MovieOut)
def get_title_by_serial(
    media_type: str = Path(..., pattern="^(movie|tv)$"),
    serial_number: str = Path(...),
    db: Session = Depends(get_db),
):
    try:
        serial = parse_title_serial(serial_number)
    except ValueError as exc:
        raise HTTPException(404, "Title not found") from exc
    movie = db.query(Movie).filter(
        Movie.media_type == media_type,
        Movie.serial_number == serial,
    ).first()
    if movie is None:
        raise HTTPException(404, "Title not found")
    return movie


@router.get("/titles/{media_type}/{serial_number}/similar", response_model=SimilarTitlesResponse)
def similar_titles_by_serial(
    media_type: str = Path(..., pattern="^(movie|tv)$"),
    serial_number: str = Path(...),
    limit: int = Query(10, ge=1, le=24),
    db: Session = Depends(get_db),
):
    try:
        serial = parse_title_serial(serial_number)
    except ValueError as exc:
        raise HTTPException(404, "Title not found") from exc
    movie = db.query(Movie).filter(
        Movie.media_type == media_type,
        Movie.serial_number == serial,
    ).first()
    if movie is None:
        raise HTTPException(404, "Title not found")
    items = recommendation_service.similar_titles(db, movie, limit=limit)
    return SimilarTitlesResponse(
        title_id=movie.title_id,
        model="itemknn-content",
        items=[MovieOut.model_validate(row) for row in items],
    )


@router.get("/movies/{title_id}", response_model=MovieOut)
def get_movie(title_id: str, db: Session = Depends(get_db)):
    movie = db.query(Movie).filter(Movie.title_id == title_id).first()
    if movie is None:
        raise HTTPException(404, "Title not found")
    return movie


@router.get("/catalogue/facets")
def catalogue_facets(db: Session = Depends(get_db)):
    """Return the media types and genres that actually exist in the catalogue."""
    media_rows = (
        db.query(Movie.media_type, func.count(Movie.title_id))
        .group_by(Movie.media_type)
        .order_by(Movie.media_type.asc())
        .all()
    )
    genre_counts: dict[str, int] = {}
    for (raw_genres,) in db.query(Movie.genres).all():
        for genre in (raw_genres or "").split("|"):
            value = genre.strip()
            if value:
                genre_counts[value] = genre_counts.get(value, 0) + 1
    return {
        "media_types": [
            {"value": media_type, "count": int(count)}
            for media_type, count in media_rows
        ],
        "genres": [
            {"value": value, "count": count}
            for value, count in sorted(
                genre_counts.items(), key=lambda item: (-item[1], item[0].casefold())
            )
        ],
    }


@router.get("/movies")
def list_movies(
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = None,
    genre: Optional[str] = None,
    media_type: Optional[str] = Query(None, pattern="^(movie|tv)$"),
    db: Session = Depends(get_db),
):
    state = db.query(CatalogueState).filter_by(id=1).first()
    version = int(state.active_version) if state else 0
    query = db.query(Movie)
    if media_type:
        query = query.filter(Movie.media_type == media_type)
    if genre:
        escaped_genre = genre.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(Movie.genres.ilike(f"%{escaped_genre}%", escape="\\"))

    last_order = None
    last_title_id = None
    if cursor:
        payload = _read_cursor(cursor)
        if int(payload.get("version", -1)) != version:
            raise HTTPException(409, "Catalogue order changed; restart pagination from the first page")
        if payload.get("genre") != genre or payload.get("media_type") != media_type:
            raise HTTPException(400, "Cursor filters do not match this request")
        last_order = int(payload["sort_order"])
        last_title_id = str(payload["title_id"])

    if version > 0:
        query = query.join(CatalogueSortIndex, and_(
            CatalogueSortIndex.title_id == Movie.title_id,
            CatalogueSortIndex.version_id == version,
        ))
        if last_order is not None:
            query = query.filter(or_(
                CatalogueSortIndex.sort_order > last_order,
                and_(CatalogueSortIndex.sort_order == last_order,
                     CatalogueSortIndex.title_id > last_title_id),
            ))
        query = query.order_by(CatalogueSortIndex.sort_order.asc(), Movie.title_id.asc())
        raw_rows = query.limit(limit + 1).all()
        has_more = len(raw_rows) > limit
        rows = raw_rows[:limit]
        last_sort_order = None
        if has_more and rows:
            last_sort_order = db.query(CatalogueSortIndex.sort_order).filter_by(
                version_id=version, title_id=rows[-1].title_id
            ).scalar()
    else:
        # First boot before the first scheduled ordering build.
        sort_key = sort_key_expression(db)
        if last_title_id:
            last = db.query(Movie.sort_key).filter(Movie.title_id == last_title_id).scalar()
            query = query.filter(or_(sort_key > last,
                                     and_(sort_key == last, Movie.title_id > last_title_id)))
        query = query.order_by(sort_key.asc(), Movie.title_id.asc())
        raw_rows = query.limit(limit + 1).all()
        has_more = len(raw_rows) > limit
        rows = raw_rows[:limit]
        last_sort_order = None
    next_cursor = None
    if rows and has_more:
        if version > 0:
            order_value = int(last_sort_order or db.query(CatalogueSortIndex.sort_order).filter_by(
                version_id=version, title_id=rows[-1].title_id
            ).scalar())
        else:
            order_value = 0
        next_cursor = _sign_cursor({
            "version": version, "sort_order": order_value,
            "title_id": rows[-1].title_id, "genre": genre, "media_type": media_type,
        })
    return {"items": [MovieOut.model_validate(row) for row in rows],
            "next_cursor": next_cursor, "catalogue_version": version}


@router.get("/search", response_model=SearchResponse)
def search_movies(q: str = Query(..., min_length=1, max_length=128),
                  limit: int = Query(20, ge=1, le=100),
                  user_id: Optional[int] = None,
                  db: Session = Depends(get_db),
                  current_user: Optional[User] = Depends(get_optional_current_user)):
    # Parameterized SQL; escape LIKE metacharacters so input is treated literally.
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    search_query = db.query(Movie).filter(Movie.title.ilike(f"%{escaped}%", escape="\\"))
    total_count = int(search_query.with_entities(func.count(Movie.title_id)).scalar() or 0)
    results = search_query.order_by(
        Movie.popularity.desc(), Movie.title_id.asc()
    ).limit(limit).all()
    if user_id is not None:
        # Search logging is optional and only accepted for the matching authenticated user.
        if current_user is None or current_user.id != user_id:
            raise HTTPException(401, "Authentication required to attach a search to a user")
        db.add(SearchLog(user_id=user_id, query=q, results_count=total_count))
        db.commit()
    return SearchResponse(query=q, count=total_count, results=results)


@router.post("/ratings", response_model=RatingOut, status_code=201)
def create_rating(payload: RatingCreate, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    movie = db.query(Movie).filter(Movie.title_id == payload.title_id).first()
    if movie is None:
        raise HTTPException(404, "Title not found")
    rating = db.query(Rating).filter_by(user_id=current_user.id, title_id=movie.title_id).first()
    if rating is None:
        rating = Rating(user_id=current_user.id, title_id=movie.title_id,
                        rating=payload.rating, relevance=payload.relevance)
        db.add(rating)
    else:
        rating.rating = payload.rating
        rating.relevance = payload.relevance
        rating.timestamp = datetime.now(timezone.utc)
    db.add(Interaction(user_id=current_user.id, title_id=movie.title_id,
                       event_type="rating", value=payload.rating))
    db.commit()
    db.refresh(rating)
    recommendation_service.invalidate_user(current_user.id)
    return rating


@router.post("/interactions", status_code=202)
def create_interaction(payload: InteractionCreate, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    movie = db.query(Movie).filter(Movie.title_id == payload.title_id).first()
    if movie is None:
        raise HTTPException(404, "Title not found")
    metadata_json = json.dumps(payload.metadata, ensure_ascii=False) if payload.metadata is not None else None
    if metadata_json and len(metadata_json) > 8000:
        raise HTTPException(413, "Interaction metadata exceeds 8 KB")
    db.add(Interaction(
        user_id=current_user.id, title_id=movie.title_id,
        event_type=payload.event_type, value=payload.value,
        metadata_json=metadata_json,
    ))
    db.commit()
    if payload.event_type != "impression":
        recommendation_service.invalidate_user(current_user.id)
    return {"status": "accepted", "title_id": movie.title_id, "event_type": payload.event_type}


@router.post("/watched/{title_id}", status_code=201)
def add_to_watched(
    title_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record that the user has watched a title."""
    movie = db.query(Movie).filter(Movie.title_id == title_id).first()
    if movie is None:
        raise HTTPException(404, "Title not found")
    # Check if already recorded
    existing = db.query(Interaction).filter_by(user_id=current_user.id, title_id=title_id, event_type="watched").first()
    if existing:
        return {"status": "already_present", "title_id": title_id}
    db.add(Interaction(
        user_id=current_user.id, title_id=title_id,
        event_type="watched", value=1.0,
    ))
    db.commit()
    recommendation_service.invalidate_user(current_user.id)
    return {"status": "accepted", "title_id": title_id}


@router.get("/users/me/preferences", response_model=UserPreferencesOut)
def get_my_preferences(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return preference_service.get(db, current_user.id)


@router.put("/users/me/preferences", response_model=UserPreferencesOut)
def update_my_preferences(
    payload: UserPreferencesIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = preference_service.replace(db, current_user.id, payload)
    recommendation_service.invalidate_user(current_user.id)
    return result


@router.get("/users/{user_id}/history", response_model=UserHistoryResponse)
def user_history(user_id: int, limit: int = Query(50, ge=1, le=200),
                 db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_self(user_id, current_user)
    total_count = int(
        db.query(func.count(Rating.id)).filter(Rating.user_id == user_id).scalar() or 0
    )
    rows = (db.query(Rating, Movie).join(Movie, Rating.title_id == Movie.title_id)
            .filter(Rating.user_id == user_id).order_by(Rating.timestamp.desc()).limit(limit).all())
    items = [HistoryItem(title_id=movie.title_id, serial_number=movie.serial_number,
                         media_type=movie.media_type, title=movie.title,
                         genres=movie.genres or "", rating=rating.rating,
                         timestamp=rating.timestamp)
             for rating, movie in rows]
    return UserHistoryResponse(user_id=user_id, count=total_count, items=items)


@router.get("/watched", response_model=list[HistoryItem])
def get_watched_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the user's watched title history."""
    rows = (db.query(Interaction, Movie).join(Movie, Interaction.title_id == Movie.title_id)
        .filter(Interaction.user_id == current_user.id, Interaction.event_type == "watched")
        .order_by(Interaction.occurred_at.desc()).all())
    items = [HistoryItem(title_id=movie.title_id, serial_number=movie.serial_number,
                         media_type=movie.media_type, title=movie.title,
                         genres=movie.genres or "", rating=0.0,
                         timestamp=Interaction.occurred_at)
             for rating, movie in rows]
    return items


@router.post("/watchlist/{title_id}", status_code=201)
def add_watchlist(title_id: str, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    movie = db.query(Movie).filter(Movie.title_id == title_id).first()
    if movie is None:
        raise HTTPException(404, "Title not found")
    existing = db.query(Watchlist).filter_by(user_id=current_user.id, title_id=title_id).first()
    if existing:
        return {"status": "already_present", "title_id": title_id}
    db.add(Watchlist(user_id=current_user.id, title_id=title_id))
    db.commit()
    recommendation_service.invalidate_user(current_user.id)
    return {"status": "added", "title_id": title_id}


@router.delete("/watchlist/{title_id}", status_code=204)
def remove_watchlist(title_id: str, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    db.query(Watchlist).filter_by(user_id=current_user.id, title_id=title_id).delete()
    db.commit()
    recommendation_service.invalidate_user(current_user.id)
    return None


@router.get("/watchlist")
def get_watchlist(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = (db.query(Watchlist, Movie).join(Movie, Watchlist.title_id == Movie.title_id)
            .filter(Watchlist.user_id == current_user.id).order_by(Watchlist.created_at.desc()).all())
    return [{"created_at": entry.created_at, "title": MovieOut.model_validate(movie)}
            for entry, movie in rows]


@router.get("/home/{user_id}")
def home_rows(user_id: int, k: int = Query(5, ge=1, le=20),
              genres: Optional[str] = Query(None), db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)):
    require_self(user_id, current_user)
    if not recommendation_service.is_ready:
        raise HTTPException(503, "No trained portable model bundle is loaded")
    genre_list = [g.strip() for g in genres.split(",") if g.strip()] if genres else ["Action", "Drama", "Comedy"]
    try:
        return recommendation_service.recommend_rows(db, user_id, k=k, genres=genre_list)
    except LookupError:
        raise HTTPException(404, "User not found")


@router.get("/home/{user_id}/more")
def load_more(user_id: int, k: int = Query(5, ge=1, le=20),
              cursor: str = Query(..., min_length=20), db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)):
    require_self(user_id, current_user)
    try:
        return recommendation_service.load_more(db, user_id, k=k, cursor=cursor)
    except InvalidPageToken as exc:
        raise HTTPException(400, str(exc)) from exc
    except LookupError:
        raise HTTPException(404, "User not found")


@router.get("/recommendations", response_model=RecommendationResponse)
def recommendations_for_current_user(
    k: int = Query(24, ge=1, le=settings.MAX_K),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Canonical recommendation endpoint; user identity comes from the access token."""
    if not recommendation_service.is_ready:
        raise HTTPException(503, "No trained portable model bundle is loaded")
    try:
        return recommendation_service.recommend(db, current_user.id, k=k)
    except LookupError as exc:
        raise HTTPException(404, "User not found") from exc


@router.get("/recommend/{user_id}", response_model=RecommendationResponse)
def recommend_legacy(user_id: int, k: int = Query(10, ge=1, le=settings.MAX_K),
                     db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_self(user_id, current_user)
    if not recommendation_service.is_ready:
        raise HTTPException(503, "No trained portable model bundle is loaded")
    try:
        return recommendation_service.recommend(db, user_id, k=k)
    except LookupError:
        raise HTTPException(404, "User not found")
