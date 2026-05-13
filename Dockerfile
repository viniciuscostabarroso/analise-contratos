# syntax=docker/dockerfile:1.7

# =============================================
# STAGE 1: Build do frontend React
# =============================================
FROM node:20-alpine AS frontend-builder
WORKDIR /build/frontend

ENV NODE_ENV=production \
    CI=true

COPY frontend/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci --omit=dev; else npm install --omit=dev; fi

COPY frontend/ ./
RUN npm run build

# =============================================
# STAGE 2: Runtime Python (Flask + Gunicorn)
# =============================================
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080 \
    GUNICORN_WORKERS=1 \
    GUNICORN_THREADS=8 \
    GUNICORN_TIMEOUT=0 \
    GUNICORN_GRACEFUL_TIMEOUT=30 \
    MAX_QUEUE_SIZE=20

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend-builder /build/frontend/build ./static

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

CMD ["gunicorn", "-c", "gunicorn.conf.py", "main:app"]
