# Use official Python 3.12 slim image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
RUN pip install uv

# Copy dependency files first (for Docker layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev extras, no editable install)
RUN uv sync --frozen --no-dev

# Copy application source
COPY app/ ./app/

# Cloud Run sets PORT env var (default 8080)
ENV PORT=8080
ENV HOST=0.0.0.0

# Expose port
EXPOSE 8080

# Run the ADK API server (REST backend — works headlessly on Cloud Run)
# GOOGLE_API_KEY must be set as a Cloud Run secret/env var
CMD uv run adk api_server --host $HOST --port $PORT app
