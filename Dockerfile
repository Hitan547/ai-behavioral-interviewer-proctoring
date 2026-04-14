# Multi-stage build for PsySense - optimized for production
FROM python:3.11-slim AS base

WORKDIR /app

# Install system dependencies (ffmpeg for audio, curl for health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir supervisor


FROM base AS model-cache

WORKDIR /app

ARG HF_MODEL=Hitan2004/psysense-emotion-ai
ENV TRANSFORMERS_CACHE=/app/hf_cache

RUN mkdir -p /app/hf_cache

# Pre-cache model files during build so startup avoids network downloads.
RUN python - <<'PY'
from transformers import DistilBertForSequenceClassification, DistilBertTokenizerFast
import os

model_name = os.environ.get("HF_MODEL", "Hitan2004/psysense-emotion-ai")
cache_dir = "/app/hf_cache"

print(f"Pre-caching model: {model_name}")
try:
    DistilBertForSequenceClassification.from_pretrained(model_name, cache_dir=cache_dir)
    DistilBertTokenizerFast.from_pretrained(model_name, cache_dir=cache_dir)
    print("Model cache complete")
except Exception as e:
    print(f"WARNING: model pre-cache failed: {e}")
PY


FROM base AS production

WORKDIR /app

# Copy pre-cached model artifacts first.
COPY --from=model-cache /app/hf_cache /app/hf_cache

# Copy application code.
COPY . .

# Supervisor config for multi-process management.
COPY supervisord.conf /etc/supervisord.conf

ENV TRANSFORMERS_CACHE=/app/hf_cache \
    HF_LOCAL_ONLY=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create non-root user for security.
RUN useradd -m -u 1000 psysense && chown -R psysense:psysense /app
USER psysense

# Expose all required ports.
EXPOSE 8000 8001 8002 8003 8004 8501

# Health check for user-facing UI and active emotion API.
HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=3 \
    CMD curl -fsS http://localhost:8501/_stcore/health && \
        curl -fsS http://localhost:8002/health || exit 1

# Start all services with supervisor (auto-restart on crash).
CMD ["/usr/local/bin/supervisord", "-c", "/etc/supervisord.conf"]