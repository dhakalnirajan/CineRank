from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import AccessTokenClaims, decode_access_token
from app.db.session import get_db
from app.models.entities import User, UserSession
from app.services.auth_service import security_log, session_is_active

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/token")
optional_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/token", auto_error=False
)


@dataclass(frozen=True)
class AuthPrincipal:
    user: User
    session: UserSession
    claims: AccessTokenClaims


def _unauthorized(detail: str = "Invalid or expired access token") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _authenticate_access_token(token: str, db: Session) -> AuthPrincipal:
    claims = decode_access_token(token)
    if claims is None:
        raise _unauthorized()

    session = db.query(UserSession).filter(UserSession.id == claims.session_id).first()
    now = datetime.now(timezone.utc)
    if session is None or not session_is_active(session, now):
        security_log(
            "access_invalid_session",
            user_id=claims.user_id,
            session_id=claims.session_id,
        )
        raise _unauthorized()
    if session.user_id != claims.user_id:
        security_log(
            "access_session_owner_mismatch",
            user_id=claims.user_id,
            session_id=claims.session_id,
        )
        raise _unauthorized()

    user = (
        db.query(User)
        .filter(User.id == claims.user_id, User.is_active.is_(True))
        .first()
    )
    if user is None:
        security_log("access_inactive_or_unknown_user", user_id=claims.user_id)
        raise _unauthorized()
    return AuthPrincipal(user=user, session=session, claims=claims)


def get_auth_principal(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> AuthPrincipal:
    return _authenticate_access_token(token, db)


def get_current_user(principal: AuthPrincipal = Depends(get_auth_principal)) -> User:
    return principal.user


def get_current_session(
    principal: AuthPrincipal = Depends(get_auth_principal),
) -> UserSession:
    return principal.session


def get_optional_current_user(
    token: str | None = Depends(optional_oauth2_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    if not token:
        return None
    return _authenticate_access_token(token, db).user


def require_self(user_id: int, current_user: User) -> None:
    if int(user_id) != int(current_user.id):
        security_log("authorization_owner_mismatch", user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may only access your own account data",
        )


def validate_cookie_request_origin(request: Request) -> None:
    """CSRF defense for cookie-authenticated endpoints.

    Browsers send Origin on cross-site and same-site POST requests. Production
    rejects a missing Origin as well as unknown origins. Development and test
    allow missing Origin for command-line clients, but never an unknown origin.
    """
    origin = request.headers.get("origin")
    production = settings.ENVIRONMENT.strip().lower() == "production"
    if not origin:
        if production:
            security_log("csrf_missing_origin")
            raise HTTPException(status_code=403, detail="Request origin is required")
        return
    if origin == "null" or origin not in settings.cors_origin_list:
        security_log("csrf_origin_rejected", origin=origin)
        raise HTTPException(status_code=403, detail="Request origin is not allowed")
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        security_log("csrf_cross_site_rejected", origin=origin)
        raise HTTPException(status_code=403, detail="Cross-site request is not allowed")
