from src.workers.celery_app import celery_app

# Import tasks for registration side effects (Celery worker/beat loads this package).
import src.workers.poller  # noqa: F401

__all__ = ["celery_app"]
