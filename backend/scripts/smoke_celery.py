"""Run the three batch tasks in-process (no worker/broker) against the live DB, to verify the
task bodies execute and return their summaries. Seed first (e.g. scripts/smoke_recommend.py).

    DP_DATABASE_URL=postgresql://... PYTHONPATH=. python scripts/smoke_celery.py
"""
from __future__ import annotations

from app.tasks import recompute_svd_task, rebuild_taste_profiles_task, retrain_als_task

svd = recompute_svd_task()
als = retrain_als_task()
taste = rebuild_taste_profiles_task()

print("recompute_svd          ->", svd)
print("retrain_als            ->", als)
print("rebuild_taste_profiles ->", taste)

assert svd["status"] in {"ok", "skipped"}
assert als["status"] in {"ok", "skipped"}
assert taste["status"] == "ok"
print("\nCELERY SMOKE OK — all three batch tasks ran in-process against the live DB.")
