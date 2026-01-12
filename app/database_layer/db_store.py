# app/database_layer/db_store.py
from typing import List, Dict
import logging
from datetime import datetime, timezone

from app.database_layer.db_config import SessionLocal
from app.database_layer.db_model import (
    Pipeline,
    PipelineStage,
    PipelineStageStatus,
)

logger = logging.getLogger("app_logger")

def save_pipeline(pipeline_data: dict, user_id: int) -> int:
    """
    Save pipeline to database with audit fields.
    
    Args:
        pipeline_data: Dictionary containing pipeline data
        user_id: ID of the user creating the pipeline
        
    Returns:
        Database ID of the created pipeline
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        pipeline = Pipeline(
            pipeline_id=pipeline_data["pipeline_id"],
            name=pipeline_data.get("pipeline_name"),
            remarks=pipeline_data.get("remarks"),
            created_at=now,
            created_by=user_id,
            updated_at=now,
            updated_by=user_id,
        )
        db.add(pipeline)
        db.commit()
        db.refresh(pipeline)
        return pipeline.id

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save pipeline: {e}", exc_info=True)
        raise
    finally:
        db.close()


# --------------------------------------------------
# SAVE STAGES + STATUSES
# 🔥 Ensures ONLY last stage has end_stage = 1
# --------------------------------------------------
def save_pipeline_stages_with_statuses(
    pipeline_id: int,
    stages: List[Dict],
):
    if not stages:
        raise ValueError("Pipeline must contain at least one stage")

    db = SessionLocal()
    try:
        stages = sorted(stages, key=lambda s: s.get("stage_order", 0))
        last_stage_index = len(stages) - 1

        for index, stage in enumerate(stages):
            pipeline_stage = PipelineStage(
                name=stage.get("stage_name"),
                description=stage.get("description"),
                order=stage.get("stage_order"),
                color_code=stage.get("color_code") or None,
                end_stage=index == last_stage_index,
                pipeline_id=pipeline_id,
            )

            db.add(pipeline_stage)
            db.flush()

            statuses = stage.get("statuses", [])
            for idx, status in enumerate(statuses, start=1):
                # Ensure tag is None if empty string (enum doesn't accept empty strings)
                tag_value = status.get("tag")
                if tag_value == "":
                    tag_value = None
                
                pipeline_status = PipelineStageStatus(
                    pipeline_stage_id=pipeline_stage.id,
                    option=status.get("status_name"),
                    color_code=status.get("color_code") or None,
                    order=idx,
                    tag=tag_value,
                )
                db.add(pipeline_status)

        db.commit()

    except Exception as e:
        db.rollback()
        logger.error(f"Failed saving stages/statuses: {e}", exc_info=True)
        raise
    finally:
        db.close()
