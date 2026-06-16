FROM python:3.12-slim

WORKDIR /app

# System deps needed for ffmpeg (Whisper audio processing) and building some wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip tooling first to avoid pkg_resources/build-isolation issues
RUN pip install --upgrade pip setuptools wheel

# Install Python dependencies (prod-only, no training/eval libs)
COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

# Copy application code
COPY . .

# Railway provides $PORT at runtime
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]