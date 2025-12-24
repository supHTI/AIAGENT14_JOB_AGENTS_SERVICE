"""
Celery Configuration Module

This module configures Celery for background task processing
with Redis as message broker and result backend.

Author: [Supriyo Chowdhury]
Version: 1.0
Last Modified: [2024-12-19]
"""

from celery import Celery
from app.cache_db.redis_config import get_redis_url
import logging
from celery.schedules import crontab

# Optionally load environment variables from a .env file so workers pick up API keys
try:
    from dotenv import load_dotenv
    load_dotenv()
    logging.getLogger("app_logger").info("Loaded .env into environment for Celery workers")
except Exception:
    logging.getLogger("app_logger").info("python-dotenv not installed; skipping .env load")

logger = logging.getLogger("app_logger")

# Get Redis URL
redis_url = get_redis_url()

# Create Celery app
# Include both job_post_tasks and job_agent_tasks so workers register all tasks
celery_app = Celery(
    "job_agents_service",
    broker=redis_url,
    backend=redis_url,
    include=[
        "app.celery.tasks.job_post_tasks",
        "app.celery.tasks.job_agent_tasks",
        "app.celery.tasks.cooling_period_task",
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
    task_time_limit=30,  # 30 seconds
    task_soft_time_limit=25,  # 25 seconds
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
    # 🔥 Daily 08:00 AM IST Scheduler
    beat_schedule={
        "test-cooling-period-reminders": {
            "task": "send_daily_cooling_period_reminders",
            "schedule":30, # crontab(hour=8, minute=0),  # Every 30 seconds for testing
            "options": {"queue": "job_queue"},
        },
        "send-admin-cooling-period-summary": {
            "task": "send_admin_cooling_period_summary",
            "schedule": 30,  # Daily at 08:00 AM UTC
            "options": {"queue": "job_queue"},
        },
    },
)

logger.info("Celery app configured successfully")

