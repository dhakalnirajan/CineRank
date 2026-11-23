"""Typed runtime configuration. Secrets must be supplied through environment variables."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", case_sensitive=True, extra="ignore")

    PROJECT_NAME: str = "CineRank Recommendation Service"
    VERSION: str = "2.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "CHANGE-ME-IN-PRODUCTION-USE-A-RANDOM-64-CHARACTER-SECRET"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173"

    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "CineRank"
    JWT_AUDIENCE: str = "CineRank API"
    JWT_LEEWAY_SECONDS: int = 5
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15

    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    AUTH_REFRESH_REUSE_GRACE_SECONDS: int = 10
    AUTH_COOKIE_NAME: str = "cinerank_refresh"
    AUTH_COOKIE_PATH: str = "/api/v1/auth"
    AUTH_COOKIE_SECURE: bool = False
    AUTH_COOKIE_HTTPONLY: bool = True
    AUTH_COOKIE_SAMESITE: str = "lax"
    AUTH_COOKIE_DOMAIN: str | None = None

    PASSWORD_MIN_LENGTH: int = 12
    PASSWORD_MAX_LENGTH: int = 256
    PASSWORD_SCRYPT_N: int = 32768
    PASSWORD_SCRYPT_R: int = 8
    PASSWORD_SCRYPT_P: int = 1

    AUTH_RATE_LIMIT_LOGIN_PER_MINUTE: int = 5
    AUTH_RATE_LIMIT_REGISTER_PER_HOUR: int = 5
    AUTH_RATE_LIMIT_REFRESH_PER_MINUTE: int = 10
    AUTH_RATE_LIMIT_LOGOUT_PER_MINUTE: int = 30
    AUTH_RATE_LIMIT_EMAIL_PER_HOUR: int = 5

    FRONTEND_BASE_URL: str = "http://localhost:5173"
    EMAIL_VERIFICATION_TTL_HOURS: int = 24
    PASSWORD_RESET_TTL_MINUTES: int = 60
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "no-reply@cinerank.example"
    SMTP_STARTTLS: bool = True
    SMTP_SSL: bool = False
    SMTP_TIMEOUT_SECONDS: int = 15

    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'data' / 'cinerank.db'}"
    REDIS_URL: str = ""
    REDIS_CACHE_TTL_SECONDS: int = 120
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_PUBLIC_PER_MINUTE: int = 240
    RATE_LIMIT_SEARCH_PER_MINUTE: int = 30
    RATE_LIMIT_RECOMMENDATIONS_PER_MINUTE: int = 20
    RATE_LIMIT_WRITE_PER_MINUTE: int = 60
    SQL_POOL_SIZE: int = 5
    SQL_MAX_OVERFLOW: int = 10
    SQL_POOL_TIMEOUT_SECONDS: int = 30
    SQL_POOL_RECYCLE_SECONDS: int = 1800
    SQL_ECHO: bool = False
    AUTO_CREATE_SCHEMA: bool = False  # Schema is managed by Alembic in every environment.

    MODEL_DIR: Path = BASE_DIR / "artifacts" / "models"  # v1 lifecycle compatibility
    MODEL_RELEASE_DIR: Path = BASE_DIR / "artifacts" / "models" / "releases"
    MODEL_INFERENCE_CACHE_SIZE: int = 1024
    MODEL_INFERENCE_USE_GPU: bool = False
    MODEL_INFERENCE_REQUIRE_GPU: bool = False
    DATA_DIR: Path = BASE_DIR / "data"
    CACHE_DIR: Path = BASE_DIR / "cache"
    LOG_DIR: Path = BASE_DIR / "logs"
    LOG_LEVEL: str = "INFO"
    LOG_FILE_ENABLED: bool = True
    LOG_FILE_NAME: str = "cinerank.log"
    LOG_MAX_BYTES: int = 10_485_760
    LOG_BACKUP_COUNT: int = 5

    WEIGHT_POP: str = "rec-pop-v1"
    WEIGHT_CONTENT: str = "rec-content-v1"
    WEIGHT_ITEMKNN: str = "rec-itemknn-v1"
    WEIGHT_ALS: str = "rec-als-v1"
    WEIGHT_BPR: str = "rec-bpr-v1"
    WEIGHT_ATTN: str = "rec-attn-v1"
    WEIGHT_HYBRID: str = "rec-hybrid-v1"
    ID_MAPS: str = "id-maps-v1"
    TRAIN_MAT: str = "train-mat-v1"

    DEFAULT_K: int = 5
    MAX_K: int = 50
    CANDIDATE_POOL_SIZE: int = 100
    ATTENTION_SCORE_BATCH_SIZE: int = 2048
    RECOMMENDATION_TOKEN_TTL_SECONDS: int = 3600

    TMDB_API_KEY: str = ""
    TMDB_READ_ACCESS_TOKEN: str = ""
    CRAWLER_REQUESTS_PER_SECOND: float = 2.0
    CRAWLER_USER_AGENT: str = "CineRankBot/2.0 (catalogue metadata synchronisation)"
    CRAWLER_MAX_RETRIES: int = 4
    CRAWLER_PAGES_PER_MEDIA_TYPE: int = 3
    WEB_CRAWLER_ENABLED: bool = False
    CRAWLER_SEED_URLS: str = ""
    CRAWLER_MAX_PAGES_PER_RUN: int = 100
    CRAWLER_MAX_DEPTH: int = 3
    CRAWLER_MAX_BODY_BYTES: int = 2_000_000
    CRAWLER_MAX_LINKS_PER_PAGE: int = 200
    CRAWLER_DEFAULT_DELAY_SECONDS: float = 1.0
    CRAWLER_MIN_HOST_DELAY_SECONDS: float = 2.0
    CRAWLER_REVISIT_HOURS: int = 24
    CRAWLER_RETRY_HOURS: int = 6
    CRAWLER_ROBOTS_TTL_SECONDS: int = 86400
    CRAWLER_CONNECT_TIMEOUT: int = 10
    CRAWLER_READ_TIMEOUT: int = 20
    CRAWLER_MAX_REDIRECTS: int = 3
    CRAWLER_ALLOW_SUBDOMAINS: bool = False
    CRAWLER_MIN_VOTE_COUNT: int = 5
    CATALOGUE_SORT_BATCH_SIZE: int = 5000
    JOB_LEASE_SECONDS: int = 3600
    SCHEDULER_POLL_SECONDS: int = 30
    MODEL_REFRESH_DAYS: int = 60
    MODEL_TRAINING_TIMEOUT_SECONDS: int = 86400
    MODEL_PROMOTION_MIN_DELTA: float = 0.002
    MODEL_EVALUATION_KS: str = "5,10,20"
    MODEL_EVALUATION_MAX_USERS: int = 2000
    MODEL_EVALUATION_MIN_HIT_RATE_10: float = 0.0
    TRAINING_DATA_DIR: Path = BASE_DIR / "data" / "training"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def jwt_secret_key(self) -> str:
        return self.JWT_SECRET_KEY or self.SECRET_KEY

    @property
    def auth_cookie_samesite(self) -> str:
        return self.AUTH_COOKIE_SAMESITE.strip().lower()

    @property
    def auth_cookie_domain(self) -> str | None:
        return self.AUTH_COOKIE_DOMAIN.strip() or None if self.AUTH_COOKIE_DOMAIN else None

    @property
    def crawler_seed_urls(self) -> list[str]:
        return [value.strip() for value in self.CRAWLER_SEED_URLS.split(",") if value.strip()]

    @property
    def evaluation_ks(self) -> list[int]:
        values = sorted({int(value.strip()) for value in self.MODEL_EVALUATION_KS.split(",") if value.strip()})
        return [value for value in values if 1 <= value <= 100]


def validate_security_settings(config: Settings) -> None:
    """Reject unsafe production authentication configuration at startup."""
    if config.ENVIRONMENT.strip().lower() != "production":
        return
    if len(config.SECRET_KEY) < 48 or config.SECRET_KEY.startswith(("CHANGE-ME", "REPLACE")):
        raise RuntimeError(
            "SECRET_KEY must be a random secret of at least 48 characters in production."
        )
    if len(config.jwt_secret_key) < 48 or config.jwt_secret_key.startswith(("CHANGE-ME", "REPLACE")):
        raise RuntimeError(
            "JWT_SECRET_KEY must be a random secret of at least 48 characters in production."
        )
    if config.JWT_ALGORITHM not in {"HS256", "HS384", "HS512"}:
        raise RuntimeError("JWT_ALGORITHM must be HS256, HS384, or HS512.")
    if not 5 <= config.ACCESS_TOKEN_EXPIRE_MINUTES <= 15:
        raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be between 5 and 15 in production.")
    if not 1 <= config.REFRESH_TOKEN_EXPIRE_DAYS <= 365:
        raise RuntimeError("REFRESH_TOKEN_EXPIRE_DAYS must be between 1 and 365.")
    if not config.AUTH_COOKIE_SECURE:
        raise RuntimeError("AUTH_COOKIE_SECURE must be true in production.")
    if not config.AUTH_COOKIE_HTTPONLY:
        raise RuntimeError("AUTH_COOKIE_HTTPONLY must be true in production.")
    if config.auth_cookie_samesite not in {"lax", "strict", "none"}:
        raise RuntimeError("AUTH_COOKIE_SAMESITE must be lax, strict, or none.")
    if config.auth_cookie_samesite == "none" and not config.AUTH_COOKIE_SECURE:
        raise RuntimeError("SameSite=None requires AUTH_COOKIE_SECURE=true.")
    if not config.AUTH_COOKIE_PATH.startswith("/"):
        raise RuntimeError("AUTH_COOKIE_PATH must start with /.")
    if not config.cors_origin_list or "*" in config.cors_origin_list:
        raise RuntimeError("CORS_ORIGINS must list explicit frontend origins in production.")
    if not config.REDIS_URL.strip():
        raise RuntimeError("REDIS_URL is required in production for shared rate limiting and cache coordination.")
    if config.SQL_POOL_SIZE < 1 or config.SQL_MAX_OVERFLOW < 0:
        raise RuntimeError("Database pool size/overflow settings are invalid.")
    if config.PASSWORD_MIN_LENGTH < 12:
        raise RuntimeError("PASSWORD_MIN_LENGTH must be at least 12.")
    if config.PASSWORD_MAX_LENGTH < config.PASSWORD_MIN_LENGTH:
        raise RuntimeError("PASSWORD_MAX_LENGTH must be at least PASSWORD_MIN_LENGTH.")
    if not 0 <= config.AUTH_REFRESH_REUSE_GRACE_SECONDS <= 60:
        raise RuntimeError("AUTH_REFRESH_REUSE_GRACE_SECONDS must be between 0 and 60.")
    if not config.FRONTEND_BASE_URL.startswith("https://"):
        raise RuntimeError("FRONTEND_BASE_URL must use HTTPS in production.")
    if config.SMTP_SSL and config.SMTP_STARTTLS:
        raise RuntimeError("Configure either SMTP_SSL or SMTP_STARTTLS, not both.")
    if config.SMTP_HOST and not config.SMTP_FROM_EMAIL:
        raise RuntimeError("SMTP_FROM_EMAIL is required when SMTP_HOST is configured.")


settings = Settings()
for directory in (settings.MODEL_DIR, settings.DATA_DIR, settings.CACHE_DIR, settings.LOG_DIR, settings.TRAINING_DATA_DIR):
    directory.mkdir(parents=True, exist_ok=True)

validate_security_settings(settings)
