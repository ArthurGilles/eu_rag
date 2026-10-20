from celery import Celery

from backend.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "backend",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
