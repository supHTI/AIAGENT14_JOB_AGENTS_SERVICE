from app.celery import celery_app
from app.models.job_agents import resume_extractor_agent
from app.utils.file_handler import FileHandler
from app.cache_db.redis_config import get_redis_client
from app.api.dependencies.progress import report_progress
from app.database_layer.db_config import SessionLocal
from app.database_layer.db_model import TaskLogs

import logging
import json
import base64
from datetime import datetime, timezone

logger = logging.getLogger("app_logger")


@celery_app.task(bind=True, queue="extract_resume_task")
def extract_resume_task(self, task_data: dict):

    task_id = task_data.get("task_id")
    jd_text = task_data.get("jd_text", "")
    file_content_b64 = task_data.get("file_content_b64")
    filename = task_data.get("filename")
    image_train = task_data.get("image_train", False)

    structured_data = None
    type = "JOB_AGENT"

    db = SessionLocal()

    try:
        self.update_state(state="STARTED")
        report_progress(task_id, "STARTED", 15, "Task started", type)

        # Update DB → STARTED
        log = db.query(TaskLogs).filter(TaskLogs.task_id == task_id).first()
        if log:
            log.status = "STARTED"
            log.error = None
            db.commit()

        report_progress(task_id, "PROGRESS", 35, "Processing file", type)

    
        log = db.query(TaskLogs).filter(TaskLogs.task_id == task_id).first()
        if log:
            log.status = "PROGRESS"
            db.commit()

        if file_content_b64:
            file_bytes = base64.b64decode(file_content_b64)
            resume_text = FileHandler.extract_text(
                file_bytes=file_bytes,
                filename=filename,
                perform_ocr=image_train
            )
        else:
            resume_text = ""
            
        report_progress(task_id, "PROGRESS", 75, "Running AI extraction", type)

        # Update DB → PROGRESS
        log = db.query(TaskLogs).filter(TaskLogs.task_id == task_id).first()
        if log:
            log.status = "PROGRESS"
            db.commit()

        structured_data = resume_extractor_agent.extract_resume_data(
            resume_data=resume_text,
            jd_text=jd_text
        )

        redis = get_redis_client()
        redis.setex(
            f"task_result:{task_id}",
            3600,
            json.dumps({
                "structured_data": structured_data,
                "filename": filename,
                "completed_at": datetime.now(timezone.utc).isoformat()
            })
        )

    
        self.update_state(state="SUCCESS")
        report_progress(task_id, "SUCCESS", 100, "Task completed", type)

        # Update DB → SUCCESS
        log = db.query(TaskLogs).filter(TaskLogs.task_id == task_id).first()
        if log:
            log.status = "SUCCESS"
            log.error = None
            db.commit()

        return {
            "task_id": task_id,
            "status": "SUCCESS",
            "structured_data": structured_data
        }


    except self.retry(exc=e, countdown=10):
       
        report_progress(task_id, "RETRY", 0, "Retry triggered", type)

        # Update DB → RETRY
        log = db.query(TaskLogs).filter(TaskLogs.task_id == task_id).first()
        if log:
            log.status = "RETRY"
            log.error = str(e)
            db.commit()

        raise

    except Exception as e:
    
        self.update_state(state="FAILURE")
        report_progress(task_id, "FAILURE", 0, f"Error: {str(e)}", type)

        # Save failure to Redis
        redis = get_redis_client()
        redis.setex(
            f"task_result:{task_id}",
            3600,
            json.dumps({
                "status": "FAILURE",
                "error": str(e),
                "failed_at": datetime.now(timezone.utc).isoformat()
            })
        )

        # Update DB → FAILURE
        log = db.query(TaskLogs).filter(TaskLogs.task_id == task_id).first()
        if log:
            log.status = "FAILURE"
            log.error = str(e)
            db.commit()

        raise

    finally:
        db.close()



# from app.celery import celery_app
# from app.models.job_agents import resume_extractor_agent
# from app.utils.file_handler import FileHandler
# from app.cache_db.redis_config import get_redis_client
# from app.api.dependencies.progress import report_progress
# from app.database_layer.db_config import SessionLocal
# from app.database_layer.db_model import TaskLogs

# import logging
# import json
# import base64
# from datetime import datetime, timezone

# logger = logging.getLogger("app_logger")


# @celery_app.task(bind=True, queue="extract_resume_task", max_retries=3)
# def extract_resume_task(self, task_data: dict):
#     """
#     Async resume extraction pipeline with DB + Redis logging.
#     Supports STARTED → PROGRESS → SUCCESS → RETRY → FAILURE.
#     """

#     # ---------------------------------------------------
#     # Extract task payload
#     # ---------------------------------------------------
#     task_id = task_data.get("task_id")
#     jd_text = task_data.get("jd_text", "")
#     file_content_b64 = task_data.get("file_content_b64")
#     filename = task_data.get("filename")
#     image_train = task_data.get("image_train", False)

#     JOB_TYPE = "JOB_AGENT"
#     db = SessionLocal()

#     try:
#         # =======================================================
#         # 1️⃣ STARTED
#         # =======================================================
#         self.update_state(state="STARTED")
#         report_progress(task_id, "STARTED", 10, "Task started", JOB_TYPE)

#         log = db.query(TaskLogs).filter(TaskLogs.task_id == task_id).first()
#         if log:
#             log.status = "STARTED"
#             log.error = None
#             db.commit()

#         # =======================================================
#         # 2️⃣ FILE PROCESSING
#         # =======================================================
#         report_progress(task_id, "PROGRESS", 40, "Processing file", JOB_TYPE)

#         log = db.query(TaskLogs).filter(TaskLogs.task_id == task_id).first()
#         if log:
#             log.status = "PROGRESS"
#             db.commit()

#         if file_content_b64:
#             file_bytes = base64.b64decode(file_content_b64)

#             resume_text = FileHandler.extract_text(
#                 file_bytes=file_bytes,
#                 filename=filename,
#                 perform_ocr=image_train
#             )
#         else:
#             resume_text = ""

#         # =======================================================
#         # 3️⃣ AI EXTRACTION
#         # =======================================================
#         report_progress(task_id, "PROGRESS", 80, "Running AI extraction", JOB_TYPE)

#         structured_data = resume_extractor_agent.extract_resume_data(
#             resume_data=resume_text,
#             jd_text=jd_text
#         )

#         # =======================================================
#         # 4️⃣ SAVE RESULT TO REDIS
#         # =======================================================
#         redis = get_redis_client()
#         redis.setex(
#             f"task_result:{task_id}",
#             3600,
#             json.dumps({
#                 "structured_data": structured_data,
#                 "filename": filename,
#                 "completed_at": datetime.now(timezone.utc).isoformat()
#             })
#         )

#         # =======================================================
#         # 5️⃣ SUCCESS
#         # =======================================================
#         self.update_state(state="SUCCESS")
#         report_progress(task_id, "SUCCESS", 100, "Task completed", JOB_TYPE)

#         log = db.query(TaskLogs).filter(TaskLogs.task_id == task_id).first()
#         if log:
#             log.status = "SUCCESS"
#             log.error = None
#             db.commit()

#         return {
#             "task_id": task_id,
#             "status": "SUCCESS",
#             "structured_data": structured_data
#         }

#     # =======================================================
#     # RETRY HANDLING (CORRECT CELERY PATTERN)
#     # =======================================================
#     except Exception as e:
#         try:
#             # Log retry state
#             report_progress(task_id, "RETRY", 0, "Retry triggered", JOB_TYPE)

#             log = db.query(TaskLogs).filter(TaskLogs.task_id == task_id).first()
#             if log:
#                 log.status = "RETRY"
#                 log.error = str(e)
#                 db.commit()

#             raise self.retry(exc=e, countdown=10)

#         # -------------------------------------------------------
#         # If all retries failed → mark hard failure
#         # -------------------------------------------------------
#         except self.MaxRetriesExceededError:
#             self.update_state(state="FAILURE")
#             report_progress(task_id, "FAILURE", 0, f"Task failed: {str(e)}", JOB_TYPE)

#             redis = get_redis_client()
#             redis.setex(
#                 f"task_result:{task_id}",
#                 3600,
#                 json.dumps({
#                     "status": "FAILURE",
#                     "error": str(e),
#                     "failed_at": datetime.now(timezone.utc).isoformat()
#                 })
#             )

#             log = db.query(TaskLogs).filter(TaskLogs.task_id == task_id).first()
#             if log:
#                 log.status = "FAILURE"
#                 log.error = str(e)
#                 db.commit()

#             raise

#     finally:
#         db.close()
