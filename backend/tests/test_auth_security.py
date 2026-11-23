import base64
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, settings, validate_security_settings
from app.core.rate_limit import auth_rate_limiter, request_rate_limiter
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
    verify_password_and_update,
)
from app.db.session import Base, get_db
from app.main import app
from app.models.entities import Movie, Rating, User, UserSession
from app.services import auth_service

PASSWORD = "correct-horse-battery-staple"
ALLOWED_ORIGIN = "http://localhost:5173"


@pytest.fixture()
def api(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    auth_rate_limiter.reset()
    request_rate_limiter.reset()
    with TestClient(app) as client:
        yield client, TestingSession
    app.dependency_overrides.clear()
    auth_rate_limiter.reset()
    request_rate_limiter.reset()
    Base.metadata.drop_all(engine)
    engine.dispose()


def create_user(SessionFactory, username="ada", password=PASSWORD, active=True) -> int:
    db = SessionFactory()
    try:
        user = User(
            username=username,
            email=f"{username}@example.com",
            password_hash=hash_password(password),
            is_active=active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return int(user.id)
    finally:
        db.close()


def login(client: TestClient, username="ada", password=PASSWORD, **kwargs):
    return client.post(
        "/api/v1/auth/token",
        data={"username": username, "password": password},
        **kwargs,
    )


def bearer(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def decode(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.JWT_ALGORITHM],
        audience=settings.JWT_AUDIENCE,
        issuer=settings.JWT_ISSUER,
    )


def set_cookie(client: TestClient, value: str) -> None:
    client.cookies.clear()
    client.cookies.set(
        settings.AUTH_COOKIE_NAME,
        value,
        path=settings.AUTH_COOKIE_PATH,
    )


def claims_for(user_id: int, session_id: str, **overrides: Any) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": now,
        "nbf": now - timedelta(seconds=1),
        "exp": now + timedelta(minutes=5),
        "jti": secrets.token_urlsafe(16),
        "sid": session_id,
        "type": "access",
    }
    claims.update(overrides)
    return claims


def custom_access(claims: dict[str, Any], key: str | None = None, algorithm: str = "HS256") -> str:
    return jwt.encode(claims, key or settings.jwt_secret_key, algorithm=algorithm)


class TestPasswordSecurity:
    def test_hash_verify_and_safe_failure(self):
        encoded = hash_password(PASSWORD)
        assert encoded.startswith("$argon2id$")
        assert PASSWORD not in encoded
        assert verify_password(PASSWORD, encoded)
        assert not verify_password("wrong-password", encoded)
        assert not verify_password(PASSWORD, None)
        assert not verify_password("x" * (settings.PASSWORD_MAX_LENGTH + 1), encoded)

    def test_hash_upgrade_for_weaker_parameters(self):
        salt = secrets.token_bytes(16)
        derived = hashlib.scrypt(
            PASSWORD.encode(), salt=salt, n=2**14, r=8, p=1, dklen=64
        )
        legacy = (
            "scrypt$16384$8$1$"
            + base64.urlsafe_b64encode(salt).decode()
            + "$"
            + base64.urlsafe_b64encode(derived).decode()
        )

        valid, replacement = verify_password_and_update(PASSWORD, legacy)

        assert valid
        assert replacement is not None
        assert replacement != legacy
        assert replacement.startswith("$argon2id$")
        assert verify_password(PASSWORD, replacement)

    def test_passwords_outside_limits_are_rejected(self):
        with pytest.raises(ValueError):
            hash_password("short")
        with pytest.raises(ValueError):
            hash_password("x" * (settings.PASSWORD_MAX_LENGTH + 1))


class TestRegistrationAndLogin:
    def test_registration_hashes_password_and_hides_it(self, api):
        client, SessionFactory = api
        response = client.post(
            "/api/v1/auth/register",
            json={"username": "new-user", "email": "new@example.com", "password": PASSWORD},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["username"] == "new-user"
        assert "password" not in body
        assert "password_hash" not in body

        db = SessionFactory()
        try:
            user = db.query(User).filter(User.username == "new-user").one()
            assert user.password_hash != PASSWORD
            assert verify_password(PASSWORD, user.password_hash)
        finally:
            db.close()

    def test_duplicate_registration_and_invalid_payload(self, api):
        client, _SessionFactory = api
        payload = {"username": "duplicate", "password": PASSWORD}
        assert client.post("/api/v1/auth/register", json=payload).status_code == 201
        assert client.post("/api/v1/auth/register", json=payload).status_code == 409
        assert (
            client.post(
                "/api/v1/auth/register",
                json={"username": "x", "password": "short"},
            ).status_code
            == 422
        )

    def test_login_creates_session_and_sets_secure_cookie_attributes(self, api):
        client, SessionFactory = api
        user_id = create_user(SessionFactory)

        response = login(
            client,
            headers={"User-Agent": "CineRank test browser"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        assert "refresh" not in body
        token_claims = decode(body["access_token"])
        assert token_claims["sub"] == str(user_id)
        assert token_claims["type"] == "access"
        assert token_claims["iss"] == settings.JWT_ISSUER
        assert token_claims["aud"] == settings.JWT_AUDIENCE

        set_cookie_header = response.headers["set-cookie"]
        assert f"{settings.AUTH_COOKIE_NAME}=" in set_cookie_header
        assert "HttpOnly" in set_cookie_header
        assert f"Path={settings.AUTH_COOKIE_PATH}" in set_cookie_header
        assert "SameSite=lax" in set_cookie_header

        db = SessionFactory()
        try:
            session = db.query(UserSession).one()
            assert session.user_id == user_id
            assert len(session.refresh_token_hash) == 64
            assert session.refresh_token_hash not in set_cookie_header
            assert session.id == token_claims["sid"]
        finally:
            db.close()

        me = client.get("/api/v1/auth/me", headers=bearer(body["access_token"]))
        assert me.status_code == 200
        assert me.json()["id"] == user_id

    def test_login_failures_are_generic_and_do_not_create_sessions(self, api):
        client, SessionFactory = api
        create_user(SessionFactory, username="ada")
        create_user(SessionFactory, username="inactive", active=False)

        wrong = login(client, password="wrong-password")
        unknown = login(client, username="nobody")
        inactive = login(client, username="inactive")

        assert wrong.status_code == unknown.status_code == inactive.status_code == 401
        assert wrong.json()["detail"] == unknown.json()["detail"] == inactive.json()["detail"]

        db = SessionFactory()
        try:
            assert db.query(UserSession).count() == 0
        finally:
            db.close()


class TestAccessJwtValidation:
    def test_expired_wrong_issuer_audience_type_algorithm_and_signature_are_rejected(self, api):
        client, SessionFactory = api
        user_id = create_user(SessionFactory)
        login_response = login(client)
        token = login_response.json()["access_token"]
        session_id = decode(token)["sid"]

        assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 200

        now = datetime.now(timezone.utc)
        invalid_tokens = [
            custom_access(
                claims_for(
                    user_id,
                    session_id,
                    exp=now - timedelta(seconds=settings.JWT_LEEWAY_SECONDS + 5),
                )
            ),
            custom_access(claims_for(user_id, session_id, iss="Other Issuer")),
            custom_access(claims_for(user_id, session_id, aud="Other Audience")),
            custom_access(claims_for(user_id, session_id, type="refresh")),
            custom_access(claims_for(user_id, session_id), key="different-secret-key-" * 4),
            custom_access(claims_for(user_id, session_id), key="x" * 64, algorithm="HS512"),
        ]
        for invalid in invalid_tokens:
            assert client.get("/api/v1/auth/me", headers=bearer(invalid)).status_code == 401

        missing_subject = claims_for(user_id, session_id)
        missing_subject.pop("sub")
        assert (
            client.get(
                "/api/v1/auth/me", headers=bearer(custom_access(missing_subject))
            ).status_code
            == 401
        )

    def test_unknown_revoked_and_expired_sessions_are_rejected(self, api):
        client, SessionFactory = api
        user_id = create_user(SessionFactory)
        token = login(client).json()["access_token"]
        session_id = decode(token)["sid"]

        assert (
            client.get(
                "/api/v1/auth/me",
                headers=bearer(create_access_token(str(user_id), "unknown-session")),
            ).status_code
            == 401
        )

        db = SessionFactory()
        try:
            session = db.query(UserSession).filter_by(id=session_id).one()
            session.revoked_at = datetime.now(timezone.utc)
            db.commit()
        finally:
            db.close()
        assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 401

        second_token = login(client).json()["access_token"]
        second_session = decode(second_token)["sid"]
        db = SessionFactory()
        try:
            session = db.query(UserSession).filter_by(id=second_session).one()
            session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        finally:
            db.close()
        assert client.get("/api/v1/auth/me", headers=bearer(second_token)).status_code == 401

    def test_inactive_account_cannot_use_its_existing_access_token(self, api):
        client, SessionFactory = api
        user_id = create_user(SessionFactory)
        token = login(client).json()["access_token"]

        db = SessionFactory()
        try:
            user = db.query(User).filter_by(id=user_id).one()
            user.is_active = False
            db.commit()
        finally:
            db.close()

        assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 401


class TestRefreshRotationAndReuse:
    def test_refresh_rotates_token_and_keeps_one_active_session(self, api):
        client, SessionFactory = api
        create_user(SessionFactory)
        first = login(client)
        first_refresh = first.cookies.get(settings.AUTH_COOKIE_NAME)
        assert first_refresh

        db = SessionFactory()
        try:
            initial_expiry = db.query(UserSession).one().expires_at
        finally:
            db.close()

        response = client.post(
            "/api/v1/auth/refresh",
            headers={"Origin": ALLOWED_ORIGIN},
        )

        assert response.status_code == 200
        second_refresh = response.cookies.get(settings.AUTH_COOKIE_NAME)
        assert second_refresh and second_refresh != first_refresh
        assert response.json()["access_token"] != first.json()["access_token"]
        assert client.get(
            "/api/v1/auth/me", headers=bearer(response.json()["access_token"])
        ).status_code == 200

        db = SessionFactory()
        try:
            assert db.query(UserSession).count() == 1
            session = db.query(UserSession).one()
            assert session.revoked_at is None
            assert session.expires_at > initial_expiry
        finally:
            db.close()

    def test_immediate_old_token_replay_is_concurrency_not_theft(self, api):
        client, SessionFactory = api
        create_user(SessionFactory)
        first_refresh = login(client).cookies.get(settings.AUTH_COOKIE_NAME)
        assert first_refresh
        rotated = client.post(
            "/api/v1/auth/refresh", headers={"Origin": ALLOWED_ORIGIN}
        )
        assert rotated.status_code == 200

        set_cookie(client, first_refresh)
        replay = client.post(
            "/api/v1/auth/refresh", headers={"Origin": ALLOWED_ORIGIN}
        )

        assert replay.status_code == 401
        db = SessionFactory()
        try:
            session = db.query(UserSession).one()
            assert session.revoked_at is None
        finally:
            db.close()

    def test_old_token_replay_after_grace_revokes_session(self, api):
        client, SessionFactory = api
        create_user(SessionFactory)
        first_refresh = login(client).cookies.get(settings.AUTH_COOKIE_NAME)
        assert first_refresh
        assert client.post(
            "/api/v1/auth/refresh", headers={"Origin": ALLOWED_ORIGIN}
        ).status_code == 200

        db = SessionFactory()
        try:
            session = db.query(UserSession).one()
            session.last_used_at = datetime.now(timezone.utc) - timedelta(minutes=5)
            db.commit()
        finally:
            db.close()

        set_cookie(client, first_refresh)
        response = client.post(
            "/api/v1/auth/refresh", headers={"Origin": ALLOWED_ORIGIN}
        )

        assert response.status_code == 401
        db = SessionFactory()
        try:
            session = db.query(UserSession).one()
            assert session.revoked_at is not None
        finally:
            db.close()

    def test_invalid_and_expired_refresh_tokens_clear_the_cookie(self, api):
        client, SessionFactory = api
        create_user(SessionFactory)

        set_cookie(client, "not-a-valid-token")
        response = client.post(
            "/api/v1/auth/refresh", headers={"Origin": ALLOWED_ORIGIN}
        )
        assert response.status_code == 401
        assert settings.AUTH_COOKIE_NAME in response.headers.get("set-cookie", "")

        login_response = login(client)
        assert login_response.status_code == 200
        db = SessionFactory()
        try:
            session = db.query(UserSession).one()
            session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        finally:
            db.close()
        expired = client.post(
            "/api/v1/auth/refresh", headers={"Origin": ALLOWED_ORIGIN}
        )
        assert expired.status_code == 401

    def test_inactive_user_cannot_refresh(self, api):
        client, SessionFactory = api
        user_id = create_user(SessionFactory)
        assert login(client).status_code == 200

        db = SessionFactory()
        try:
            user = db.query(User).filter_by(id=user_id).one()
            user.is_active = False
            db.commit()
        finally:
            db.close()

        response = client.post(
            "/api/v1/auth/refresh", headers={"Origin": ALLOWED_ORIGIN}
        )
        assert response.status_code == 401
        db = SessionFactory()
        try:
            assert db.query(UserSession).one().revoked_at is not None
        finally:
            db.close()


class TestLogoutAndSessionManagement:
    def test_logout_revokes_current_session_and_old_refresh_fails(self, api):
        client, SessionFactory = api
        create_user(SessionFactory)
        login_response = login(client)
        refresh_token = login_response.cookies.get(settings.AUTH_COOKIE_NAME)

        response = client.post("/api/v1/auth/logout", headers={"Origin": ALLOWED_ORIGIN})

        assert response.status_code == 200
        assert settings.AUTH_COOKIE_NAME in response.headers.get("set-cookie", "")
        db = SessionFactory()
        try:
            assert db.query(UserSession).one().revoked_at is not None
        finally:
            db.close()

        set_cookie(client, refresh_token or "")
        assert (
            client.post(
                "/api/v1/auth/refresh", headers={"Origin": ALLOWED_ORIGIN}
            ).status_code
            == 401
        )

    def test_logout_all_revokes_every_session(self, api):
        client, SessionFactory = api
        create_user(SessionFactory)
        login(client)
        second = login(client)
        token = second.json()["access_token"]

        response = client.post("/api/v1/auth/logout-all", headers=bearer(token))

        assert response.status_code == 200
        assert response.json()["revoked"] == 2
        db = SessionFactory()
        try:
            sessions = db.query(UserSession).all()
            assert len(sessions) == 2
            assert all(session.revoked_at is not None for session in sessions)
        finally:
            db.close()

    def test_session_listing_is_safe_and_marks_current(self, api):
        client, SessionFactory = api
        create_user(SessionFactory)
        login(client)
        second = login(client)

        response = client.get(
            "/api/v1/auth/sessions", headers=bearer(second.json()["access_token"])
        )

        assert response.status_code == 200
        sessions = response.json()
        assert len(sessions) == 2
        assert sum(1 for session in sessions if session["current"]) == 1
        assert all("refresh_token_hash" not in session for session in sessions)
        assert all("user_agent" in session for session in sessions)

    def test_cross_user_session_revocation_is_rejected(self, api):
        client, SessionFactory = api
        create_user(SessionFactory, username="ada")
        create_user(SessionFactory, username="grace")
        ada_token = login(client).json()["access_token"]

        client.cookies.clear()
        assert login(client, username="grace").status_code == 200
        grace_refresh = client.cookies.get(settings.AUTH_COOKIE_NAME)
        db = SessionFactory()
        try:
            grace_session = (
                db.query(UserSession)
                .join(User, User.id == UserSession.user_id)
                .filter(User.username == "grace")
                .one()
            )
            grace_session_id = grace_session.id
        finally:
            db.close()
        assert grace_refresh

        response = client.delete(
            f"/api/v1/auth/sessions/{grace_session_id}", headers=bearer(ada_token)
        )

        assert response.status_code == 404
        db = SessionFactory()
        try:
            assert (
                db.query(UserSession).filter_by(id=grace_session_id).one().revoked_at
                is None
            )
        finally:
            db.close()

    def test_owner_can_revoke_a_selected_session(self, api):
        client, SessionFactory = api
        create_user(SessionFactory)
        login(client)
        second = login(client)
        token = second.json()["access_token"]
        other_session = (
            client.get("/api/v1/auth/sessions", headers=bearer(token)).json()
        )
        target = next(session for session in other_session if not session["current"])

        response = client.delete(
            f"/api/v1/auth/sessions/{target['id']}", headers=bearer(token)
        )

        assert response.status_code == 204
        db = SessionFactory()
        try:
            assert db.query(UserSession).filter_by(id=target["id"]).one().revoked_at is not None
        finally:
            db.close()


class TestAuthorizationAndRequestProtection:
    def test_cross_user_history_access_is_forbidden(self, api):
        client, SessionFactory = api
        create_user(SessionFactory, username="ada")
        other_id = create_user(SessionFactory, username="grace")
        token = login(client).json()["access_token"]

        response = client.get(
            f"/api/v1/users/{other_id}/history", headers=bearer(token)
        )

        assert response.status_code == 403

    def test_history_count_is_total_even_when_items_are_limited(self, api):
        client, SessionFactory = api
        user_id = create_user(SessionFactory)
        db = SessionFactory()
        try:
            movies = [Movie(title=f"History title {index}", genres="Drama") for index in range(3)]
            db.add_all(movies)
            db.flush()
            db.add_all([
                Rating(user_id=user_id, title_id=movie.title_id, rating=4.0 + index * 0.5, relevance=1.0)
                for index, movie in enumerate(movies)
            ])
            db.commit()
        finally:
            db.close()

        token = login(client).json()["access_token"]
        response = client.get(
            f"/api/v1/users/{user_id}/history?limit=1", headers=bearer(token)
        )

        assert response.status_code == 200
        assert response.json()["count"] == 3
        assert len(response.json()["items"]) == 1

    def test_refresh_rejects_unknown_origin(self, api):
        client, SessionFactory = api
        create_user(SessionFactory)
        assert login(client).status_code == 200

        response = client.post(
            "/api/v1/auth/refresh", headers={"Origin": "https://evil.example"}
        )

        assert response.status_code == 403
        db = SessionFactory()
        try:
            assert db.query(UserSession).one().revoked_at is None
        finally:
            db.close()

    def test_login_rate_limit_returns_429(self, api, monkeypatch):
        client, SessionFactory = api
        create_user(SessionFactory)
        monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_LOGIN_PER_MINUTE", 2)
        auth_rate_limiter.reset()

        assert login(client, password="wrong-password").status_code == 401
        assert login(client, password="wrong-password").status_code == 401
        limited = login(client)

        assert limited.status_code == 429
        assert "Retry-After" in limited.headers

    def test_security_logs_do_not_contain_credentials(self, api, caplog):
        client, SessionFactory = api
        create_user(SessionFactory)
        caplog.set_level(logging.INFO, logger="cinerank.security")
        response = login(client)
        token = response.json()["access_token"]

        assert response.status_code == 200
        assert PASSWORD not in caplog.text
        assert token not in caplog.text


class TestProfileAndSessionManagement:
    def test_email_and_password_changes_require_current_password(self, api):
        client, SessionFactory = api
        user_id = create_user(SessionFactory)
        token = login(client).json()["access_token"]
        headers = bearer(token)

        denied = client.patch(
            f"/api/v1/users/{user_id}",
            headers=headers,
            json={"email": "new-address@example.com"},
        )
        assert denied.status_code == 403

        changed = client.patch(
            f"/api/v1/users/{user_id}",
            headers=headers,
            json={
                "email": "new-address@example.com",
                "current_password": PASSWORD,
                "password": "new-correct-horse-battery-staple",
            },
        )
        assert changed.status_code == 200
        assert changed.json()["email"] == "new-address@example.com"
        assert "password_hash" not in changed.json()
        db = SessionFactory()
        try:
            user = db.query(User).filter(User.id == user_id).one()
            assert verify_password("new-correct-horse-battery-staple", user.password_hash)
        finally:
            db.close()

    def test_logout_other_sessions_preserves_current_and_revokes_the_rest(self, api):
        client, SessionFactory = api
        user_id = create_user(SessionFactory)
        login(client)
        first_session_id = decode(
            client.post("/api/v1/auth/refresh", headers={"Origin": ALLOWED_ORIGIN}).json()["access_token"]
        )["sid"]
        client.cookies.clear()
        login(client)
        current_token = login(client).json()["access_token"]
        current_session_id = decode(current_token)["sid"]

        response = client.post("/api/v1/auth/logout-others", headers=bearer(current_token))
        assert response.status_code == 200
        assert response.json()["revoked"] >= 1

        db = SessionFactory()
        try:
            sessions = db.query(UserSession).filter(UserSession.user_id == user_id).all()
            current = next(row for row in sessions if row.id == current_session_id)
            first = next(row for row in sessions if row.id == first_session_id)
            assert current.revoked_at is None
            assert first.revoked_at is not None
        finally:
            db.close()

    def test_avatar_upload_reencodes_valid_image_as_webp(self, api, monkeypatch, tmp_path):
        from io import BytesIO
        from PIL import Image
        from app.core.config import settings

        client, _SessionFactory = api
        create_user(_SessionFactory)
        token = login(client).json()["access_token"]
        monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
        image_bytes = BytesIO()
        Image.new("RGB", (64, 64), color=(220, 20, 40)).save(image_bytes, format="PNG")

        response = client.post(
            "/api/v1/users/me/avatar",
            headers=bearer(token),
            files={"image": ("avatar.png", image_bytes.getvalue(), "image/png")},
        )
        assert response.status_code == 200
        avatar_url = response.json()["avatar_url"]
        assert avatar_url.startswith("/media/avatars/") and avatar_url.endswith(".webp")
        stored = tmp_path / "media" / "avatars" / avatar_url.rsplit("/", 1)[-1]
        assert stored.is_file()
        assert stored.read_bytes().startswith(b"RIFF")


class TestProductionConfiguration:
    def test_production_rejects_unsafe_cookie_and_secret_configuration(self):
        with pytest.raises(RuntimeError):
            validate_security_settings(
                Settings(
                    _env_file=None,
                    ENVIRONMENT="production",
                    SECRET_KEY="x" * 64,
                    JWT_SECRET_KEY="y" * 64,
                    AUTH_COOKIE_SECURE=False,
                )
            )
        with pytest.raises(RuntimeError):
            validate_security_settings(
                Settings(
                    _env_file=None,
                    ENVIRONMENT="production",
                    SECRET_KEY="REPLACE_ME",
                    JWT_SECRET_KEY="y" * 64,
                    AUTH_COOKIE_SECURE=True,
                )
            )

    def test_valid_production_configuration_is_accepted(self):
        validate_security_settings(
            Settings(
                _env_file=None,
                ENVIRONMENT="production",
                SECRET_KEY="x" * 64,
                JWT_SECRET_KEY="y" * 64,
                AUTH_COOKIE_SECURE=True,
                AUTH_COOKIE_HTTPONLY=True,
                AUTH_COOKIE_SAMESITE="lax",
                ACCESS_TOKEN_EXPIRE_MINUTES=10,
                CORS_ORIGINS="https://cinerank.example",
                FRONTEND_BASE_URL="https://cinerank.example",
                REDIS_URL="redis://localhost:6379/0",
            )
        )


def test_user_preferences_are_private_persisted_and_normalized(api):
    client, SessionFactory = api
    user_id = create_user(SessionFactory)
    response = login(client)
    assert response.status_code == 200
    headers = bearer(response.json()["access_token"])

    initial = client.get("/api/v1/users/me/preferences", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["include_adult"] is False
    assert initial.json()["preferred_genres"] == []

    updated = client.put("/api/v1/users/me/preferences", headers=headers, json={
        "preferred_genres": [" Drama ", "drama", "Science Fiction"],
        "excluded_genres": ["Comedy"],
        "include_adult": False,
        "min_year": 1990,
        "max_runtime": 180,
    })
    assert updated.status_code == 200
    assert updated.json()["preferred_genres"] == ["Drama", "Science Fiction"]
    assert updated.json()["excluded_genres"] == ["Comedy"]
    assert updated.json()["min_year"] == 1990

    db = SessionFactory()
    try:
        from app.models.entities import UserPreference
        row = db.query(UserPreference).filter_by(user_id=user_id).one()
        assert '"Science Fiction"' in row.preferred_genres_json
    finally:
        db.close()


def test_preferences_are_scoped_to_the_authenticated_identity(api):
    client, SessionFactory = api
    create_user(SessionFactory, username="ada")
    create_user(SessionFactory, username="grace")
    ada_headers = bearer(login(client, username="ada").json()["access_token"])
    grace_headers = bearer(login(client, username="grace").json()["access_token"])

    updated = client.put("/api/v1/users/me/preferences", headers=ada_headers, json={
        "preferred_genres": ["Drama"],
        "excluded_genres": [],
        "include_adult": False,
        "min_year": None,
        "max_runtime": None,
    })
    assert updated.status_code == 200

    ada = client.get("/api/v1/users/me/preferences", headers=ada_headers)
    grace = client.get("/api/v1/users/me/preferences", headers=grace_headers)
    assert ada.json()["preferred_genres"] == ["Drama"]
    assert grace.json()["preferred_genres"] == []


def test_watchlist_is_scoped_to_the_authenticated_owner(api):
    client, SessionFactory = api
    create_user(SessionFactory, username="ada")
    create_user(SessionFactory, username="grace")
    db = SessionFactory()
    try:
        movie = Movie(title="Shared catalogue title", genres="Drama")
        db.add(movie)
        db.commit()
        db.refresh(movie)
        title_id = movie.title_id
    finally:
        db.close()

    ada_headers = bearer(login(client, username="ada").json()["access_token"])
    grace_headers = bearer(login(client, username="grace").json()["access_token"])

    assert client.post(f"/api/v1/watchlist/{title_id}", headers=ada_headers).status_code == 201
    assert len(client.get("/api/v1/watchlist", headers=ada_headers).json()) == 1
    assert client.get("/api/v1/watchlist", headers=grace_headers).json() == []

    # Deleting a title from another account's watchlist must not remove it there.
    assert client.delete(f"/api/v1/watchlist/{title_id}", headers=grace_headers).status_code == 204
    assert len(client.get("/api/v1/watchlist", headers=ada_headers).json()) == 1


def test_user_preferences_reject_invalid_ranges(api):
    client, SessionFactory = api
    create_user(SessionFactory)
    response = login(client)
    headers = bearer(response.json()["access_token"])
    invalid = client.put("/api/v1/users/me/preferences", headers=headers, json={
        "preferred_genres": [], "excluded_genres": [], "include_adult": False,
        "min_year": 1700, "max_runtime": 900,
    })
    assert invalid.status_code == 422


def test_request_policy_adds_request_id_and_security_headers(api):
    client, _ = api
    response = client.get("/api/v1/health/live", headers={"X-Request-ID": "cinerank-test-123"})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "cinerank-test-123"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_canonical_recommendation_route_uses_authenticated_identity(api, monkeypatch):
    from datetime import datetime, timezone
    from app.schemas.schemas import RecommendationResponse
    from app.services.recommendation_service import recommendation_service

    client, SessionFactory = api
    user_id = create_user(SessionFactory)
    token_response = login(client)
    headers = bearer(token_response.json()["access_token"])
    captured = {}

    monkeypatch.setattr(recommendation_service, "is_ready", True)
    def fake_recommend(db, requested_user_id, k):
        captured["user_id"] = requested_user_id
        captured["k"] = k
        return RecommendationResponse(
            user_id=requested_user_id, model="test", k=0, items=[],
            generated_at=datetime.now(timezone.utc),
        )
    monkeypatch.setattr(recommendation_service, "recommend", fake_recommend)

    response = client.get("/api/v1/recommendations?k=7&user_id=999", headers=headers)
    assert response.status_code == 200
    assert captured == {"user_id": user_id, "k": 7}


def test_distributed_rate_limiter_uses_hashed_redis_keys(monkeypatch):
    import app.core.rate_limit as rate_limit_module

    class FakeRedis:
        def __init__(self):
            self.calls = []
        def eval(self, script, key_count, key, *args):
            self.calls.append((script, key_count, key, args))
            return 0

    fake = FakeRedis()
    monkeypatch.setattr(rate_limit_module, "get_redis", lambda: fake)
    limiter = rate_limit_module.DistributedRateLimiter()
    assert limiter.check("login:identity:ada@example.com", 5) is None
    assert len(fake.calls) == 1
    assert "ada@example.com" not in fake.calls[0][2]
    assert fake.calls[0][1] == 1


def test_production_rate_limiter_fails_closed_when_redis_unavailable(monkeypatch):
    import app.core.rate_limit as rate_limit_module

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(rate_limit_module, "get_redis", lambda: (_ for _ in ()).throw(ConnectionError("down")))
    limiter = rate_limit_module.DistributedRateLimiter()
    assert limiter.check("login:ip:127.0.0.1", 5, 60) == 60


def test_registration_uses_hourly_ip_and_identity_quota(api, monkeypatch):
    client, _ = api
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_REGISTER_PER_HOUR", 1)
    first = client.post("/api/v1/auth/register", json={
        "username": "hourly-one", "email": "hourly-one@example.com",
        "password": "CorrectHorseBattery12!",
    })
    second = client.post("/api/v1/auth/register", json={
        "username": "hourly-two", "email": "hourly-two@example.com",
        "password": "CorrectHorseBattery12!",
    })
    assert first.status_code == 201
    assert second.status_code == 429
    assert second.headers.get("Retry-After")


class TestEmailVerificationAndPasswordReset:
    def test_registration_sends_hashed_token_and_verify_is_single_use(self, api, monkeypatch):
        from app.models.entities import EmailActionToken
        from app.services import email_service

        client, SessionFactory = api
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.test")
        monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "no-reply@example.test")
        captured = {}
        monkeypatch.setattr(
            email_service,
            "send_verification_email",
            lambda address, token: captured.update(address=address, token=token),
        )

        registered = client.post(
            "/api/v1/auth/register",
            json={"username": "verify-me", "email": "verify@example.com", "password": PASSWORD},
        )
        assert registered.status_code == 201
        assert registered.json()["email_verified"] is False
        assert captured["address"] == "verify@example.com"

        db = SessionFactory()
        try:
            stored = db.query(EmailActionToken).one()
            assert stored.token_hash != captured["token"]
            assert captured["token"] not in stored.token_hash
            assert stored.purpose == "verify_email"
        finally:
            db.close()

        verified = client.post("/api/v1/auth/email/verify", json={"token": captured["token"]})
        assert verified.status_code == 200
        assert verified.json()["email_verified"] is True

        replay = client.post("/api/v1/auth/email/verify", json={"token": captured["token"]})
        assert replay.status_code == 400

    def test_verification_link_does_not_confirm_a_changed_email(self, api, monkeypatch):
        from app.services import email_service

        client, SessionFactory = api
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.test")
        monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "no-reply@example.test")
        captured = {}
        monkeypatch.setattr(
            email_service,
            "send_verification_email",
            lambda address, token: captured.update(address=address, token=token),
        )

        assert client.post(
            "/api/v1/auth/register",
            json={"username": "moving-email", "email": "old@example.com", "password": PASSWORD},
        ).status_code == 201
        db = SessionFactory()
        try:
            user = db.query(User).filter(User.username == "moving-email").one()
            user.email = "new@example.com"
            db.commit()
        finally:
            db.close()

        rejected = client.post(
            "/api/v1/auth/email/verify", json={"token": captured["token"]}
        )

        assert rejected.status_code == 400
        db = SessionFactory()
        try:
            user = db.query(User).filter(User.username == "moving-email").one()
            assert user.email_verified_at is None
        finally:
            db.close()

    def test_password_reset_revokes_sessions_and_changes_password(self, api, monkeypatch):
        from app.services import email_service

        client, SessionFactory = api
        create_user(SessionFactory, username="reset-user")
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.test")
        monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "no-reply@example.test")
        captured = {}
        monkeypatch.setattr(
            email_service,
            "send_password_reset_email",
            lambda address, token: captured.update(address=address, token=token),
        )

        assert login(client, username="reset-user").status_code == 200
        requested = client.post(
            "/api/v1/auth/password/forgot", json={"email": "reset-user@example.com"}
        )
        assert requested.status_code == 202
        assert requested.json()["status"] == "reset_link_sent"
        assert captured["address"] == "reset-user@example.com"

        new_password = "new-correct-horse-battery-staple"
        reset = client.post(
            "/api/v1/auth/password/reset",
            json={"token": captured["token"], "new_password": new_password},
        )
        assert reset.status_code == 200
        assert reset.json()["status"] == "password_reset"

        db = SessionFactory()
        try:
            assert all(session.revoked_at is not None for session in db.query(UserSession).all())
        finally:
            db.close()

        client.cookies.clear()
        assert login(client, username="reset-user").status_code == 401
        assert login(client, username="reset-user", password=new_password).status_code == 200

    def test_password_forgot_is_generic_for_unknown_accounts(self, api, monkeypatch):
        from app.services import email_service

        client, _SessionFactory = api
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.test")
        monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "no-reply@example.test")
        sent = []
        monkeypatch.setattr(
            email_service,
            "send_password_reset_email",
            lambda address, token: sent.append(address),
        )

        response = client.post(
            "/api/v1/auth/password/forgot", json={"email": "missing@example.com"}
        )

        assert response.status_code == 202
        assert response.json()["status"] == "reset_link_sent"
        assert sent == []

    def test_email_endpoints_report_unconfigured_delivery(self, api, monkeypatch):
        client, _SessionFactory = api
        monkeypatch.setattr(settings, "SMTP_HOST", "")

        response = client.post(
            "/api/v1/auth/password/forgot", json={"email": "someone@example.com"}
        )

        assert response.status_code == 503

    def test_changing_email_clears_verified_state(self, api):
        client, SessionFactory = api
        user_id = create_user(SessionFactory)
        db = SessionFactory()
        try:
            user = db.query(User).filter(User.id == user_id).one()
            user.email_verified_at = datetime.now(timezone.utc)
            db.commit()
        finally:
            db.close()

        token = login(client).json()["access_token"]
        changed = client.patch(
            f"/api/v1/users/{user_id}",
            headers=bearer(token),
            json={"email": "changed@example.com", "current_password": PASSWORD},
        )

        assert changed.status_code == 200
        assert changed.json()["email"] == "changed@example.com"
        assert changed.json()["email_verified"] is False


def test_user_preference_constraints_are_enforced_by_database(api):
    from sqlalchemy.exc import IntegrityError
    from app.models.entities import UserPreference

    _client, SessionFactory = api
    user_id = create_user(SessionFactory)
    db = SessionFactory()
    try:
        db.add(UserPreference(user_id=user_id, min_year=1700))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.close()
