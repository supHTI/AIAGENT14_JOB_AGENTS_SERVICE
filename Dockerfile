# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first (better layer caching)
COPY pyproject.toml uv.lock* /app/

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Copy source
COPY . /app

# Make entrypoint script executable
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Expose default port; override at runtime
EXPOSE 8510

# Healthcheck (assumes /health exists; adjust if different)
# HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
#   CMD curl -f http://127.0.0.1:${APP_PORT:-8510}/health || exit 1

# Default to running API service, can be overridden with SERVICE_TYPE env var
# Options: api, celery, both
ENV SERVICE_TYPE=api
CMD ["/app/entrypoint.sh"]