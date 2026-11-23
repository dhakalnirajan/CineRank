from contextlib import asynccontextmanager
import asyncio
import re
import logging
import time
from uuid import uuid4

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, make_asgi_app

from app.core.config import settings
from app.core.logging_config import configure_logging
from app.db.session import engine
from app.db.schema_guard import validate_database_schema
from app.api.routes import router
from app.services.recommendation_service import recommendation_service
from app.core.rate_limit import request_rate_limiter
from app.core.redis_client import redis_health
from app.core.security import decode_access_token

configure_logging()
access_logger = logging.getLogger("cinerank.access")
REQUEST_COUNT = Counter(
    "cinerank_http_requests_total",
    "Total HTTP requests handled by CineRank API",
    ("method", "route", "status"),
)
REQUEST_LATENCY = Histogram(
    "cinerank_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ("method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.ENVIRONMENT.strip().lower() != "test":
        validate_database_schema(engine)
    recommendation_service.load_artifacts()
    app.state.recommendation_ready = recommendation_service.is_ready
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Modular movie and television recommendation backend",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "Retry-After"],
)
app.include_router(router, prefix=settings.API_V1_STR)


@app.middleware("http")
async def request_policy_middleware(request, call_next):
    """Request IDs, bounded shared rate limits, security headers and access logs."""
    supplied_id = request.headers.get("x-request-id", "")
    request_id = supplied_id if re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", supplied_id) else uuid4().hex
    request.state.request_id = request_id
    started = time.perf_counter()
    status_code = 500
    path = request.url.path

    if path.startswith(settings.API_V1_STR) and request.method != "OPTIONS" and path not in {
        f"{settings.API_V1_STR}/health/live", f"{settings.API_V1_STR}/health/ready",
        f"{settings.API_V1_STR}/health",
    }:
        if path.startswith(f"{settings.API_V1_STR}/search"):
            limit, scope = settings.RATE_LIMIT_SEARCH_PER_MINUTE, "search"
        elif "/recommend" in path or "/home/" in path:
            limit, scope = settings.RATE_LIMIT_RECOMMENDATIONS_PER_MINUTE, "recommendations"
        elif path.endswith("/interactions"):
            limit, scope = 60, "interactions"
        elif "/ratings" in path:
            limit, scope = 20, "ratings"
        elif "/watchlist" in path:
            limit, scope = 30, "watchlist"
        elif request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            limit, scope = settings.RATE_LIMIT_WRITE_PER_MINUTE, "writes"
        else:
            limit, scope = settings.RATE_LIMIT_PUBLIC_PER_MINUTE, "public"

        host = request.client.host if request.client else "unknown"
        retry_after = await asyncio.to_thread(
            request_rate_limiter.check,
            f"{scope}:ip:{host}", limit, settings.RATE_LIMIT_WINDOW_SECONDS,
        )
        auth_header = request.headers.get("authorization", "")
        if retry_after is None and auth_header.lower().startswith("bearer "):
            claims = decode_access_token(auth_header[7:].strip())
            if claims is not None:
                retry_after = await asyncio.to_thread(
                    request_rate_limiter.check,
                    f"{scope}:user:{claims.user_id}", limit, settings.RATE_LIMIT_WINDOW_SECONDS,
                )
        if retry_after is not None:
            response = JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Try again later.", "request_id": request_id},
                headers={"Retry-After": str(retry_after), "X-Request-ID": request_id},
            )
            status_code = 429
        else:
            response = None
    else:
        response = None

    try:
        if response is None:
            response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.headers.get("authorization") or "/auth/" in path:
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        if request.headers.get("x-forwarded-proto", request.url.scheme) == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
    except Exception:
        access_logger.exception(
            "request_failed",
            extra={
                "event": "request_failed",
                "request_id": request_id,
                "method": request.method,
                "path": path,
            },
        )
        raise
    finally:
        elapsed_seconds = time.perf_counter() - started
        elapsed_ms = elapsed_seconds * 1000.0
        if path.startswith(settings.API_V1_STR):
            route_object = request.scope.get("route")
            route_label = getattr(route_object, "path", "unmatched")
            REQUEST_COUNT.labels(request.method, route_label, str(status_code)).inc()
            REQUEST_LATENCY.labels(request.method, route_label).observe(elapsed_seconds)
        access_logger.info(
            "request_complete",
            extra={
                "event": "request_complete",
                "request_id": request_id,
                "method": request.method,
                "path": path,
                "status": status_code,
                "duration_ms": round(elapsed_ms, 2),
            },
        )

# User-uploaded media is stored outside the application package.
_media_dir = settings.DATA_DIR / "media"
_media_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=_media_dir), name="media")
# Scraped only over the private Docker network; Nginx explicitly denies /metrics.
app.mount("/metrics", make_asgi_app(), name="metrics")


@app.get("/")
def root():
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "health": f"{settings.API_V1_STR}/health",
        "api_base": settings.API_V1_STR,
    }
