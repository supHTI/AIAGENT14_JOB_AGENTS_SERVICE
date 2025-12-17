"""
Call Processing API Endpoints

This module handles audio call upload, processing, and result retrieval.
Supports MP3, WAV, M4A formats with automatic transcription and analysis.

Author: [Supriyo Chowdhury]
Version: 1.0
Last Modified: [2024-12-15]
"""

from fastapi import APIRouter, File, UploadFile, Form, HTTPException, status
from fastapi.responses import JSONResponse
from typing import Optional
from pydantic import BaseModel, Field
import logging
import uuid
import json
from datetime import datetime

from app.cache_db.redis_config import get_redis_client

logger = logging.getLogger("app_logger")
router = APIRouter(prefix="/api/v1/call", tags=["Call Processing"])
redis_client = get_redis_client()

# Supported audio formats
SUPPORTED_FORMATS = {'.wav', '.mp3', '.m4a'}


class CallProcessRequest(BaseModel):
    """Response model for call processing request"""
    request_id: str = Field(..., description="Unique identifier for the processing request")
    status: str = Field(..., description="Current status of the request")


class CallProcessResult(BaseModel):
    """Response model for call processing result"""
    request_id: str
    status: str
    candidate_id: Optional[int] = None
    job_id: Optional[int] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


def validate_audio_file(filename: str) -> bool:
    """Validate if the uploaded file is a supported audio format"""
    if not filename:
        return False
    return any(filename.lower().endswith(ext) for ext in SUPPORTED_FORMATS)


@router.post("/process", response_model=CallProcessRequest, status_code=status.HTTP_202_ACCEPTED)
async def process_call(
    audio_file: UploadFile = File(..., description="Audio file (.wav, .mp3, .m4a)"),
    candidate_id: int = Form(..., description="Candidate ID"),
    job_id: int = Form(..., description="Job ID"),
    language: Optional[str] = Form("en-IN", description="Language code (default: en-IN)"),
    diarization: Optional[bool] = Form(True, description="Enable speaker diarization")
):
    """
    Upload and process call audio file asynchronously.
    
    **Parameters:**
    - **audio_file**: Audio file in WAV, MP3, or M4A format
    - **candidate_id**: ID of the candidate being interviewed
    - **job_id**: ID of the job position
    - **language**: Language code for transcription (default: en-IN)
    - **diarization**: Enable/disable speaker diarization (default: True)
    
    **Returns:**
    - **request_id**: Unique identifier to track the processing request
    - **status**: Current status ("processing")
    
    **Processing Flow:**
    1. Audio format validation
    2. Audio preprocessing (normalization, noise reduction)
    3. Speech-to-Text transcription with Google AI
    4. Transcript normalization and cleaning
    5. Chunking for LLM analysis
    """
    from app.celery.tasks.call_processing_tasks import process_call_audio_task
    
    try:
        # Validate file format
        if not validate_audio_file(audio_file.filename):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file format. Supported formats: {', '.join(SUPPORTED_FORMATS)}"
            )
        
        # Validate candidate_id and job_id
        if candidate_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="candidate_id must be a positive integer"
            )
        
        if job_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="job_id must be a positive integer"
            )
        
        # Generate unique request ID
        request_id = str(uuid.uuid4())[:8]
        
        # Read audio file content
        audio_content = await audio_file.read()
        
        # Store initial request metadata in Redis
        request_data = {
            "request_id": request_id,
            "status": "processing",
            "candidate_id": candidate_id,
            "job_id": job_id,
            "language": language,
            "diarization": diarization,
            "filename": audio_file.filename,
            "created_at": datetime.utcnow().isoformat()
        }
        
        redis_key = f"call_process:{request_id}"
        redis_client.setex(
            redis_key,
            3600 * 24,  # 24 hours TTL
            json.dumps(request_data)
        )
        
        # Queue the audio processing task
        task = process_call_audio_task.delay(
            request_id=request_id,
            audio_content=audio_content.hex(),  # Convert bytes to hex string
            filename=audio_file.filename,
            candidate_id=candidate_id,
            job_id=job_id,
            language=language,
            diarization=diarization
        )
        
        logger.info(
            f"Call processing queued - Request ID: {request_id}, "
            f"Candidate: {candidate_id}, Job: {job_id}, Task: {task.id}"
        )
        
        return CallProcessRequest(
            request_id=request_id,
            status="processing"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in process_call endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process audio file: {str(e)}"
        )


@router.get("/result/{request_id}", response_model=CallProcessResult)
async def get_call_result(request_id: str):
    """
    Fetch the processing result for a given request ID.
    
    **Parameters:**
    - **request_id**: Unique identifier returned from the /process endpoint
    
    **Returns:**
    - **request_id**: The request identifier
    - **status**: Current status (processing, completed, failed)
    - **candidate_id**: Candidate ID
    - **job_id**: Job ID
    - **result**: Processing result (if completed)
    - **error**: Error message (if failed)
    - **created_at**: Timestamp when request was created
    - **completed_at**: Timestamp when processing completed (if finished)
    
    **Status Values:**
    - **processing**: Audio is still being processed
    - **completed**: Processing finished successfully
    - **failed**: Processing encountered an error
    """
    try:
        redis_key = f"call_process:{request_id}"
        
        # Fetch from Redis
        result_data = redis_client.get(redis_key)
        
        if not result_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No result found for request_id: {request_id}"
            )
        
        # Parse the result
        result = json.loads(result_data)
        
        return CallProcessResult(**result)
        
    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse result for {request_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to parse result data"
        )
    except Exception as e:
        logger.error(f"Error fetching result for {request_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch result: {str(e)}"
        )


@router.delete("/result/{request_id}")
async def delete_call_result(request_id: str):
    """
    Delete the processing result for a given request ID.
    
    **Parameters:**
    - **request_id**: Unique identifier to delete
    
    **Returns:**
    - Success message
    """
    try:
        redis_key = f"call_process:{request_id}"
        
        # Check if exists
        if not redis_client.exists(redis_key):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No result found for request_id: {request_id}"
            )
        
        # Delete from Redis
        redis_client.delete(redis_key)
        
        logger.info(f"Deleted call processing result: {request_id}")
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": f"Successfully deleted result for request_id: {request_id}"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting result for {request_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete result: {str(e)}"
        )
