import json
import random
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any

from app.celery.celery_config import celery_app
from app.models.pipeline_model import pipeline_agent
from app.utils import file_handler
from app.cache_db import get_redis_client
from app.api.dependencies.progress import report_progress
from app.database_layer.db_store import (
    save_pipeline,
    save_pipeline_stages_with_statuses,
)
from app.database_layer.db_model import PipelineStageTag

logger = logging.getLogger("app_logger")
redis_client = get_redis_client()

# Default blue hex color code
DEFAULT_BLUE_COLOR = "#0000FF"

# Valid tag enum values
VALID_TAG_VALUES = {tag.value for tag in PipelineStageTag}


def normalize_tag(tag_value: Any) -> str | None:
    """
    Normalize tag value to be either None or a valid enum value.
    
    Args:
        tag_value: The tag value from the input data
        
    Returns:
        Valid tag enum value string or None
    """
    if tag_value is None:
        return None
    
    tag_str = (tag_value or "").strip()
    
    if not tag_str:
        return None
    
    # Check if the tag matches any valid enum value
    if tag_str in VALID_TAG_VALUES:
        return tag_str
    
    # If tag doesn't match any valid enum value, return None
    logger.warning(f"Invalid tag value '{tag_str}', setting to None. Valid values are: {VALID_TAG_VALUES}")
    return None


def generate_pipeline_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    random_number = random.randint(1000, 9999)
    return f"PIPE_{timestamp}_{random_number}"


def validate_and_normalize_pipeline_data(pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and normalize pipeline data according to requirements:
    1. pipeline_name must not be empty
    2. stage_names (stage_name) must not be empty
    3. stage_colors (color_code) must not be empty - default to blue if empty
    4. If statuses are present, then status_name, status_color (color_code), and order cannot be empty
    5. If any color is empty, add blue hex code by default
    6. If any order is empty, dynamically add order
    
    Args:
        pipeline_data: Dictionary containing pipeline data
        
    Returns:
        Validated and normalized pipeline data
        
    Raises:
        ValueError: If validation fails
    """
    # Validate pipeline_name
    pipeline_name = (pipeline_data.get("pipeline_name") or "").strip()
    if not pipeline_name:
        raise ValueError("pipeline_name cannot be empty")
    
    # Validate interview_stages
    interview_stages = pipeline_data.get("interview_stages", [])
    if not interview_stages:
        raise ValueError("interview_stages cannot be empty")
    
    normalized_stages = []
    
    for stage_index, stage in enumerate(interview_stages, start=1):
        # Validate stage_name
        stage_name = (stage.get("stage_name") or "").strip()
        if not stage_name:
            raise ValueError(f"stage_name cannot be empty for stage at index {stage_index}")
        
        # Validate and set stage color_code (default to blue if empty)
        stage_color = (stage.get("color_code") or "").strip()
        if not stage_color:
            stage_color = DEFAULT_BLUE_COLOR
            logger.warning(f"Empty color_code for stage '{stage_name}', defaulting to {DEFAULT_BLUE_COLOR}")
        
        # Set stage_order if empty
        stage_order = stage.get("stage_order")
        if stage_order is None or stage_order == "":
            stage_order = stage_index
            logger.warning(f"Empty stage_order for stage '{stage_name}', setting to {stage_order}")
        
        # Normalize stage
        normalized_stage = {
            "stage_order": stage_order,
            "stage_name": stage_name,
            "description": (stage.get("description") or "").strip(),
            "color_code": stage_color,
            "statuses": []
        }
        
        # Validate statuses if present
        statuses = stage.get("statuses", [])
        if statuses:
            normalized_statuses = []
            
            for status_index, status in enumerate(statuses, start=1):
                # Validate status_name
                status_name = (status.get("status_name") or "").strip()
                if not status_name:
                    raise ValueError(
                        f"status_name cannot be empty for status at index {status_index} "
                        f"in stage '{stage_name}'"
                    )
                
                # Validate and set status color_code (default to blue if empty)
                status_color = (status.get("color_code") or "").strip()
                if not status_color:
                    status_color = DEFAULT_BLUE_COLOR
                    logger.warning(
                        f"Empty color_code for status '{status_name}' in stage '{stage_name}', "
                        f"defaulting to {DEFAULT_BLUE_COLOR}"
                    )
                
                # Set status order if empty
                status_order = status.get("order")
                if status_order is None or status_order == "":
                    status_order = status_index
                    logger.warning(
                        f"Empty order for status '{status_name}' in stage '{stage_name}', "
                        f"setting to {status_order}"
                    )
                
                # Normalize tag (must be None or a valid enum value, not empty string)
                status_tag = normalize_tag(status.get("tag"))
                
                # Normalize status
                normalized_status = {
                    "status_name": status_name,
                    "description": (status.get("description") or "").strip(),
                    "color_code": status_color,
                    "tag": status_tag,
                    "order": status_order
                }
                normalized_statuses.append(normalized_status)
            
            normalized_stage["statuses"] = normalized_statuses
        
        normalized_stages.append(normalized_stage)
    
    # Return normalized pipeline data
    normalized_data = {
        "pipeline_name": pipeline_name,
        "remarks": (pipeline_data.get("remarks") or "").strip(),
        "interview_stages": normalized_stages
    }
    
    return normalized_data


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

        report_progress(task_id, "PROGRESS", 70, "Validating pipeline data")
        
        # Validate and normalize pipeline data
        pipeline_data = validate_and_normalize_pipeline_data(pipeline_data)

        pipeline_data["pipeline_id"] = generate_pipeline_id()

        report_progress(task_id, "PROGRESS", 80, "Saving pipeline to database")
       
        pipeline_db_id = save_pipeline(pipeline_data)

        save_pipeline_stages_with_statuses(
            pipeline_id=pipeline_db_id,
            stages=pipeline_data.get("interview_stages", []),
        )


        report_progress(task_id, "SUCCESS", 100, "Pipeline created successfully", pipeline_id=pipeline_db_id)
        self.update_state(state="SUCCESS")

        return {
            "task_id": task_id,
            "status": "SUCCESS",
            "pipeline_db_id": pipeline_db_id,
        }

    except Exception as e:
        logger.error(f"Pipeline agent failed: {e}", exc_info=True)
        report_progress(task_id, "FAILED", 0, str(e))
        raise
