"""
Celery Worker Entry Point

This module is the entry point for running Celery workers.

Usage:
    uv run celery -A celery_worker worker --loglevel=info --pool=threads --concurrency=4

Author: [Supriyo Chowdhury]
Version: 1.0
Last Modified: [2024-12-19]
"""

from app.celery import celery_app

# This allows Celery to discover the app
if __name__ == "__main__":
    celery_app.start()

