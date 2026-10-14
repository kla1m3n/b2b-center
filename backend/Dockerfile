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

COPY . .
