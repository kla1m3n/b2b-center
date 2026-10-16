"""База НПА: редакции ПП № 1875 и их позиции. Новая редакция загружается без передеплоя."""
import secrets
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select

from app.celery_app import process_npa_version
from app.config import get_settings
from app.db import SessionLocal
from app.models import NpaItem, NpaVersion
from app.npa.service import create_version
from app.schemas import Regime

router = APIRouter(prefix="/npa", tags=["База НПА"])
ALLOWED = (".json", ".xlsx")
MAX_BYTES = 20 * 1024 * 1024


class VersionOut(BaseModel):
    id: int
    title: str
    source_url: str
    uploaded_at: datetime
    status: str
    is_active: bool
    items_count: int
    error: str | None
    warnings: list[str]


class ItemOut(BaseModel):
    id: int
    version_id: int
    appendix: int
    item_no: str
    title: str
    codes: list[str]
    regime: Regime
    quota: int | None
    note: str
    has_conditions: bool
    source_url: str


class UploadOut(BaseModel):
    version_id: int


@router.get("/versions", response_model=list[VersionOut], summary="Редакции ПП 1875 (новые сверху)")
def versions() -> list[VersionOut]:
    with SessionLocal() as s:
        counts = dict(s.execute(select(NpaItem.version_id, func.count()).group_by(NpaItem.version_id)).all())
        return [
            VersionOut(id=v.id, title=v.title, source_url=v.source_url, uploaded_at=v.uploaded_at, status=v.status,
                       is_active=v.is_active, items_count=counts.get(v.id, 0), error=v.error, warnings=v.warnings or [])
            for v in s.scalars(select(NpaVersion).order_by(NpaVersion.id.desc()))
        ]


@router.post("/upload", response_model=UploadOut, status_code=202,
             summary="Загрузить новую редакцию ПП 1875 (.json или .xlsx) — без перезапуска сервиса")
async def upload(file: UploadFile = File(...), title: str = Form(""), source_url: str = Form(""),
                 x_admin_token: str | None = Header(None, description="Пароль администратора, если задан ADMIN_TOKEN")
                 ) -> UploadOut:
    expected = get_settings().admin_token
    if expected and not secrets.compare_digest((x_admin_token or "").encode(), expected.encode()):
        raise HTTPException(403, "Неверный пароль администратора")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(422, "Поддерживаются файлы .json и .xlsx (формат описан в README)")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(422, "Файл больше 20 МБ")
    upload_dir = Path(get_settings().upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{uuid4()}{suffix}"
    path.write_bytes(data)
    with SessionLocal() as s:
        v = create_version(s, path, title.strip(), source_url.strip())
        version_id = v.id
    process_npa_version.delay(version_id)
    return UploadOut(version_id=version_id)


@router.get("/items/{item_id}", response_model=ItemOut, summary="Позиция ПП 1875 (для ссылки «пункт постановления»)")
def item(item_id: int) -> ItemOut:
    with SessionLocal() as s:
        it = s.get(NpaItem, item_id)
        if it is None:
            raise HTTPException(404, "Позиция не найдена")
        v = s.get(NpaVersion, it.version_id)
        return ItemOut(id=it.id, version_id=it.version_id, appendix=it.appendix, item_no=it.item_no, title=it.title,
                       codes=it.codes, regime=Regime(it.regime), quota=it.quota, note=it.note,
                       has_conditions=it.has_conditions, source_url=v.source_url)
