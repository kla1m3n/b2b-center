from celery import Celery
from sqlalchemy import select

from app.classifier.pipeline import get_pipeline
from app.config import get_settings
from app.db import SessionLocal
from app.models import Job, JobItem

CHUNK = 25  # прогресс «обработано N из M» обновляется после каждой порции

celery = Celery("pp1875", broker=get_settings().redis_url, backend=get_settings().redis_url)
celery.conf.update(task_track_started=True, worker_prefetch_multiplier=1, task_acks_late=True)


@celery.task(name="classify_job")
def classify_job(job_id: str) -> None:
    with SessionLocal() as s:
        job = s.get(Job, job_id)
        items = list(s.scalars(select(JobItem).where(JobItem.job_id == job_id).order_by(JobItem.idx)))
        job.status = "running"
        s.commit()
        try:
            pipe = get_pipeline()
            for i in range(0, len(items), CHUNK):
                chunk = items[i:i + CHUNK]
                for item, res in zip(chunk, pipe.classify_many([it.input for it in chunk], job.npa_version_id)):
                    item.result = res.model_dump(mode="json")
                job.done = i + len(chunk)
                s.commit()
            job.status = "done"
        except Exception as e:  # ошибка задачи не должна оставлять её «вечно выполняющейся»
            s.rollback()
            job = s.get(Job, job_id)
            job.status, job.error = "failed", f"Ошибка обработки: {e}"
        s.commit()


@celery.task(name="process_npa_version")
def process_npa_version(version_id: int) -> None:
    from app.npa.service import process_version

    with SessionLocal() as s:
        process_version(s, version_id)
