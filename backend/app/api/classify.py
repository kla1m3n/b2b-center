"""Классификация: один товар (синхронно) и пакет до 100 товаров (через очередь Celery)."""
import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

from app import state
from app.celery_app import classify_job
from app.classifier.pipeline import get_pipeline
from app.config import get_settings
from app.db import SessionLocal
from app.io_files import FileReadError, read_names
from app.models import Job, JobItem
from app.npa.service import get_active_version
from app.schemas import ClassificationResult, JobCreated

router = APIRouter(tags=["Классификация"])


class ClassifyIn(BaseModel):
    name: str = Field(min_length=1, max_length=1000, examples=["Ноутбук Lenovo IdeaPad 15, 16 ГБ, SSD 512 ГБ"])


class BatchIn(BaseModel):
    names: list[str] = Field(examples=[["Ноутбук Lenovo IdeaPad 15", "Бумага А4 500 листов", "Стул офисный"]])


@router.post("/classify", response_model=ClassificationResult, summary="Классифицировать один товар")
def classify(body: ClassifyIn) -> ClassificationResult:
    if not state.models_ready:
        raise HTTPException(503, "Система запускается: модели ИИ загружаются, попробуйте через минуту")
    return get_pipeline().classify_many([body.name])[0]


BATCH_OPENAPI = {"requestBody": {"required": True, "content": {
    "application/json": {"schema": BatchIn.model_json_schema()},
    "multipart/form-data": {"schema": {"type": "object", "properties": {
        "file": {"type": "string", "format": "binary", "description": "Файл .xlsx, .csv или .txt со списком товаров"}}}},
}}}


async def _names_from_request(request: Request) -> list[str]:
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        upload = (await request.form()).get("file")
        if upload is None or not hasattr(upload, "filename"):
            raise HTTPException(422, "Прикрепите файл в поле file")
        try:
            return read_names(upload.filename or "", await upload.read())
        except FileReadError as e:
            raise HTTPException(422, str(e))
    try:
        return BatchIn.model_validate(json.loads(await request.body())).names
    except (json.JSONDecodeError, ValidationError):
        raise HTTPException(422, 'Ожидается JSON вида {"names": ["товар 1", "товар 2"]} или файл в поле file')


@router.post("/classify/batch", response_model=JobCreated, status_code=202, openapi_extra=BATCH_OPENAPI,
             summary="Классифицировать список товаров (до 100) или файл .xlsx/.csv")
async def classify_batch(request: Request) -> JobCreated:
    limit = get_settings().batch_limit
    names = [n.strip() for n in await _names_from_request(request) if n and n.strip()]
    if not names:
        raise HTTPException(422, "Список товаров пуст")
    if len(names) > limit:
        raise HTTPException(422, f"Не более {limit} товаров за один запрос (получено {len(names)})")
    with SessionLocal() as s:
        version = get_active_version(s)
        job = Job(id=str(uuid4()), total=len(names), done=0, status="queued",
                  npa_version_id=version.id if version else None)  # снимок версии ПП на момент запроса
        s.add(job)
        s.flush()
        s.add_all(JobItem(job_id=job.id, idx=i, input=n) for i, n in enumerate(names))
        s.commit()
        job_id = job.id
    classify_job.delay(job_id)
    return JobCreated(job_id=job_id)
