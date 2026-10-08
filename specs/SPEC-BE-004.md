Purpose
Fix the backend's in-process job scheduler so it uses APScheduler (already listed
in requirements.txt) instead of the currently broken Celery references in
app/workers/celery_app.py, and wire it into the app's existing startup and
shutdown lifecycle.

Scope
The existing files under backend/app/workers/ and
backend/app/services/scheduler_service.py, plus two small additions to
backend/app/main.py and backend/app/config.py. No new files or folders are
created. No task business logic (ads, analytics, content, etc.) is implemented
in this step - only the scheduler foundation and inert stub jobs.

Contract
After this step: backend/app/workers/celery_app.py imports cleanly and exposes
a working APScheduler singleton; the app starts and stops the scheduler
automatically; each existing task module in backend/app/workers/tasks/ exposes
one stub job function that is registered but does nothing real yet.

Functional rules
-  celery_app.py exposes get_scheduler(), returning one shared AsyncIOScheduler
  instance for the whole process.
-  celery_app.py imports get_settings from app.config - not a nonexistent
  settings object (the current cause of the ImportError).
-  schedules.py lists every job to register: one entry per file in
  app/workers/tasks/.
-  retry_policy.py provides a retry helper: exponential backoff, 6 attempts
  max, used by jobs that call external services.
-  scheduler_service.py provides start_scheduler(), shutdown_scheduler(), and
  get_scheduler_status().
-  main.py's existing startup event starts the scheduler; its existing
  shutdown event stops it. Nothing else in main.py changes.
-  config.py gains two settings: SCHEDULER_ENABLED (default on) and
  SCHEDULER_TIMEZONE (default UTC).
-  Each file in app/workers/tasks/ exposes one async stub function: takes the
  parameters it will eventually need, logs that it is a stub, returns without
  doing real work.

Edge cases
-  If SCHEDULER_ENABLED is off, the app starts normally and logs that the
  scheduler is disabled - it does not start.
-  If a job's retry helper exhausts all attempts, the original error is
  raised, not swallowed.
-  Do not add celery, redis, or any other broker library.

Non-functional rules
No new files or folders - rewrite only the 13 files listed below. No test
framework exists in this project yet, so verification is by running the app
and checking output directly, not by writing test files.

Acceptance criteria
-  Importing app.workers.celery_app succeeds with no error.
-  Starting the app with uvicorn shows the scheduler starting and lists as
  many jobs as there are task files.
-  Stopping the app shows the scheduler shutting down cleanly.
-  Setting SCHEDULER_ENABLED to false and restarting shows the scheduler
  skipped, not started.

Assumptions
apscheduler is already installed (spec 1). app/main.py already has startup
and shutdown event handlers. app/config.py already has a working Settings
class (spec 3).

Target files (all existing - none added, none removed):
backend/app/workers/celery_app.py
backend/app/workers/schedules.py
backend/app/workers/retry_policy.py
backend/app/services/scheduler_service.py
backend/app/main.py
backend/app/config.py
backend/app/workers/tasks/ad_tasks.py
backend/app/workers/tasks/analytics_tasks.py
backend/app/workers/tasks/content_tasks.py
backend/app/workers/tasks/notification_tasks.py
backend/app/workers/tasks/optimization_tasks.py
backend/app/workers/tasks/publish_tasks.py
backend/app/workers/tasks/sync_tasks.py
backend/app/workers/tasks/workflow_tasks.py
