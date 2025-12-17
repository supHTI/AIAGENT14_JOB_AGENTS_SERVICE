"""
Celery Configuration Module

This module configures Celery for background task processing
with Redis as message broker and result backend.

Author: [Supriyo Chowdhury]
Version: 1.0
Last Modified: [2024-12-19]
"""

from celery import Celery
from celery.schedules import crontab
from app.cache_db.redis_config import get_redis_url
import logging

logger = logging.getLogger("app_logger")

# Get Redis URL
redis_url = get_redis_url()

# Create Celery app
# Include all task modules so workers register all tasks
celery_app = Celery(
    "job_agents_service",
    broker=redis_url,
    backend=redis_url,
    include=[
        "app.celery.tasks.job_post_tasks",
        "app.celery.tasks.job_agent_tasks",
        "app.celery.tasks.cooling_period_tasks",
        "app.celery.tasks.call_processing_tasks",
    ],
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    # Thread pool configuration for 4 workers
    worker_pool="threads",
    worker_concurrency=4,
    # Route everything to the single job queue
    task_default_queue="job_queue",
    task_queues={
        "job_queue": {
            "exchange": "job_queue",
            "routing_key": "job_queue",
        }
    },
    # Celery Beat schedule for periodic tasks
    beat_schedule={
        "send-daily-cooling-period-reminders": {
            "task": "send_daily_cooling_period_reminders",
            "schedule": crontab(minute='*/1'),  # Run eve ry 1 minute
            # "schedule": crontab(hour=9, minute=0),  # Run daily at 9:00 AM UTC
            "options": {"queue": "job_queue"},
        },
    },
)
 
logger.info("Celery app configured successfully with beat schedule")

