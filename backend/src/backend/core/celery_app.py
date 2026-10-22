from celery import Celery

from backend.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "backend",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["backend.tasks.ingestion"],
)
# Tasks acknowledge their message only when done: reserve one message at a time so
# a busy process never holds messages it has not started.
celery_app.conf.worker_prefetch_multiplier = 1
