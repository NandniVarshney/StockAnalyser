# ─── StockAnalyser — runtime image ─────────────────────────────────────────
# NOTE: The Rovo Dev CLI (`acli rovodev serve`) must run on the HOST, not inside
# this container — it needs your Atlassian credentials + MFA. The container talks
# to it via host.docker.internal:8766.
# ──────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for pandas/pyarrow wheels + nselib (TLS, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better Docker layer caching)
COPY pyproject.toml ./
RUN pip install -U pip wheel && pip install -e ".[dev]"

# Copy app
COPY . .

# Persistent data
RUN mkdir -p /app/data/ohlcv /app/db /app/logs

EXPOSE 8000

CMD ["uvicorn", "stockanalyser.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
