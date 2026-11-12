"""Классификация: один товар (синхронно) и пакет до 100 товаров (через очередь Celery); отчёты без задачи."""
import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError

from app import state
from app.api.jobs import DOCX, XLSX, attachment
from app.celery_app import classify_job
from app.classifier.pipeline import get_pipeline
from app.config import get_settings
from app.db import SessionLocal
from app.exports import annotate_xlsx, justification_to_docx, report_to_docx, results_to_xlsx
from app.io_files import FileReadError, read_names
from app.models import Job, JobItem
from app.npa.service import get_active_version
from app.schemas import ClassificationResult, JobCreated

router = APIRouter(tags=["Классификация"])


CODE = r"^\d{2}(\.\d{1,3}){0,3}$"  # код ОКПД2: 26 … 26.20.11.110


class ClassifyIn(BaseModel):
    name: str = Field(min_length=1, max_length=1000, examples=["Ноутбук Lenovo IdeaPad 15, 16 ГБ, SSD 512 ГБ"])
    code: str | None = Field(None, pattern=CODE, examples=[None], description=(
        "Код ОКПД2, выбранный специалистом вместо автоматического (или тот же — как подтверждение). Режим, пункты ПП, "
        "рекомендация и обоснование строятся по нему, пометка «проверьте вручную» снимается."))


class BatchIn(BaseModel):
    names: list[str] = Field(examples=[["Ноутбук Lenovo IdeaPad 15", "Бумага А4 500 листов", "Стул офисный"]])


class ReportIn(BatchIn):
    codes: list[str | None] | None = Field(None, examples=[None], description=(
        "Коды ОКПД2, выбранные специалистом, — список той же длины, что names; null — оставить автоматический код."))


def _classify(names: list[str], codes: list[str | None] | None = None) -> list[ClassificationResult]:
    if not state.models_ready:
        raise HTTPException(503, "Система запускается: модели ИИ загружаются, попробуйте через минуту")
    if not codes or not any(codes):
        return get_pipeline().classify_many(names)
    try:
        return get_pipeline().classify_with_codes(names, codes)
    except ValueError as e:  # код не найден в справочнике
        raise HTTPException(422, str(e))


def _report_input(body: ReportIn) -> tuple[list[str], list[str | None]]:
    """Наименования без пустых строк и выровненные с ними коды специалиста."""
    limit = get_settings().batch_limit
    codes = body.codes or [None] * len(body.names)
    if len(codes) != len(body.names):
        raise HTTPException(422, "Список codes должен быть той же длины, что names")
    pairs = [(n.strip(), (c or "").strip() or None) for n, c in zip(body.names, codes) if n and n.strip()]
    if not pairs:
        raise HTTPException(422, "Список товаров пуст")
    if len(pairs) > limit:
        raise HTTPException(422, f"Не более {limit} товаров за один запрос (получено {len(pairs)})")
    return [n for n, _ in pairs], [c for _, c in pairs]


@router.post("/classify", response_model=ClassificationResult, summary="Классифицировать один товар")
def classify(body: ClassifyIn) -> ClassificationResult:
    """С полем `code` — пересчёт под код, выбранный специалистом: `code_confirmed: true`, прежний код —
    в `alternatives` и в `auto_code`."""
    return _classify([body.name], [body.code])[0]


@router.post("/classify/justification.docx", summary="Обоснование по одному товару в Word",
             response_class=Response, responses={200: {"content": {DOCX: {}}}})
def classify_justification(body: ClassifyIn) -> Response:
    """Готовый документ для закупочной документации или служебной записки: код, режим, пункт ПП со ссылкой,
    уверенность, альтернативные коды с их режимом и рекомендация. Тот же текст — в поле `justification` ответа
    `/api/classify`."""
    return attachment(justification_to_docx(_classify([body.name], [body.code])[0]), DOCX, "pp1875_obosnovanie.docx")


@router.post("/report.xlsx", summary="Отчёт в Excel по списку товаров без создания задачи",
             response_class=Response, responses={200: {"content": {XLSX: {}}}})
def report_xlsx(body: ReportIn) -> Response:
    """То же, что `/api/jobs/{id}/export.xlsx`, но сразу по списку наименований (уже проверенные товары берутся
    из кэша): для одиночной проверки, для результатов из истории и для списка, где специалист выбрал
    коды вручную (`codes`)."""
    return attachment(results_to_xlsx(_classify(*_report_input(body))), XLSX, "pp1875_report.xlsx")


@router.post("/report.docx", summary="Сводный отчёт в Word по списку товаров без создания задачи",
             response_class=Response, responses={200: {"content": {DOCX: {}}}})
def report_docx(body: ReportIn) -> Response:
    return attachment(report_to_docx(_classify(*_report_input(body))), DOCX, "pp1875_report.docx")


@router.post("/report/annotated.xlsx", summary="Вернуть загруженную таблицу Excel с дописанными результатами",
             response_class=Response, responses={200: {"content": {XLSX: {}}}})
async def report_annotated(request: Request) -> Response:
    """Файл специалиста остаётся как есть (его строки, колонки, оформление), справа дописываются код ОКПД2, режим,
    пункты ПП, уверенность и рекомендация; отдельным листом — сводка. Форма: `file` (.xlsx) и необязательное
    `codes` — JSON-список кодов, выбранных специалистом, по порядку наименований в файле."""
    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "filename"):
        raise HTTPException(422, "Прикрепите файл в поле file")
    try:
        codes = json.loads(form.get("codes") or "null")
        if codes is not None and not (isinstance(codes, list) and all(c is None or isinstance(c, str) for c in codes)):
            raise ValueError
    except ValueError:
        raise HTTPException(422, "Поле codes — JSON-список кодов ОКПД2 или null")
    limit = get_settings().batch_limit

    def run(names: list[str]) -> list[ClassificationResult]:
        if len(names) > limit:
            raise FileReadError(f"Не более {limit} товаров за один запрос (в файле {len(names)})")
        picked = (codes or []) + [None] * len(names)
        return _classify(names, [(c or "").strip() or None for c in picked[:len(names)]])

    try:
        data = annotate_xlsx(upload.filename or "", await upload.read(), run)
    except FileReadError as e:
        raise HTTPException(422, str(e))
    return attachment(data, XLSX, "pp1875_specification.xlsx")


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
