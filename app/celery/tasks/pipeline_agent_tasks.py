import json
import random
import logging
import requests
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
from app.core import settings
from app.database_layer.db_config import SessionLocal
from app.database_layer.db_model import User

logger = logging.getLogger("app_logger")
redis_client = get_redis_client()

# Default blue hex color code
DEFAULT_BLUE_COLOR = "#0000FF"

# Valid tag enum values
VALID_TAG_VALUES = {tag.value for tag in PipelineStageTag}

# Allowed roles for pipeline creation
ALLOWED_PIPELINE_ROLES = {"super_admin", "admin"}


def validate_jwt_token_and_get_user(token: str) -> Dict[str, Any]:
    """
    Validate JWT token via AUTH_SERVICE_URL and return user information.
    Checks if user has admin or super_admin role.
    
    Args:
        token: JWT token string
        
    Returns:
        Dictionary with user_id, role_id, and role_name
        
    Raises:
        ValueError: If token is invalid or user doesn't have required permissions
    """
    try:
        response = requests.post(
            f"{settings.AUTH_SERVICE_URL}",
            params={"token": token},
            headers={"accept": "application/json"}
        )
        
        if response.status_code != 200:
            raise ValueError("Invalid or expired token")
        
        token_info = response.json()
        user_id = token_info.get("user_id")
        role_id = token_info.get("role_id")
        role_name = token_info.get("role_name")
        
        if not user_id or not role_id or not role_name:
            raise ValueError("Token missing required user information")
        
        # Check if user has admin or super_admin role
        role_name_lower = role_name.lower()
        if role_name_lower not in ALLOWED_PIPELINE_ROLES:
            raise ValueError(
                f"Access denied. Only admin and super_admin roles can create pipelines. "
                f"Your role: {role_name}"
            )
        
        # Verify user exists in database
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise ValueError("User not found in database")
            
            # Double-check role from database
            if user.role and user.role.name:
                db_role_name = user.role.name.lower()
                if db_role_name not in ALLOWED_PIPELINE_ROLES:
                    raise ValueError(
                        f"Access denied. Only admin and super_admin roles can create pipelines. "
                        f"Your role: {user.role.name}"
                    )
        finally:
            db.close()
        
        return {
            "user_id": user_id,
            "role_id": role_id,
            "role_name": role_name
        }
        
    except requests.RequestException as e:
        logger.error(f"Authentication service unavailable: {e}")
        raise ValueError("Authentication service unavailable")
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        raise


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
    token = task_data.get("token", "")

    try:
        report_progress(task_id, "STARTED", 10, "Pipeline task started")
        
        # Validate JWT token and get user information
        if not token:
            raise ValueError("JWT token is required")
        
        report_progress(task_id, "PROGRESS", 15, "Validating user permissions")
        user_info = validate_jwt_token_and_get_user(token)
        user_id = user_info["user_id"]

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
       
        pipeline_db_id = save_pipeline(pipeline_data, user_id=user_id)

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
