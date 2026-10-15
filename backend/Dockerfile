FROM python:3.11-slim

ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models \
    HF_HUB_DISABLE_TELEMETRY=1

WORKDIR /app

RUN pip install torch==2.5.1 --index-url ${TORCH_INDEX}

COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install ".[dev]" && pip uninstall -y pp1875-classifier && rm -rf app
ENV PYTHONPATH=/app

ARG EMBED_MODEL=intfloat/multilingual-e5-base
ARG RERANK_MODEL=BAAI/bge-reranker-v2-m3
COPY scripts/download_models.py scripts/
RUN python scripts/download_models.py ${EMBED_MODEL} ${RERANK_MODEL}
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

COPY . .
