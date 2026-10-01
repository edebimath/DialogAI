# DialogAI API: FastAPI + Pipecat (Whisper, Piper, WebRTC). Built by deploy/docker-compose.yml.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_NO_CACHE=1

# libgomp: OpenMP for CTranslate2 (Whisper) and ONNX Runtime (VAD, Smart Turn, Piper).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 app

# The repo layout is kept (…/backend/app) so settings find the repo root the same way as in dev.
WORKDIR /srv/dialogai/backend

COPY pyproject.toml ./
RUN pip install uv==0.9.* && uv pip install --system -r pyproject.toml

# GPU Whisper: CTranslate2 loads cuBLAS/cuDNN from the pip wheels (unused on CPU).
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

# Named volumes copy these directories' ownership on first use, so the app user can write them.
RUN mkdir -p /data /home/app/.cache && chown -R app:app /data /home/app/.cache
USER app

ENV APP_ENV=production \
    DATA_DIR=/data \
    HF_HOME=/home/app/.cache/huggingface \
    API_HOST=0.0.0.0

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"

# One worker: live calls, the indexing and simulation queues and the login lockouts live in
# this process. --proxy-headers: the client address comes from nginx (X-Forwarded-For), which
# is the only thing that can reach this port.
CMD ["sh", "-c", "exec uvicorn app.main:app --host \"$API_HOST\" --port 8000 --proxy-headers --forwarded-allow-ips='*' --no-server-header"]
