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

# /pipseed — локальные колёса (wheels/cpu): сначала ставим только из них, без сети;
# если папка пуста или чего-то не хватает — обычная установка из интернета
RUN --mount=type=bind,from=pipseed,target=/pipseed \
    pip install --no-index --find-links /pipseed torch==2.5.1 \
    || pip install torch==2.5.1 --index-url ${TORCH_INDEX}

COPY pyproject.toml ./
RUN --mount=type=bind,from=pipseed,target=/pipseed \
    mkdir app && touch app/__init__.py \
    && (pip install --no-index --find-links /pipseed ".[dev]" || pip install ".[dev]") \
    && pip uninstall -y pp1875-classifier && rm -rf app
ENV PYTHONPATH=/app

ARG EMBED_MODEL=intfloat/multilingual-e5-large
ARG EMBED_BACKEND=onnx
ARG EMBED_ONNX_FILE=
COPY scripts/download_models.py scripts/
# /seed — локальный кэш моделей (.hf в корне репозитория); если пуст, модель скачивается из интернета
RUN --mount=type=bind,from=hfseed,target=/seed \
    EMBED_BACKEND=${EMBED_BACKEND} EMBED_ONNX_FILE=${EMBED_ONNX_FILE} python scripts/download_models.py ${EMBED_MODEL}
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

COPY . .
