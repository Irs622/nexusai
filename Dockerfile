# =============================================================================
# Stage 1: Builder
# =============================================================================
FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install minimal build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy dependency specifications and install
COPY pyproject.toml .
RUN pip install --upgrade pip setuptools wheel hatchling
RUN pip install .

# =============================================================================
# Stage 2: Production Runtime
# =============================================================================
FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    NEXUSAI_ENV=production \
    PORT=8080

# Install runtime utilities (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application source and assets
COPY src/ /app/src/
COPY web/ /app/web/
COPY pyproject.toml /app/pyproject.toml

# Install package in editable/local mode into venv
RUN pip install --no-deps -e .

# Create non-root user and directories (UID 10001 matching Kubernetes Helm spec)
RUN groupadd -g 10001 nexusai && \
    useradd -u 10001 -g nexusai -s /bin/bash -m nexusai && \
    mkdir -p /app/data /app/logs && \
    chown -R 10001:10001 /app

USER 10001:10001

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health/live || exit 1

ENTRYPOINT ["uvicorn", "nexusai.api.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
