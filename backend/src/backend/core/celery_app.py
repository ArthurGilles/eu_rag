import os

from celery import Celery

celery_app = Celery(
    "backend",
    broker=os.environ["REDIS_URL"],
    backend=os.environ["REDIS_URL"],
)
