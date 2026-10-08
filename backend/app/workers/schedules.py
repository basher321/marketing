"""Job registration list for the APScheduler instance — one entry per app/workers/tasks/ module.

Cadences are placeholders (the jobs are inert stubs right now); retune once
each task module gets real business logic.
"""
from typing import Any

from app.workers.tasks import (
    ad_tasks,
    analytics_tasks,
    content_tasks,
    generation_tasks,
    notification_tasks,
    optimization_tasks,
    publish_tasks,
    sync_tasks,
    workflow_tasks,
)

JOBS: list[dict[str, Any]] = [
    # SPEC-BE-056: Meta results + status import every 3 hours.
    {"func": ad_tasks.run_ad_tasks, "id": "ad_tasks", "trigger": "interval", "hours": 3},
    {"func": analytics_tasks.rollup_metrics, "id": "analytics_tasks", "trigger": "interval", "hours": 1},
    # SPEC-BE-078: organic post results every 6 hours.
    {"func": analytics_tasks.import_organic_metrics_all, "id": "organic_metrics", "trigger": "interval", "hours": 6},
    {"func": content_tasks.generate_content_async, "id": "content_tasks", "trigger": "interval", "hours": 1},
    {"func": notification_tasks.notify_owner, "id": "notification_tasks", "trigger": "interval", "hours": 1},
    {
        "func": optimization_tasks.run_optimizer_pass,
        "id": "optimization_tasks",
        "trigger": "interval",
        "minutes": 30,
    },
    # SPEC-BE-076: organic posts are published on time - checked every minute.
    {"func": publish_tasks.publish_scheduled_post, "id": "publish_tasks", "trigger": "interval", "minutes": 1},
    # SPEC-BE-077: resume photo/video generations a restart left behind.
    {"func": generation_tasks.resume_generation_jobs, "id": "generation_tasks", "trigger": "interval", "minutes": 1},
    # SPEC-BE-058: shipping re-sync from connected stores every 6 hours.
    {"func": sync_tasks.run_sync_tasks, "id": "sync_tasks", "trigger": "interval", "hours": 6},
    # SPEC-BE-080: social sign-in tokens (TikTok 24 h, LinkedIn 60 days) renewed ahead of expiry.
    {"func": sync_tasks.refresh_social_tokens, "id": "social_token_refresh", "trigger": "interval", "minutes": 30},
    {
        # SPEC-BE-060: cron-triggered workflows, checked every minute.
        "func": workflow_tasks.dispatch_cron_workflows,
        "id": "workflow_tasks",
        "trigger": "interval",
        "minutes": 1,
    },
]
