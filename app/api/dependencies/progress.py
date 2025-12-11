
import redis
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from app.core import settings

logger = logging.getLogger("app_logger")

# Redis connection with error handling
try:
    r = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        decode_responses=True
    )
    
    # Test connection
    r.ping()
    logger.info("Redis connection established successfully")
except redis.ConnectionError as e:
    logger.error(f"Failed to connect to Redis: {e}")
    r = None
except Exception as e:
    logger.error(f"Redis initialization error: {e}")
    r = None

def report_progress(task_id: str, status: str, progress: int, message: str = "", task_type: str = "job_agent", error: str = None):
    """
    Store task progress in Redis as JSON with error handling.
    """
    if not task_id or not isinstance(task_id, str):
        logger.error("Invalid task_id provided to report_progress")
        return False
        
    if not isinstance(progress, int) or progress < 0 or progress > 100:
        logger.error(f"Invalid percent value: {progress}")
        return False

    data = {
        "task_id": task_id,
        "status": status,
        "progress": progress,
        "message": message or "",
        "type": task_type,
        "error": error,
        "updated_at": datetime.utcnow().isoformat()
    }
    
    try:
        if r is None:
            logger.error("Redis not available, cannot store progress")
            return False
            
        r.set(f"task:{task_id}", json.dumps(data), ex=3600)  # Expire after 1 hour
        logger.debug(f"Progress stored for task {task_id}: {status} - {progress}%")
        return True
        
    except redis.RedisError as e:
        logger.error(f"Redis error storing progress for task {task_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error storing progress for task {task_id}: {e}")
        return False

def get_progress(task_id: str) -> Optional[Dict[str, Any]]:
    """
    Get progress from Redis with error handling.
    """
    if not task_id or not isinstance(task_id, str):
        logger.error("Invalid task_id provided to get_progress")
        return None
        
    try:
        if r is None:
            logger.error("Redis not available, cannot retrieve progress")
            return None
            
        data = r.get(f"task:{task_id}")
        if data:
            return json.loads(data)
        else:
            logger.debug(f"No progress data found for task {task_id}")
            return None
            
    except redis.RedisError as e:
        logger.error(f"Redis error retrieving progress for task {task_id}: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error for task {task_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error retrieving progress for task {task_id}: {e}")
        return None

def delete_progress(task_id: str) -> bool:
    """
    Delete progress data from Redis.
    """
    if not task_id or not isinstance(task_id, str):
        logger.error("Invalid task_id provided to delete_progress")
        return False
        
    try:
        if r is None:
            logger.error("Redis not available, cannot delete progress")
            return False
            
        result = r.delete(f"task:{task_id}")
        logger.debug(f"Progress deleted for task {task_id}: {result}")
        return bool(result)
        
    except redis.RedisError as e:
        logger.error(f"Redis error deleting progress for task {task_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error deleting progress for task {task_id}: {e}")
        return False
