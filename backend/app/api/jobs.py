"""Статус пакетной задачи и выгрузка результатов в Excel."""
from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from app.db import SessionLocal
from app.io_files import results_to_xlsx
from app.models import Job, JobItem
from app.schemas import ClassificationResult, JobOut

router = APIRouter(tags=["Классификация"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _load(job_id: str) -> tuple[Job, list[ClassificationResult]]:
    with SessionLocal() as s:
        job = s.get(Job, job_id)
        if job is None:
            raise HTTPException(404, "Задача не найдена")
        rows = s.scalars(select(JobItem).where(JobItem.job_id == job_id).order_by(JobItem.idx))
        results = [ClassificationResult.model_validate(r.result) for r in rows if r.result is not None]
        return job, results


@router.get("/jobs/{job_id}", response_model=JobOut, summary="Статус и результаты пакетной задачи")
def get_job(job_id: str) -> JobOut:
    job, results = _load(job_id)
    return JobOut(job_id=job.id, status=job.status, total=job.total, done=job.done, error=job.error,
                  results=results if job.status == "done" else None)


@router.get("/jobs/{job_id}/export.xlsx", summary="Скачать результаты в Excel")
def export_job(job_id: str) -> Response:
    job, results = _load(job_id)
    if job.status != "done":
        raise HTTPException(409, "Задача ещё выполняется — выгрузка будет доступна после завершения")
    return Response(results_to_xlsx(results), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="pp1875_results.xlsx"'})
