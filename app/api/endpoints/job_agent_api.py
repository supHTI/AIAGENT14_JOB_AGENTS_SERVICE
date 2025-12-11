"""
Job Agent API Endpoints
"""

from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from typing import Optional, Dict, Any
from pydantic import BaseModel


from app.cache_db.redis_config import get_redis_client
from app.database_layer import JobAgentResponse

import logging
import uuid
import json
import base64
from datetime import datetime, timezone

logger = logging.getLogger("app_logger")
router = APIRouter(tags=["Job Agent"])
redis_client = get_redis_client()
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png'
}


def is_image_file(filename: str) -> bool:
    if not filename:
        return False
    return any(filename.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)


class JobAgentResponse(BaseModel):
    task_id: str
    status: str
    message: str


@router.post("/job_agent", response_model=JobAgentResponse)
async def job_agent(
    jd_text: Optional[str] = Form(None, description="Job description text"),
    file: Optional[UploadFile] = File(None, description="Job description file"),
    image_train: Optional[bool] = Form(None, description="Whether to perform OCR on the file")
):
    """
    Job Agent Endpoint
    Queues a background task & returns task ID.
    """
    from app.celery.tasks.job_agent_tasks import job_agent_task

    if (not jd_text or not jd_text.strip()) and not file:
        raise HTTPException(400, "Either jd_text or file must be provided.")
    

    if file:
        file_bytes = await file.read()

        if not file_bytes:
            raise HTTPException(400, "Uploaded file is empty.")
        
        #Check if the file is an image
        is_img = is_image_file(file.filename)

        # Auto-enable image OCR
        if is_img:
            image_train = True
        elif image_train is None:
            image_train = False

        #Encode the file to base64
        file_b64 = base64.b64encode(file_bytes).decode("utf-8")
        
        #Prepare the task data
        task_data = {
            "file_content_b64": file_b64,
            "filename": file.filename,
            "image_train": bool(image_train)
        }

        logger.info(f"[FILE] Processing: {file.filename}, OCR={image_train}")
    else:
        task_data = {
            "jd_text": jd_text
        }


    try:
        task = job_agent_task.delay(task_data)

        logger.info(f"[CELERY] Task queued: {task.id}")

    except HTTPException as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")
    except Exception as e:
        logger.error(f"[CELERY ERROR] Failed to queue task: {e}")
        raise e

   
    return JobAgentResponse(
        task_id=task.id,
        status="pending",
        message="Task queued successfully"
    )

@router.get("/job_agent/result/{task_id}")
def get_job_agent_result(task_id: str):

    

    # Check task processing status from Redis (set by report_progress)
    redis_status = redis_client.get(f"task:{task_id}")
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
                "message": status_data.get("message", "Task is processing"),
            },
        }

    # POSSIBLE FAILURE
    if state in ["FAILED", "FAILURE"]:
        return {
            "success": False,
            "data": {
                "task_id": task_id,
                "status": state,
                "error": status_data.get("error", "Unknown error"),
            },
        }

    # SUCCESS
    if state == "SUCCESS":
        # Result stored by job_agent_task
        redis_result = redis_client.get(f"job_agent_task_result:{task_id}")
        if not redis_result:
            return {
                "success": False,
                "data": {
                    "task_id": task_id,
                    "status": "SUCCESS",
                    "message": "Task finished but result not available yet",
                },
            }

        return {
            "success": True,
            "data": {
                "task_id": task_id,
                "status": "SUCCESS",
                "result": json.loads(redis_result),
            },
        }

