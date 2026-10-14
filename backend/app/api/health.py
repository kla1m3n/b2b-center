from fastapi import APIRouter

from app import state
from app.db import db_alive
from app.schemas import HealthOut

router = APIRouter()


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    db_ok = db_alive()
    ready = db_ok and state.models_ready
    return HealthOut(
        status="ok" if ready else "starting",
        db=db_ok,
        models=state.models_ready,
        npa_version=state.npa_version_title,
    )
