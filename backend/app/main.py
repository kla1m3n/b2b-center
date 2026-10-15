import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import state
from app.api import classify, health, jobs, npa
from app.db import SessionLocal, init_db
from app.npa.service import get_active_version

log = logging.getLogger("app")


def _warmup() -> None:
    from app.classifier.pipeline import get_pipeline

    try:
        get_pipeline()
        with SessionLocal() as s:
            v = get_active_version(s)
            state.npa_version_title = v.title if v else None
        state.models_ready = True
        log.info("Модели загружены, сервис готов")
    except Exception:
        log.exception("Не удалось загрузить модели")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    threading.Thread(target=_warmup, daemon=True).start()
    yield


app = FastAPI(
    title="Классификатор товаров по ПП № 1875",
    description="Определение кода ОКПД2 и режима национального режима закупок по ПП РФ № 1875.",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(health.router, prefix="/api")
app.include_router(classify.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(npa.router, prefix="/api")
