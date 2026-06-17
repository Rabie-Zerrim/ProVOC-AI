FROM python:3.12-slim
WORKDIR /app
# System deps needed for ffmpeg (Whisper audio processing) and building some wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*
# Upgrade pip tooling first to avoid pkg_resources/build-isolation issues
RUN pip install --upgrade pip setuptools wheel
# Install CPU-only PyTorch first (avoids pulling several GB of unused CUDA
# libraries; Railway has no GPU, so the default GPU build wastes image size)
RUN pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu
# Install remaining Python dependencies (prod-only, no training/eval libs)
COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt
# Copy application code
COPY . .
# Download and extract the fine-tuned Whisper model (too large for git,
# hosted as a GitHub Release asset instead)
RUN curl -L "https://github.com/Rabie-Zerrim/ProVOC-AI/releases/download/whisper-model-v1/whisper-provoc-v1.zip" -o /tmp/whisper-model.zip \
    && mkdir -p ./whisper-provoc-small/final \
    && unzip -q /tmp/whisper-model.zip -d ./whisper-provoc-small/final \
    && rm /tmp/whisper-model.zip
# Railway provides $PORT at runtime
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
