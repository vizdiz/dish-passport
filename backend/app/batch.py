"""CLI entrypoint for the batch jobs. Azure Container Apps Jobs (cron-scheduled) run
`python app/batch.py <name>`; each invocation runs one batch task synchronously against the DB
and exits. No broker needed (the Celery task bodies don't touch Redis when called directly).

    PYTHONPATH=/app python app/batch.py {svd|als|taste}
"""
from __future__ import annotations

import sys

from app.tasks import (
    rebuild_taste_profiles_task,
    recompute_svd_task,
    retrain_als_task,
)

TASKS = {
    "svd": recompute_svd_task,
    "als": retrain_als_task,
    "taste": rebuild_taste_profiles_task,
}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in TASKS:
        print(f"usage: python app/batch.py {{{'|'.join(TASKS)}}}", file=sys.stderr)
        raise SystemExit(2)
    name = sys.argv[1]
    print(f"{name}: {TASKS[name]()}")


if __name__ == "__main__":
    main()
