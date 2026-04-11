# Multi-stage build for PsySense - optimized for production
FROM python:3.11-slim as base

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
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 psysense && chown -R psysense:psysense /app
USER psysense

# Expose all required ports
EXPOSE 8000 8001 8002 8003 8004 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Start all services using a process manager
CMD ["sh", "-c", "\
    python answer_service/main.py & \
    python emotion_service/main.py & \
    python fusion_service/main.py & \
    python insight_service/main.py & \
    streamlit run demo_app.py --server.port=8501 --server.address=0.0.0.0 \
"]