from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("hydrosage", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_routes = {}
