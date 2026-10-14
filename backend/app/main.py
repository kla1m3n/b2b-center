from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Классификатор товаров по ПП № 1875",
    description="Определение кода ОКПД2 и режима национального режима закупок по ПП РФ № 1875.",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(health.router, prefix="/api")
