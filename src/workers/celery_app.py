from __future__ import annotations

from celery import Celery

from src.config import get_settings


settings = get_settings()

celery_app = Celery(
    "agentbox",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Celery CLI usually looks for `app` or `celery` in the module.
app = celery_app
celery = celery_app

__all__ = ["celery_app"]

