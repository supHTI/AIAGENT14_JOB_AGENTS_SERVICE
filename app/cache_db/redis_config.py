"""
Redis Configuration Module

This module handles Redis connection setup and configuration
for caching and Celery message broker.

Author: [Supriyo Chowdhury]
Version: 1.0
Last Modified: [2024-12-19]
"""

import redis
from app.core import settings
import logging

logger = logging.getLogger("app_logger")

def get_redis_client():
    """
    Create and return a Redis client instance.
    
    Returns:
        redis.Redis: Redis client instance
    """
    try:
        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=int(settings.REDIS_PORT),
            db=int(settings.REDIS_DB),
            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
        # Test connection
        redis_client.ping()
        logger.info("Redis client connected successfully")
        return redis_client
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise

# Redis URL for Celery
def get_redis_url() -> str:
    """
    Get Redis URL for Celery broker and backend.
    
    Returns:
        str: Redis URL string
    """
    password_part = f":{settings.REDIS_PASSWORD}@" if settings.REDIS_PASSWORD else ""
    redis_url = f"redis://{password_part}{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
    logger.debug(f"Redis URL configured: redis://****@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}")
    return redis_url

