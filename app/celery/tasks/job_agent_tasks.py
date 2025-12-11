from app.celery.celery_config import celery_app
from app.models import job_agent
from app.utils import file_handler
from app.cache_db import get_redis_client
from app.api.dependencies.progress import report_progress

import logging
import json
import base64
from datetime import datetime, timezone
redis_client = get_redis_client()

logger = logging.getLogger("app_logger")


@celery_app.task(bind=True, queue="job_queue")
def job_agent_task(self, task_data: dict):
    
    #Validate the task data
    task_id = self.request.id

    jd_text = task_data.get('jd_text', '')
    file_content_b64 = task_data.get('file_content_b64', '')
    filename = task_data.get('filename', '')
    image_train = task_data.get('image_train', False)

    structured_data = None
    type = "job_agent"

    try:
        report_progress(task_id, "STARTED", 15, "Task started")

        report_progress(task_id, "PROGRESS", 35, "Processing file")


        if file_content_b64:
            jd_text = file_handler.extract_text(
                file_content_b64=file_content_b64,
                filename=filename,
                perform_ocr=image_train,
                task_id=task_id
            )
        # If no file was provided, fall back to any jd_text passed in task_data
        else:
            jd_text = jd_text or ""
            
        report_progress(task_id, "PROGRESS", 75, "Running AI extraction")

        if not jd_text:
            raise Exception("No text extracted from file")
        structured_data = job_agent.extract_job_data(
            jd_text=jd_text
        )

        
        redis_client.setex(
            f"job_agent_task_result:{task_id}",
            15*60,
            json.dumps({
                "structured_data": structured_data,
                "filename": filename,
                "completed_at": datetime.now(timezone.utc).isoformat()
            })
        )

    
        self.update_state(state="SUCCESS")
        report_progress(task_id, "SUCCESS", 100, "Task completed")

        return {
            "task_id": task_id,
            "status": "SUCCESS",
            "structured_data": structured_data
        }


    except Exception as e:
        logger.error(f"Job agent task error: {e}")
        report_progress(task_id, "FAILURE", 0, f"Error: {str(e)}")

        raise
