"""
Celery application configuration.
"""

from celery import Celery

from ..config import get_settings

settings = get_settings()

# Redis URL for broker and backend
REDIS_URL = getattr(settings, "redis_url", "redis://localhost:6379/0")

# Create Celery app
celery_app = Celery(
    "campaign_generator",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "api.tasks.idea_tasks",
        "api.tasks.research_tasks",
        "api.tasks.outreach_tasks",
    ]
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max
    task_soft_time_limit=3300,  # 55 minutes soft limit
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
)
