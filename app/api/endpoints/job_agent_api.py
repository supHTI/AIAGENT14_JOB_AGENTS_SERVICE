"""
Job Agent API Endpoints
"""

from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from typing import Optional, Dict, Any
from pydantic import BaseModel

from app.celery.tasks.job_agent_tasks import extract_resume_task
from app.cache_db.redis_config import get_redis_client
from app.database_layer.db_config import SessionLocal
from app.database_layer.db_model import TaskLogs

import logging
import uuid
import json
import base64
from datetime import datetime, timezone

logger = logging.getLogger("app_logger")

router = APIRouter(tags=["Job Agent"])

IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp', '.heic', '.svg'
}


def is_image_file(filename: str) -> bool:
    if not filename:
        return False
    return any(filename.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)


class JobAgentResponse(BaseModel):
    success: bool = True
    data: Dict[str, Any]


@router.post("/job_agent", response_model=JobAgentResponse)
async def job_agent(
    jd_text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    image_train: Optional[bool] = Form(None)
):
    """
    Job Agent Endpoint
    Queues a background task & returns task ID.
    """

    if (not jd_text or not jd_text.strip()) and not file:
        raise HTTPException(400, "Either jd_text or file must be provided.")

   
    task_id = str(uuid.uuid4())

    db = SessionLocal()
    try:
        new_log = TaskLogs(
            task_id=task_id,
            type="JOB_AGENT",
            key_id=None,
            status="STARTED",          
            error=None
        )
        db.add(new_log)
        db.commit()
        db.refresh(new_log)
        logger.info(f"[DB] TaskLogs created for {task_id}")

    except Exception as e:
        logger.error(f"[DB ERROR] Could not insert TaskLogs: {e}", exc_info=True)

    finally:
        db.close()

    try:
        redis_client = get_redis_client()

        initial_status = {
            "task_id": task_id,
            "status": "PENDING",
            "progress": 0,
            "message": "Task queued, waiting to start",
            "step": "queued",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        redis_client.setex(f"task:{task_id}", 3600, json.dumps(initial_status))
        redis_client.publish(f"task_status_updates:{task_id}", json.dumps(initial_status))

        logger.info(f"[REDIS] Initial status stored for {task_id}")

    except Exception as e:
        logger.error(f"[REDIS ERROR] Could not set initial status: {e}")


    task_data = {
        "task_id": task_id,
        "jd_text": jd_text.strip() if jd_text else "",
    }

    if file:
        file_bytes = await file.read()

        if not file_bytes:
            raise HTTPException(400, "Uploaded file is empty.")

        is_img = is_image_file(file.filename)

        # Auto-enable image OCR
        if is_img:
            image_train = True
        elif image_train is None:
            image_train = False

        file_b64 = base64.b64encode(file_bytes).decode("utf-8")

        task_data.update({
            "file_content_b64": file_b64,
            "filename": file.filename,
            "image_train": bool(image_train)
        })

        logger.info(f"[FILE] Processing: {file.filename}, OCR={image_train}")


    try:
        extract_resume_task.delay(task_data)
        logger.info(f"[CELERY] Task queued: {task_id}")

    except Exception as e:
        logger.error(f"[CELERY ERROR] Failed to queue task: {e}")
        raise HTTPException(500, "Failed to queue extraction task")

   
    return JobAgentResponse(
        success=True,
        data={
            "task_id": task_id,
            "status": "PENDING",
            "filename": file.filename if file else None
        }
    )

@router.get("/job_agent/result/{task_id}")
def get_job_agent_result(task_id: str):

    redis = get_redis_client()

    # Check task processing status from Redis
    redis_status = redis.get(f"task:{task_id}")
    
    status_data = json.loads(redis_status) if redis_status else None

    if not status_data:
        raise HTTPException(404, "Invalid or expired task_id")

    state = status_data.get("status")

    # STILL PROCESSING
    if state in ["PENDING", "STARTED", "PROGRESS", "RETRY"]:
        return {
            "success": True,
            "data": {
                "task_id": task_id,
                "status": state,
                "progress": status_data.get("progress"),
                "message": status_data.get("message", "Task is processing")
            }
        }

    # POSSIBLE FAILURE
    if state in ["FAILED", "FAILURE"]:
        return {
            "success": False,
            "data": {
                "task_id": task_id,
                "status": state,
                "error": status_data.get("error", "Unknown error")
            }
        }

    # SUCCESS 
    if state == "SUCCESS":
        redis_result = redis.get(f"task_result:{task_id}")
        if not redis_result:
            return {
                "success": False,
                "data": {
                    "task_id": task_id,
                    "status": "SUCCESS",
                    "message": "Task finished but result not available yet"
                }
            }

        return {
            "success": True,
            "data": {
                "task_id": task_id,
                "status": "SUCCESS",
                "result": json.loads(redis_result)
            }
        }

