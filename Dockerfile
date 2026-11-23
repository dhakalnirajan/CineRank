# One source Dockerfile with independent production targets:
#   docker compose build api worker migrate web
# API, worker, migration runner and static web are separate containers by design.

FROM python:3.11-slim AS api

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    ENVIRONMENT=production \
    AUTO_CREATE_SCHEMA=false \
    MODEL_RELEASE_DIR=/app/artifacts/models/releases \
    DATA_DIR=/app/data \
    LOG_DIR=/app/logs

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# The production image needs ONNX inference, not notebook/training stacks such
# as PyTorch, implicit, pandas or scikit-learn.
COPY backend/requirements-runtime.txt /tmp/requirements-runtime.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /tmp/requirements-runtime.txt

# Source is copied after dependencies to preserve the pip build cache.
COPY backend/alembic.ini /app/alembic.ini
COPY backend/migrations/ /app/migrations/
COPY backend/app/ /app/app/
COPY backend/crawler/ /app/crawler/
COPY backend/ranker/ /app/ranker/
COPY backend/scripts/ /app/scripts/
COPY backend/artifacts/models/releases/ /app/artifacts/models/releases/
COPY backend/data/seeds/ /app/data/seeds/
RUN mkdir -p /app/data/media/avatars /app/logs /app/cache \
    && groupadd --system --gid 10001 cinerank \
    && useradd --system --uid 10001 --gid cinerank --home-dir /app cinerank \
    && chown -R cinerank:cinerank /app/data /app/logs /app/cache

USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=4s --start-period=45s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live', timeout=3)" || exit 1
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "172.30.0.2", "--no-access-log"]

FROM node:22-alpine AS frontend-build
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM nginx:1.28-alpine AS web
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /web/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=4s --start-period=10s --retries=5 \
  CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
