"""Статус пакетной задачи, сводка и выгрузка отчётов (Excel, Word)."""
from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from app.db import SessionLocal
from app.exports import report_to_docx, results_to_xlsx
from app.models import Job, JobItem
from app.report import summarize
from app.schemas import ClassificationResult, JobOut

router = APIRouter(tags=["Классификация"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def attachment(data: bytes, media_type: str, filename: str) -> Response:
    return Response(data, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _load(job_id: str) -> tuple[Job, list[ClassificationResult]]:
    with SessionLocal() as s:
        job = s.get(Job, job_id)
        if job is None:
            raise HTTPException(404, "Задача не найдена")
        rows = s.scalars(select(JobItem).where(JobItem.job_id == job_id).order_by(JobItem.idx))
        results = [ClassificationResult.model_validate(r.result) for r in rows if r.result is not None]
        return job, results


def _done(job_id: str) -> list[ClassificationResult]:
    job, results = _load(job_id)
    if job.status != "done":
        raise HTTPException(409, "Задача ещё выполняется — выгрузка будет доступна после завершения")
    return results


@router.get("/jobs/{job_id}", response_model=JobOut, summary="Статус, результаты и сводка пакетной задачи")
def get_job(job_id: str) -> JobOut:
    job, results = _load(job_id)
    done = job.status == "done"
    return JobOut(job_id=job.id, status=job.status, total=job.total, done=job.done, error=job.error,
                  results=results if done else None, summary=summarize(results) if done else None)


@router.get("/jobs/{job_id}/export.xlsx", summary="Скачать отчёт в Excel: лист сводки и лист результатов")
def export_job(job_id: str) -> Response:
    return attachment(results_to_xlsx(_done(job_id)), XLSX, "pp1875_report.xlsx")


@router.get("/jobs/{job_id}/report.docx", summary="Скачать сводный отчёт в Word: сводка, ручная проверка, обоснования")
def report_job(job_id: str) -> Response:
    return attachment(report_to_docx(_done(job_id)), DOCX, "pp1875_report.docx")
