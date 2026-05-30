"""Celery app + Beat schedule for the three batch jobs.

Run a worker:  celery -A app.celery_app.celery worker -l info
Run the beat:  celery -A app.celery_app.celery beat   -l info
(both need DP_DATABASE_URL set and Redis reachable at DP_CELERY_BROKER_URL.)

Tasks live in app/tasks.py (loaded via `include`, avoiding a circular import). They wrap the
async batch services on a short-lived asyncpg pool — the ONLY place those services run in prod.
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import Settings

settings = Settings()

celery = Celery(
    "dishport",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)

# Batch cadence (tunable). Taste profiles shift with every log/impression -> hourly; ALS
# benefits from a nightly full refit; the SVD flavor structure is stable -> weekly. SVD runs
# before the nightly window it feeds, so taste profiles pick up fresh factors.
celery.conf.beat_schedule = {
    "rebuild-taste-profiles": {
        "task": "dishport.rebuild_taste_profiles",
        "schedule": crontab(minute=0),                          # top of every hour
    },
    "retrain-als": {
        "task": "dishport.retrain_als",
        "schedule": crontab(hour=3, minute=0),                  # nightly 03:00 UTC
    },
    "recompute-svd": {
        "task": "dishport.recompute_svd",
        "schedule": crontab(hour=4, minute=0, day_of_week=0),   # weekly, Sun 04:00 UTC
    },
}
