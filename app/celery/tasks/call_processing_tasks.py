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
from typing import Dict, Any, List

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
    call_id: str,
    audio_content: str,
    filename: str,
    candidate_id: str,
    candidate_name: str,
    job_id: int,
    recruiter_name: str,
    call_date: str,
    recording_consent_confirmed: bool = False,
    call_duration_seconds: int = None,
    diarization: bool = True
) -> Dict[str, Any]:
    """
    Background task to process audio call
    
    Args:
        request_id: Unique request identifier
        call_id: Unique call identifier
        audio_content: Audio file content as hex string
        filename: Original filename
        candidate_id: Candidate ID (string)
        candidate_name: Candidate full name
        job_id: Job ID (int)
        recruiter_name: HR/Recruiter name
        call_date: Call date in ISO format
        recording_consent_confirmed: Recording consent status
        call_duration_seconds: Call duration (will be calculated)
        diarization: Enable speaker diarization
    
    Returns:
        Processing result dictionary
    """
    try:
        # Import utilities with proper error handling
        try:
            from app.utils.audio_preprocessing import preprocess_audio
            from app.utils.google_stt import transcribe_audio
            from app.utils.transcript_normalizer import normalize_transcript
            from app.utils.transcript_chunker import chunk_transcript
        except ImportError as e:
            logger.error(f"[{request_id}] Failed to import required utility modules: {str(e)}", exc_info=True)
            error_result = {
                "request_id": request_id,
                "call_id": call_id,
                "status": "failed",
                "candidate_id": candidate_id,
                "candidate_name": candidate_name,
                "job_id": job_id,
                "recruiter_name": recruiter_name,
                "created_at": _get_creation_time(request_id),
                "completed_at": datetime.utcnow().isoformat(),
                "error": f"Failed to import required modules: {str(e)}"
            }
            redis_key = f"call_process:{request_id}"
            redis_client.setex(redis_key, 3600 * 24, json.dumps(error_result))
            raise
        
        logger.info(
            f"Processing call audio - Request: {request_id}, Call: {call_id}, "
            f"Candidate: {candidate_id}, Job: {job_id}"
        )
        
        # Validate audio content
        try:
            audio_bytes = bytes.fromhex(audio_content)
            if len(audio_bytes) == 0:
                raise ValueError("Audio content is empty")
            if len(audio_bytes) > 500 * 1024 * 1024:  # 500MB max
                raise ValueError(f"Audio file too large: {len(audio_bytes)} bytes")
        except ValueError as e:
            raise ValueError(f"Invalid audio content: {str(e)}")
        
        # Calculate call duration from audio file
        # Assuming 16kHz mono WAV format: duration = bytes / (16000 * 2)
        # WAV header is typically 44 bytes, audio data starts after
        audio_data_size = len(audio_bytes) - 44 if len(audio_bytes) > 44 else len(audio_bytes)
        call_duration_seconds = int(audio_data_size / (16000 * 2))
        
        logger.info(f"[{request_id}] Calculated call duration: {call_duration_seconds} seconds")
        
        # Update status to processing
        _update_status(request_id, "processing", {
            "stage": "preprocessing",
            "progress": 10
        })
        
        # Step 1: Audio Preprocessing
        logger.info(f"[{request_id}] Step 1: Preprocessing audio...")
        
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
        
        # Fail fast: try to initialize STT client to detect missing/invalid API keys early
        try:
            from app.utils.google_stt import GoogleSTT
            _stt = GoogleSTT()  # will raise a clear error if keys are missing/invalid
            logger.info(f"[{request_id}] STT client initialized successfully")
        except Exception as stt_init_err:
            logger.error(f"[{request_id}] STT initialization failed: {str(stt_init_err)}")
            # Update Redis status with failure info
            _update_status(request_id, "failed", {"stage": "transcription", "error": str(stt_init_err)})
            raise
        
        transcribe_result = transcribe_audio(audio_content=preprocessed_audio)
        
        if isinstance(transcribe_result, dict):
            raw_segments = transcribe_result.get('segments', [])
            chunk_summaries = transcribe_result.get('chunk_summaries', [])
            final_summary = transcribe_result.get('final_summary', {})
        else:
            # backward-compatible: list of segments
            raw_segments = transcribe_result
            chunk_summaries = []
            final_summary = {}
        
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
        
        # Merge similar/adjacent segments to reduce redundancy and tokens
        normalized_segments = _merge_similar_segments(normalized_segments)
        logger.info(f"[{request_id}] After merge: {len(normalized_segments)} segments")
        
        # Extract analysis data from segments (sentiment, communication metrics)
        segment_analysis = _extract_segment_analysis(normalized_segments)
        
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
        
        # Prepare final result with comprehensive metadata
        result = {
            "request_id": request_id,
            "status": "completed",
            "call_metadata": {
                "call_id": call_id,
                "candidate_name": candidate_name,
                "job_id": job_id,
                "recruiter_name": recruiter_name,
                "call_date": call_date,
                "call_duration_seconds": call_duration_seconds,
                "language": "en-IN",
                "recording_consent_confirmed": recording_consent_confirmed,
                "audio_quality_score": segment_analysis.get("avg_clarity_score", None)  # Use clarity as proxy for audio quality
            },
            "candidate_identity": {
                "full_name": candidate_name,
                "candidate_identity_confirmed": None  # To be filled by LLM analysis
            },
            "communication_analysis": {
                "clarity_score": segment_analysis.get("avg_clarity_score"),
                "confidence_score": segment_analysis.get("avg_confidence_score"),
                "fluency_score": segment_analysis.get("avg_fluency_score"),
                "responsiveness_score": segment_analysis.get("avg_responsiveness_score", segment_analysis.get("avg_fluency_score")),
                "professionalism_score": segment_analysis.get("avg_professionalism_score")
            },
            "sentiment_analysis": {
                "overall_sentiment": segment_analysis.get("dominant_sentiment"),
                "interest_level": segment_analysis.get("interest_level"),
                "enthusiasm_score": segment_analysis.get("enthusiasm_score"),
                "hesitation_detected": segment_analysis.get("hesitation_detected", False),
                "stress_indicators": segment_analysis.get("stress_indicators", False),
                "sentiment_timeline": segment_analysis.get("sentiment_timeline", [])
            },
            "questions_asked_by_candidate": segment_analysis.get("candidate_questions", []),
            "recruiter_notes_ai": {
                "call_summary": final_summary if final_summary else chunk_summary,
                "key_highlights": segment_analysis.get("communication_strengths", []),
                "concerns": segment_analysis.get("communication_concerns", []),
                "recommended_next_steps": final_summary.get('recommended_next_steps', []) if final_summary else []
            },
            "recruiter_analysis": {
                "clarity": segment_analysis.get("avg_clarity_score"),
                "professionalism": segment_analysis.get("avg_professionalism_score"),
                "responsiveness": segment_analysis.get("avg_responsiveness_score", segment_analysis.get("avg_fluency_score")),
                "structure": None  # To be filled by LLM analysis
            },
            "transcript": {
                "segments": normalized_segments,
                "statistics": transcript_stats,
                "raw_text": " ".join(seg.get('text', '') for seg in normalized_segments)
            },
            "chunks": chunks,
            "chunk_summary": chunk_summary,
            "final_summary": final_summary,
            "created_at": _get_creation_time(request_id),
            "completed_at": datetime.utcnow().isoformat()
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
        
        # Update status to failed with metadata
        error_result = {
            "request_id": request_id,
            "call_id": call_id,
            "status": "failed",
            "candidate_id": candidate_id,
            "candidate_name": candidate_name,
            "job_id": job_id,
            "recruiter_name": recruiter_name,
            "created_at": _get_creation_time(request_id),
            "completed_at": datetime.utcnow().isoformat(),
            "error": str(e),
            "retry_count": self.request.retries
        }
        
        redis_key = f"call_process:{request_id}"
        redis_client.setex(
            redis_key,
            3600 * 24,  # 1 day TTL for failed requests
            json.dumps(error_result)
        )
        
        # Retry logic - only retry on certain exceptions
        if isinstance(e, (IOError, ConnectionError, TimeoutError)):
            logger.warning(f"[{request_id}] Retrying task due to {type(e).__name__}")
            raise self.retry(exc=e, countdown=60)  # Retry after 60 seconds
        
        raise


def _extract_segment_analysis(segments: List[Dict]) -> Dict[str, Any]:
    """
    Extract and aggregate analysis data from segments
    Calculate average scores for sentiment and communication metrics
    
    Args:
        segments: List of transcript segments with analysis scores
    
    Returns:
        Dictionary with aggregated analysis data
    """
    if not segments:
        return {
            "avg_clarity_score": 0,
            "avg_confidence_score": 0,
            "avg_fluency_score": 0,
            "avg_responsiveness_score": 0,
            "avg_professionalism_score": 0,
            "dominant_sentiment": "neutral",
            "interest_level": 0,
            "enthusiasm_score": 0,
            "hesitation_detected": False,
            "stress_indicators": False,
            "sentiment_timeline": [],
            "candidate_questions": [],
            "communication_strengths": [],
            "communication_concerns": []
        }
    
    try:
        # Initialize accumulators
        clarity_scores = []
        confidence_scores = []
        fluency_scores = []
        professionalism_scores = []
        sentiment_scores = []
        sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
        candidate_questions = []
        sentiment_timeline = []
        
        # Process each segment
        for idx, segment in enumerate(segments):
            # Collect communication scores
            if 'clarity_score' in segment:
                clarity_scores.append(segment['clarity_score'])
            if 'confidence_score' in segment:
                confidence_scores.append(segment['confidence_score'])
            if 'fluency_score' in segment:
                fluency_scores.append(segment['fluency_score'])
            if 'professionalism_score' in segment:
                professionalism_scores.append(segment['professionalism_score'])
            
            # Collect sentiment data
            if 'sentiment_score' in segment:
                sentiment_scores.append(segment['sentiment_score'])
            
            sentiment = segment.get('sentiment', 'neutral').lower()
            if sentiment in sentiment_counts:
                sentiment_counts[sentiment] += 1
            
            # Build sentiment timeline
            sentiment_timeline.append({
                "segment_index": idx,
                "text_preview": segment.get('text', '')[:100],
                "sentiment": sentiment,
                "score": segment.get('sentiment_score', 50)
            })
            
            # Extract questions from candidate
            if segment.get('is_question') and segment.get('speaker', '').lower() == 'candidate':
                candidate_questions.append({
                    "timestamp": segment.get('start_time', 0),
                    "question": segment.get('question_text', segment.get('text', ''))
                })
        
        # Calculate averages
        avg_clarity = sum(clarity_scores) / len(clarity_scores) if clarity_scores else 0
        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
        avg_fluency = sum(fluency_scores) / len(fluency_scores) if fluency_scores else 0
        avg_professionalism = sum(professionalism_scores) / len(professionalism_scores) if professionalism_scores else 0
        avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 50
        
        # Determine dominant sentiment
        if sentiment_counts["positive"] > sentiment_counts["negative"] and sentiment_counts["positive"] > sentiment_counts["neutral"]:
            dominant_sentiment = "positive"
            interest_level = min(100, 60 + (sentiment_counts["positive"] / len(segments) * 40))
        elif sentiment_counts["negative"] > sentiment_counts["positive"] and sentiment_counts["negative"] > sentiment_counts["neutral"]:
            dominant_sentiment = "negative"
            interest_level = max(0, 40 - (sentiment_counts["negative"] / len(segments) * 40))
        else:
            dominant_sentiment = "neutral"
            interest_level = 50
        
        # Calculate enthusiasm (based on confidence and fluency)
        enthusiasm_score = (avg_confidence + avg_fluency) / 2
        
        logger.debug(
            f"Segment analysis - Clarity: {avg_clarity:.1f}, "
            f"Confidence: {avg_confidence:.1f}, Fluency: {avg_fluency:.1f}, "
            f"Professionalism: {avg_professionalism:.1f}, "
            f"Sentiment: {dominant_sentiment} ({avg_sentiment:.1f})"
        )
        
        return {
            "avg_clarity_score": round(avg_clarity, 2),
            "avg_confidence_score": round(avg_confidence, 2),
            "avg_fluency_score": round(avg_fluency, 2),
            "avg_responsiveness_score": round(avg_confidence, 2),  # Use confidence as responsiveness
            "avg_professionalism_score": round(avg_professionalism, 2),
            "dominant_sentiment": dominant_sentiment,
            "interest_level": round(interest_level, 2),
            "enthusiasm_score": round(enthusiasm_score, 2),
            "hesitation_detected": sentiment_counts["negative"] > len(segments) * 0.2,
            "stress_indicators": sentiment_counts["negative"] > len(segments) * 0.3,
            "sentiment_timeline": sentiment_timeline,
            "candidate_questions": candidate_questions,
            "communication_strengths": _identify_strengths(avg_clarity, avg_confidence, avg_fluency, avg_professionalism),
            "communication_concerns": _identify_concerns(avg_clarity, avg_confidence, avg_fluency, sentiment_counts)
        }
        
    except Exception as e:
        logger.error(f"Error extracting segment analysis: {str(e)}")
        # Return safe defaults
        return {
            "avg_clarity_score": 0,
            "avg_confidence_score": 0,
            "avg_fluency_score": 0,
            "avg_responsiveness_score": 0,
            "avg_professionalism_score": 0,
            "dominant_sentiment": "neutral",
            "interest_level": 0,
            "enthusiasm_score": 0,
            "hesitation_detected": False,
            "stress_indicators": False,
            "sentiment_timeline": [],
            "candidate_questions": [],
            "communication_strengths": [],
            "communication_concerns": []
        }


def _identify_strengths(clarity: float, confidence: float, fluency: float, professionalism: float) -> List[str]:
    """Identify communication strengths based on scores"""
    strengths = []
    
    if clarity > 75:
        strengths.append("Clear articulation")
    if confidence > 75:
        strengths.append("Good confidence level")
    if fluency > 75:
        strengths.append("Smooth communication flow")
    if professionalism > 75:
        strengths.append("Professional demeanor")
    
    # If no high scores, identify relative strengths
    if not strengths:
        max_score = max(clarity, confidence, fluency, professionalism)
        if clarity == max_score:
            strengths.append("Relatively clear speech")
        elif confidence == max_score:
            strengths.append("Relatively confident")
        elif fluency == max_score:
            strengths.append("Relatively fluent")
        elif professionalism == max_score:
            strengths.append("Professional approach")
    
    return strengths


def _identify_concerns(clarity: float, confidence: float, fluency: float, sentiment_counts: Dict) -> List[str]:
    """Identify communication concerns based on scores and sentiment"""
    concerns = []
    
    if clarity < 50:
        concerns.append("Speech clarity issues")
    if confidence < 50:
        concerns.append("Low confidence level")
    if fluency < 50:
        concerns.append("Frequent pauses or hesitations")
    
    if sentiment_counts.get("negative", 0) > 0:
        concerns.append("Negative sentiment detected")
    
    return concerns


def _merge_similar_segments(segments: List[Dict]) -> List[Dict]:
    """Merge ONLY very short adjacent segments from same speaker to reduce filler.

    Conservative heuristic:
    - Only merge if same speaker AND current segment is very short (<30 chars) - these are usually filler.
    - When merging, preserve all score data by averaging.
    """
    if not segments or len(segments) < 2:
        return segments

    merged = [segments[0].copy()]

    for seg in segments[1:]:
        prev = merged[-1]
        same_speaker = (seg.get('speaker') == prev.get('speaker'))
        very_short_filler = len(seg.get('text', '')) < 30  # Only ultra-short texts are likely filler

        if same_speaker and very_short_filler:
            # Merge texts
            prev['text'] = (prev.get('text', '') + ' ' + seg.get('text', '')).strip()
            # extend end_time
            prev['end_time'] = max(prev.get('end_time', 0), seg.get('end_time', 0))
            # average scores
            for score_key in ['sentiment_score', 'clarity_score', 'confidence_score', 'fluency_score', 'professionalism_score']:
                try:
                    prev_val = float(prev.get(score_key, 0))
                    seg_val = float(seg.get(score_key, 0))
                    prev[score_key] = round((prev_val + seg_val) / 2, 2)
                except Exception:
                    pass
            # combine question flags
            prev['is_question'] = prev.get('is_question', False) or seg.get('is_question', False)
            if not prev.get('question_text') and seg.get('question_text'):
                prev['question_text'] = seg.get('question_text')
        else:
            merged.append(seg.copy())

    return merged


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
