"""One scheduler process per deployment; opt-in Compose profile."""

import os
import time

from backend import database
from backend.scheduler import run_scheduled_refresh


def main() -> None:
    if not os.getenv("ERP_SCHEDULER_ACTOR", "").strip():
        raise RuntimeError("ERP_SCHEDULER_ACTOR is required for the scheduler profile")
    database.init_db()
    interval = max(int(os.getenv("ERP_SCHEDULER_INTERVAL_SECONDS", "86400")), 60)
    while True:
        result = run_scheduled_refresh()
        print(f"scheduler status={result.get('status')} job_key={result.get('job_key')}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    main()
