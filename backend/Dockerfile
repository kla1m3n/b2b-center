# syntax=docker/dockerfile:1
FROM python:3.11-slim

ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    HF_HOME=/models \
    HF_HUB_DISABLE_TELEMETRY=1

WORKDIR /app

RUN pip install torch==2.5.1 --index-url ${TORCH_INDEX}

COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install ".[dev]" && pip uninstall -y pp1875-classifier && rm -rf app
ENV PYTHONPATH=/app

ARG EMBED_MODEL=intfloat/multilingual-e5-large
COPY scripts/download_models.py scripts/
# /seed — локальный кэш моделей (.hf в корне репозитория); если пуст, модель скачивается из интернета
RUN --mount=type=bind,from=hfseed,target=/seed python scripts/download_models.py ${EMBED_MODEL}
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

COPY . .
