"""Runs scheduler jobs from cPanel cron (the app itself keeps SCHEDULER_ENABLED=false,
because LiteSpeed starts and stops its processes). Job ids and functions are the
in-process scheduler's (app/workers/schedules.py).
Usage: python run_jobs.py publish_tasks plan_jobs ...
The cPanel crontab (one flock per cadence, so a slow run is skipped, not doubled):
  * * * * *    publish_tasks generation_tasks plan_jobs workflow_tasks
  */30 * * * * social_token_refresh
  0 */3 * * *  ad_tasks
  15 */6 * * * organic_metrics sync_tasks"""
import asyncio
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)  # settings read .env from the working directory
sys.path.insert(0, HERE)

import app.main  # noqa: E402,F401  registers every ORM model, as the API process does
from app.workers.schedules import JOBS  # noqa: E402

by_id = {j["id"]: j["func"] for j in JOBS}
failed = False
for job_id in sys.argv[1:]:
    func = by_id.get(job_id)
    if func is None:
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} unknown job {job_id}", flush=True)
        failed = True
        continue
    try:
        result = func()
        if asyncio.iscoroutine(result):
            asyncio.run(result)
    except Exception:
        failed = True
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} job {job_id} failed:", flush=True)
        traceback.print_exc()
sys.exit(1 if failed else 0)
