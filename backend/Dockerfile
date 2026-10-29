# syntax=docker/dockerfile:1.4
# =============================================================================
# IOC Pulse — Backend Dockerfile
# =============================================================================
# Build context MUST be the repo root (not backend/), because the backend
# imports modules from src/ (Module 1, Module 2, shared database client).
# docker-compose.yml handles this automatically.
#
# CACHING NOTE:
#   --mount=type=cache,target=/root/.cache/pip keeps pip's wheel cache in a
#   Docker-managed volume that survives rebuilds. Combined with the COPY
#   ordering below, a normal code change rebuilds in ~5-15 seconds instead
#   of re-downloading every Python package.
# =============================================================================

FROM python:3.11-slim

# System deps for lxml / trafilatura / pypdf / aiohttp
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libxml2-dev \
        libxslt1-dev \
        libffi-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- Python deps: root requirements (aiohttp, feedparser, google-genai, ...) ----
# NOTE: no `--no-cache-dir` — we WANT pip to use the cache mount below.
COPY requirements.txt ./requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# ---- Python deps: backend requirements (FastAPI, uvicorn, apscheduler) ----
COPY backend/requirements.txt ./backend/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r backend/requirements.txt

# ---- Application source ----
COPY src/     ./src/
COPY backend/ ./backend/

# Persistent data dir (bind-mounted at runtime)
RUN mkdir -p /app/data

# ---- Runtime environment ----
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DB_PATH=/app/data/ioc_pulse.db

EXPOSE 8000

# `--app-dir backend` adds /app/backend to sys.path so `app.main:app` resolves.
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]