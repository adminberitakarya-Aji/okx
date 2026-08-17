# ============================================================================
# OKX AI Trading Grid System - Production Dockerfile
# ============================================================================
# Multi-stage build for smaller image size
# Usage: docker build -f deploy/docker/Dockerfile -t okx-trading .
# ============================================================================

# ----------------------------------------------------------------------------
# STAGE 1: Builder
# ----------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies (production only, skip project install since source not yet copied)
RUN uv sync --frozen --no-dev --extra prod --no-install-project

# ----------------------------------------------------------------------------
# STAGE 2: Runtime
# ----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY src/ /app/src/
COPY scripts/ /app/scripts/
COPY pyproject.toml /app/

# Create directories for data, models, logs
RUN mkdir -p /app/data /app/models /app/logs && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command
CMD ["uvicorn", "okx_trading.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]