"""Celery wiring: tasks registered, beat schedule covers all three jobs, broker configured.
(No worker/broker needed — importing the app registers tasks; we don't enqueue here.)"""
from __future__ import annotations

import app.tasks  # noqa: F401  — importing registers the @celery.task functions
from app.celery_app import celery

TASK_NAMES = {
    "dishport.recompute_svd",
    "dishport.retrain_als",
    "dishport.rebuild_taste_profiles",
}


def test_tasks_registered():
    assert TASK_NAMES <= set(celery.tasks)


def test_beat_schedule_covers_all_three_jobs():
    scheduled = {entry["task"] for entry in celery.conf.beat_schedule.values()}
    assert scheduled == TASK_NAMES
    for entry in celery.conf.beat_schedule.values():
        assert entry["schedule"] is not None


def test_broker_and_backend_configured():
    assert celery.conf.broker_url.startswith("redis://")
    assert celery.conf.result_backend.startswith("redis://")
