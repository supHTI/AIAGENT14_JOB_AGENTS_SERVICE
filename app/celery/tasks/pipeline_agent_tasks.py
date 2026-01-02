import json
import random
import logging
from datetime import datetime, timezone

from app.celery.celery_config import celery_app
from app.models.pipeline_model import pipeline_agent
from app.utils import file_handler
from app.cache_db import get_redis_client
from app.api.dependencies.progress import report_progress
from app.database_layer.db_store import (
    save_pipeline,
    save_pipeline_stages_with_statuses,
)

logger = logging.getLogger("app_logger")
redis_client = get_redis_client()


def generate_pipeline_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    random_number = random.randint(1000, 9999)
    return f"PIPE_{timestamp}_{random_number}"


@celery_app.task(bind=True, queue="job_queue")
def pipeline_agent_task(self, task_data: dict):
    task_id = self.request.id

    jd_text = task_data.get("jd_text", "")
    file_content_b64 = task_data.get("file_content_b64", "")
    filename = task_data.get("filename", "")
    image_train = task_data.get("image_train", False)

    try:
        report_progress(task_id, "STARTED", 10, "Pipeline task started")

        if file_content_b64:
            report_progress(task_id, "PROGRESS", 30, "Extracting job description")
            jd_text = file_handler.extract_text(
                file_content_b64=file_content_b64,
                filename=filename,
                perform_ocr=image_train,
                task_id=task_id,
            )

        if not jd_text:
            raise Exception("No job description text found")

        report_progress(task_id, "PROGRESS", 60, "Extracting pipeline structure")

        pipeline_data = pipeline_agent.extract_pipeline_data(jd_text)


        pipeline_data["pipeline_id"] = generate_pipeline_id()

       
        pipeline_db_id = save_pipeline(pipeline_data)

        save_pipeline_stages_with_statuses(
            pipeline_id=pipeline_db_id,
            stages=pipeline_data.get("interview_stages", []),
        )

        redis_client.setex(
            f"task_status:{task_id}",
            15 * 60*60,
            json.dumps(
                {
                    "pipeline_db_id": pipeline_db_id,
                    "pipeline_data": pipeline_data,
                    "filename": filename,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }
            ),
        )

        report_progress(task_id, "SUCCESS", 100, "Pipeline created successfully")
        self.update_state(state="SUCCESS")

        return {
            "task_id": task_id,
            "status": "SUCCESS",
            "pipeline_db_id": pipeline_db_id,
        }

    except Exception as e:
        logger.error(f"Pipeline agent failed: {e}", exc_info=True)
        report_progress(task_id, "FAILURE", 0, str(e))
        raise
