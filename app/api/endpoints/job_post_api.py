"""
Job Post API Endpoints

This module contains API endpoints for creating and managing job posts.

Author: [Supriyo Chowdhury]
Version: 1.0
Last Modified: [2024-12-19]
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional, List
import uuid
from datetime import datetime, timezone

from app.database_layer.db_config import get_db
from app.database_layer.db_model import JobPosts, JobOpenings, Company
from app.utils.dimension_mapping import get_dimension
from app.utils.file_storage import (
    save_uploaded_file, 
    validate_image_file, 
    get_file_url
)
from app.celery.tasks import generate_job_post_task
from app.cache_db.redis_config import get_redis_client
import logging
import json

logger = logging.getLogger("app_logger")

router = APIRouter(prefix="/job-post", tags=["job-post"])


@router.post("/{job_id}")
async def create_job_post(
    job_id: int,
    dimension: str = Form(...),
    instructions: str = Form(...),
    language: Optional[str] = Form(None),
    logo_url: Optional[str] = Form(None),
    logo_file: Optional[UploadFile] = File(None),
    type: Optional[str] = Form(None),
    generate_image: bool = Form(False),
    images: Optional[List[UploadFile]] = File(None),
    cta: bool = Form(False),
    salary_info: bool = Form(True),  # Whether to include salary info
    contact_details: Optional[str] = Form(None),  # Contact name, email, phone
    created_by: int = Form(...),  # In production, get from auth token
    db: Session = Depends(get_db)
):
    """
    Create a new job post.
    
    Args:
        job_id: Job opening ID
        dimension: Dimension string (e.g., "1", "instagram")
        instructions: Instructions for the post
        language: Language for the post (optional)
        logo_url: Logo URL (optional, if logo_file not provided)
        logo_file: Logo file upload (optional, if logo_url not provided)
        type: Post type (corporate, creative, minimal, vibrant, tech, professional)
        generate_image: Whether to generate image using AI
        images: List of image files (max 2, if generate_image is False)
        cta: Call to action required
        created_by: User ID creating the post
        db: Database session
    
    Returns:
        dict: Task ID, job_post_id, job_id, and status
    """
    try:
        # Validate job exists
        job = db.query(JobOpenings).filter(JobOpenings.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job opening not found")
        
        # Get dimension mapping
        dimension_info = get_dimension(dimension)
        
        # Handle logo
        final_logo_url = None
        if logo_file:
            # Validate logo file
            is_valid, error_msg = validate_image_file(logo_file, max_size_mb=5, max_width=2000, max_height=2000)
            if not is_valid:
                raise HTTPException(status_code=400, detail=f"Logo validation failed: {error_msg}")
            
            # Save logo file
            logo_file_id, _ = save_uploaded_file(logo_file, job_id, "logo")
            final_logo_url = get_file_url(logo_file_id)
        elif logo_url:
            final_logo_url = logo_url
        
        # Handle images
        image_urls = []
        if not generate_image:
            if images:
                if len(images) > 2:
                    raise HTTPException(status_code=400, detail="Maximum 2 images allowed")
                
                for img in images:
                    # Validate image
                    is_valid, error_msg = validate_image_file(img, max_size_mb=10, max_width=5000, max_height=5000)
                    if not is_valid:
                        raise HTTPException(status_code=400, detail=f"Image validation failed: {error_msg}")
                    
                    # Save image
                    img_file_id, _ = save_uploaded_file(img, job_id, "image")
                    image_urls.append(get_file_url(img_file_id))
        
        # Get latest version for this job_id
        latest_post = db.query(JobPosts).filter(
            JobPosts.job_id == job_id,
            JobPosts.deleted_at.is_(None)
        ).order_by(JobPosts.ver.desc()).first()
        
        new_version = 1
        if latest_post and latest_post.ver:
            new_version = latest_post.ver + 1
        
        # Generate job_post_id
        job_post_id = f"JP_{job_id}_{new_version}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        
        # Generate task_id
        task_id = str(uuid.uuid4())
        
        # Create job post record
        job_post = JobPosts(
            job_id=job_id,
            job_post_id=job_post_id,
            instructions=instructions,
            ver=new_version,
            dimension=dimension_info["name"],
            logo_url=final_logo_url,
            type=type or "professional",
            language=language or "English",
            cta=1 if cta else 0,
            task_id=task_id,
            status="pending",
            created_by=created_by,
            created_at=datetime.now(timezone.utc)
        )
        
        db.add(job_post)
        db.commit()
        db.refresh(job_post)
        
        # Set initial status in Redis for WebSocket updates
        try:
            redis_client = get_redis_client()
            initial_status = {
                "task_id": task_id,
                "status": "pending",
                "progress": 0,
                "message": "Task queued, waiting to start",
                "step": "queued",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            redis_client.setex(
                f"task_status:{task_id}",
                3600,  # 1 hour expiry
                json.dumps(initial_status)
            )
            # Publish initial status to pub/sub
            redis_client.publish(
                f"task_status_updates:{task_id}",
                json.dumps(initial_status)
            )
            logger.info(f"Initial status set in Redis for task: {task_id}")
        except Exception as e:
            logger.error(f"Error setting initial Redis status: {e}", exc_info=True)
            # Continue even if Redis update fails
        
        # Prepare data for Celery task
        task_data = {
            "job_post_db_id": job_post.id,  # Database ID
            "job_post_id": job_post_id,  # String identifier
            "job_id": job_id,
            "dimension": dimension_info,
            "instructions": instructions,
            "language": language or "English",
            "logo_url": final_logo_url,
            "type": type or "professional",
            "generate_image": generate_image,
            "image_urls": image_urls,
            "cta": cta,
            "salary_info": salary_info,
            "contact_details": contact_details,
            "task_id": task_id
        }
        
        # Start Celery task
        celery_task = generate_job_post_task.delay(task_data)
        
        logger.info(f"Job post creation task started: {task_id}")
        
        return {
            "task_id": task_id,
            "job_post_id": job_post_id,
            "job_id": job_id,
            "status": "pending",
            "message": "Job post creation started"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating job post: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating job post: {str(e)}")

