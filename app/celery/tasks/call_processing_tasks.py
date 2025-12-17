"""
Call Processing Celery Tasks

This module contains background tasks for processing audio calls:
- Audio preprocessing
- Speech-to-text transcription
- Transcript normalization
- Chunking for analysis

Author: [Supriyo Chowdhury]
Version: 1.0
Last Modified: [2024-12-15]
"""

from celery import Task
import logging
import json
from datetime import datetime
from typing import Dict, Any

from app.celery.celery_config import celery_app
from app.cache_db.redis_config import get_redis_client

logger = logging.getLogger("app_logger")
redis_client = get_redis_client()


class CallbackTask(Task):
    """Base task with callback for status updates"""

    def on_success(self, retval, task_id, args, kwargs):
        """Called on task success"""
        logger.info(f"Task {task_id} completed successfully")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called on task failure"""
        logger.error(f"Task {task_id} failed: {str(exc)}")


@celery_app.task(
    bind=True,
    base=CallbackTask,
    name="process_call_audio_task",
    max_retries=2,
    soft_time_limit=600,  # 10 minutes
    time_limit=660,  # 11 minutes
)
def process_call_audio_task(
    self,
    request_id: str,
    audio_content: str,
    filename: str,
    candidate_id: int,
    job_id: int,
    language: str = "en-IN",
    diarization: bool = True
) -> Dict[str, Any]:
    """
    Background task to process audio call
    
    Args:
        request_id: Unique request identifier
        audio_content: Audio file content as hex string
        filename: Original filename
        candidate_id: Candidate ID
        job_id: Job ID
        language: Language code for transcription
        diarization: Enable speaker diarization
    
    Returns:
        Processing result dictionary
    """
    from app.utils.audio_preprocessing import preprocess_audio
    from app.utils.google_stt import transcribe_audio
    from app.utils.transcript_normalizer import normalize_transcript
    from app.utils.transcript_chunker import chunk_transcript
    
    try:
        logger.info(
            f"Processing call audio - Request: {request_id}, "
            f"Candidate: {candidate_id}, Job: {job_id}"
        )
        
        # Update status to processing
        _update_status(request_id, "processing", {
            "stage": "preprocessing",
            "progress": 10
        })
        
        # Step 1: Audio Preprocessing
        logger.info(f"[{request_id}] Step 1: Preprocessing audio...")
        audio_bytes = bytes.fromhex(audio_content)
        
        preprocessed_audio = preprocess_audio(
            audio_content=audio_bytes,
            filename=filename,
            apply_noise_reduction=True,
            trim_silence_enabled=True
        )
        
        logger.info(f"[{request_id}] Audio preprocessing completed")
        
        _update_status(request_id, "processing", {
            "stage": "transcription",
            "progress": 30
        })
        
        # Step 2: Speech-to-Text Transcription
        logger.info(f"[{request_id}] Step 2: Transcribing audio...")
        
        raw_segments = transcribe_audio(audio_content=preprocessed_audio)
        
        logger.info(f"[{request_id}] Transcription completed: {len(raw_segments)} segments")
        
        _update_status(request_id, "processing", {
            "stage": "normalization",
            "progress": 60
        })
        
        # Step 3: Transcript Normalization
        logger.info(f"[{request_id}] Step 3: Normalizing transcript...")
        
        normalization_result = normalize_transcript(raw_segments)
        normalized_segments = normalization_result['segments']
        transcript_stats = normalization_result['statistics']
        
        logger.info(f"[{request_id}] Normalization completed: {len(normalized_segments)} segments")
        
        _update_status(request_id, "processing", {
            "stage": "chunking",
            "progress": 80
        })
        
        # Step 4: Chunking for LLM Analysis
        logger.info(f"[{request_id}] Step 4: Chunking transcript...")
        
        chunking_result = chunk_transcript(
            segments=normalized_segments,
            strategy="tokens",
            max_tokens=4000,
            overlap_tokens=200
        )
        
        chunks = chunking_result['chunks']
        chunk_summary = chunking_result['summary']
        
        logger.info(f"[{request_id}] Chunking completed: {len(chunks)} chunks")
        
        # Prepare final result
        result = {
            "request_id": request_id,
            "status": "completed",
            "candidate_id": candidate_id,
            "job_id": job_id,
            "created_at": _get_creation_time(request_id),
            "completed_at": datetime.utcnow().isoformat(),
            "result": {
                "transcript": {
                    "segments": normalized_segments,
                    "statistics": transcript_stats,
                    "raw_text": " ".join(seg['text'] for seg in normalized_segments)
                },
                "chunks": chunks,
                "chunk_summary": chunk_summary,
                "audio_info": {
                    "filename": filename,
                    "language": language,
                    "diarization_enabled": diarization
                }
            }
        }
        
        # Store result in Redis
        redis_key = f"call_process:{request_id}"
        redis_client.setex(
            redis_key,
            3600 * 24 * 7,  # 7 days TTL
            json.dumps(result)
        )
        
        logger.info(f"[{request_id}] Call processing completed successfully")
        
        return result
        
    except Exception as e:
        logger.error(f"[{request_id}] Call processing failed: {str(e)}", exc_info=True)
        
        # Update status to failed
        error_result = {
            "request_id": request_id,
            "status": "failed",
            "candidate_id": candidate_id,
            "job_id": job_id,
            "created_at": _get_creation_time(request_id),
            "completed_at": datetime.utcnow().isoformat(),
            "error": str(e)
        }
        
        redis_key = f"call_process:{request_id}"
        redis_client.setex(
            redis_key,
            3600 * 24,  # 1 day TTL for failed requests
            json.dumps(error_result)
        )
        
        raise


def _update_status(request_id: str, status: str, extra_data: Dict = None):
    """
    Update processing status in Redis
    
    Args:
        request_id: Request identifier
        status: Current status
        extra_data: Additional data to include
    """
    try:
        redis_key = f"call_process:{request_id}"
        
        # Get existing data
        existing_data = redis_client.get(redis_key)
        if existing_data:
            data = json.loads(existing_data)
            data["status"] = status
            if extra_data:
                data.update(extra_data)
            
            redis_client.setex(
                redis_key,
                3600 * 24,  # 24 hours TTL
                json.dumps(data)
            )
    except Exception as e:
        logger.warning(f"Failed to update status for {request_id}: {str(e)}")


def _get_creation_time(request_id: str) -> str:
    """
    Get creation time from Redis data
    
    Args:
        request_id: Request identifier
    
    Returns:
        ISO format timestamp
    """
    try:
        redis_key = f"call_process:{request_id}"
        existing_data = redis_client.get(redis_key)
        
        if existing_data:
            data = json.loads(existing_data)
            return data.get("created_at", datetime.utcnow().isoformat())
    except Exception:
        pass
    
    return datetime.utcnow().isoformat()


@celery_app.task(
    bind=True,
    base=CallbackTask,
    name="analyze_call_transcript_task",
    max_retries=2,
)
def analyze_call_transcript_task(
    self,
    request_id: str,
    analysis_type: str = "comprehensive"
) -> Dict[str, Any]:
    """
    Analyze processed call transcript using LLM
    
    Args:
        request_id: Request identifier
        analysis_type: Type of analysis to perform
            - "comprehensive": Full analysis
            - "skills": Focus on technical skills
            - "communication": Focus on communication skills
            - "experience": Focus on work experience
    
    Returns:
        Analysis results
    """
    try:
        logger.info(f"Analyzing call transcript - Request: {request_id}, Type: {analysis_type}")
        
        # Get processed transcript from Redis
        redis_key = f"call_process:{request_id}"
        result_data = redis_client.get(redis_key)
        
        if not result_data:
            raise ValueError(f"No processed data found for request_id: {request_id}")
        
        data = json.loads(result_data)
        
        if data.get("status") != "completed":
            raise ValueError(f"Request {request_id} is not completed yet")
        
        # Get transcript chunks
        chunks = data["result"]["chunks"]
        
        # TODO: Implement LLM-based analysis
        # This is a placeholder for LLM integration
        # You can use your existing LLM service here
        
        analysis_result = {
            "request_id": request_id,
            "analysis_type": analysis_type,
            "analyzed_at": datetime.utcnow().isoformat(),
            "insights": {
                "summary": "Analysis placeholder - integrate with your LLM service",
                "key_points": [],
                "skills_mentioned": [],
                "recommendations": []
            }
        }
        
        logger.info(f"[{request_id}] Analysis completed")
        
        return analysis_result
        
    except Exception as e:
        logger.error(f"[{request_id}] Analysis failed: {str(e)}", exc_info=True)
        raise
