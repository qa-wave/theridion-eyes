# Theridion Python sidecar — Fly.io deploy
# FastAPI app on uvicorn, all 130+ protocol routes.

FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps for gRPC, cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager — sidecar uses it)
RUN pip install uv==0.5.30

# Install deps (using uv.lock for reproducibility)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy app
COPY theridion_sidecar ./theridion_sidecar

# Install the package itself
RUN uv sync --frozen --no-dev

# Non-root user
RUN useradd --create-home --shell /bin/bash app
USER app

EXPOSE 8765

# Use uvicorn directly via uv
CMD ["uv", "run", "uvicorn", "theridion_sidecar.main:app", \
     "--host", "0.0.0.0", "--port", "8765", \
     "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
