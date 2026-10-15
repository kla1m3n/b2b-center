from fastapi import APIRouter

from app import state
from app.db import SessionLocal, db_alive
from app.npa.service import get_active_version
from app.schemas import HealthOut

router = APIRouter()


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    db_ok = db_alive()
    ready = db_ok and state.models_ready
    title = None
    if db_ok:
        with SessionLocal() as s:  # из БД, а не из памяти: после загрузки новой редакции ПП название меняется
            v = get_active_version(s)
            title = v.title if v else None
    return HealthOut(
        status="ok" if ready else "starting",
        db=db_ok,
        models=state.models_ready,
        npa_version=title,
    )
