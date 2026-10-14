from celery import Celery

from app.config import get_settings

celery = Celery("pp1875", broker=get_settings().redis_url, backend=get_settings().redis_url)
celery.conf.update(task_track_started=True, worker_prefetch_multiplier=1, task_acks_late=True)
