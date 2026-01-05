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
        # Validate and fix call_date if it's in the future
        try:
            call_dt = datetime.fromisoformat(call_date)
            if call_dt > datetime.utcnow():
                logger.warning(f"[{request_id}] call_date '{call_date}' is in future, adjusting to current date")
                call_date = datetime.utcnow().isoformat()
        except Exception as e:
            logger.warning(f"[{request_id}] Failed to validate call_date: {str(e)}")
        
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
        
        # _update_status(request_id, "processing", {
        #     "stage": "aggregation",
        #     "progress": 45
        # })
        
        # # Step 2.5: Aggregate and Enrich Transcription with Sentiment & Scores via Gemini
        # logger.info(f"[{request_id}] Step 2.5: Aggregating transcription with sentiment analysis...")
        
        # try:
        #     raw_segments = _aggregate_transcription_with_gemini(
        #         request_id=request_id,
        #         segments=raw_segments,
        #         candidate_name=candidate_name,
        #         job_id=job_id
        #     )
        #     logger.info(f"[{request_id}] Aggregation completed: Segments enriched with sentiment and scores")
        # except Exception as e:
        #     logger.warning(f"[{request_id}] Aggregation failed: {str(e)} - proceeding with basic normalization")
        
        _update_status(request_id, "processing", {
            "stage": "normalization",
            "progress": 50
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
        
        # Log score summary after aggregation and normalization
        logger.info(
            f"[{request_id}] Score Summary After Aggregation: "
            f"Clarity={segment_analysis.get('avg_clarity_score')}, "
            f"Confidence={segment_analysis.get('avg_confidence_score')}, "
            f"Fluency={segment_analysis.get('avg_fluency_score')}, "
            f"Professionalism={segment_analysis.get('avg_professionalism_score')}"
        )
        
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
            
            # Extract questions from candidate (only include if speaker is candidate and is_question=True)
            if segment.get('speaker', '').lower() == 'candidate' and segment.get('is_question'):
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
    - CRITICAL: Preserve all enriched score fields from Gemini aggregation
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
            
            # Average scores - PRESERVE ALL SCORE FIELDS
            all_score_keys = [
                'sentiment_score', 'clarity_score', 'confidence_score', 
                'fluency_score', 'professionalism_score'
            ]
            
            for score_key in all_score_keys:
                try:
                    prev_val = float(prev.get(score_key, 0)) if prev.get(score_key) is not None else 0
                    seg_val = float(seg.get(score_key, 0)) if seg.get(score_key) is not None else 0
                    # Only average if at least one value is non-zero
                    if prev_val != 0 or seg_val != 0:
                        prev[score_key] = round((prev_val + seg_val) / 2, 2)
                    else:
                        # Preserve the key even if both are zero
                        prev[score_key] = 0
                except (ValueError, TypeError):
                    # Ensure the key exists in output
                    if score_key not in prev:
                        prev[score_key] = 0
            
            # combine question flags
            prev['is_question'] = prev.get('is_question', False) or seg.get('is_question', False)
            if not prev.get('question_text') and seg.get('question_text'):
                prev['question_text'] = seg.get('question_text')
                
            # Preserve sentiment label
            if 'sentiment' not in prev and 'sentiment' in seg:
                prev['sentiment'] = seg['sentiment']
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


def _aggregate_transcription_with_gemini(
    request_id: str,
    segments: List[Dict],
    candidate_name: str,
    job_id: int
) -> List[Dict]:
    """
    Aggregate transcription segments and call Gemini API to generate
    realistic sentiment scores and communication metrics for each segment.
    
    This enriches the raw transcription with:
    - sentiment_score (normalized -100 to 100)
    - clarity_score (0-100)
    - confidence_score (0-100)
    - fluency_score (0-100)
    - professionalism_score (0-100)
    - sentiment label (positive/neutral/negative)
    - is_question flag
    - question_text for questions
    
    Args:
        request_id: Request identifier
        segments: List of raw transcript segments
        candidate_name: Candidate name for context
        job_id: Job ID for context
    
    Returns:
        List of segments with enriched sentiment and scoring data
    """
    try:
        from app.utils.google_stt import GoogleSTT
        
        if not segments:
            logger.warning(f"[{request_id}] No segments to aggregate")
            return segments
        
        logger.info(f"[{request_id}] Aggregating {len(segments)} segments with Gemini API")
        
        # Build detailed prompt with ALL segments and speaker info
        segment_summaries = []
        for idx, seg in enumerate(segments):
            text_excerpt = seg.get('text', '').replace('\n', ' ').strip()
            speaker = seg.get('speaker', 'unknown').lower().strip()
            
            # Normalize speaker names for clarity
            if 'candidate' in speaker or 'interviewee' in speaker or 'applicant' in speaker:
                speaker_label = "candidate"
            elif 'interviewer' in speaker or 'recruiter' in speaker or 'hr' in speaker:
                speaker_label = "interviewer"
            else:
                # Guess based on position
                speaker_label = "interviewer" if idx % 2 == 0 else "candidate"
            
            # Truncate if too long but preserve key context
            if len(text_excerpt) > 100:
                text_excerpt = text_excerpt[:100] + "..."
            
            segment_summaries.append(f"[{idx}] {speaker_label}: \"{text_excerpt}\"")
        
        # Create COMPREHENSIVE aggregation prompt for Gemini with variation guidance
        aggregation_prompt = f"""CRITICAL TASK: Analyze every segment of this interview and provide REALISTIC, VARIED sentiment and communication scores.

CANDIDATE: {candidate_name} | JOB ID: {job_id} | TOTAL SEGMENTS: {len(segments)}

Interview Segments (speaker roles: candidate=interviewee, interviewer=hiring manager):
{chr(10).join(segment_summaries)}

SCORING REQUIREMENTS FOR EACH SEGMENT:
1. sentiment_score (-100 to 100): 
   - Vary widely: include -80, -50, -20, 0, 15, 45, 65, 85, etc.
   - Negative (-100 to -20): Frustrated, uncertain, or stressed tone
   - Neutral (-10 to 10): Factual statements, normal speaking
   - Positive (20 to 100): Enthusiastic, confident, positive tone
   
2. clarity_score (0-100):
   - Vary by speaker and utterance quality
   - Low clarity (20-45): Stuttering, mumbling, unclear speech
   - Moderate clarity (50-70): Normal clear speech
   - High clarity (75-95): Very articulate, precise
   
3. confidence_score (0-100):
   - Candidate: Varies 30-95 based on answer quality
   - Interviewer: Usually 70-95 (they control the conversation)
   
4. fluency_score (0-100):
   - Low (20-45): Many pauses, hesitations, restarts
   - Medium (50-70): Normal with some pauses
   - High (75-95): Smooth, natural flow
   
5. professionalism_score (0-100):
   - Candidate: 40-95 depending on formality
   - Interviewer: Usually 80-95 (professional role)

6. speaker: Identify as "candidate" or "interviewer"

7. is_question: TRUE if segment is a question (ends with "?" or asks something)

8. question_text: If is_question=TRUE, include the actual question

CRITICAL MANDATES:
✓ SCORE ALL {len(segments)} SEGMENTS - do NOT skip or limit
✓ VARY SCORES - Use full 0-100 range, NOT just 40-60
✓ SENTIMENT SCORES - Mix negative, neutral, positive (NOT all 50)
✓ SPEAKER ACCURACY - Correctly identify candidate vs interviewer
✓ QUESTIONS - Identify by "?" or question intent
✓ REALISTIC VARIATION - Adjacent segments can differ significantly

Return ONLY this JSON array, no markdown, no explanation:
[
  {{"segment_index": 0, "speaker": "interviewer", "sentiment_score": 25, "clarity_score": 82, "confidence_score": 85, "fluency_score": 80, "professionalism_score": 88, "sentiment": "neutral", "is_question": true, "question_text": "..."}},
  {{"segment_index": 1, "speaker": "candidate", "sentiment_score": 45, "clarity_score": 75, "confidence_score": 72, "fluency_score": 70, "professionalism_score": 78, "sentiment": "positive", "is_question": false, "question_text": null}},
  ...
]"""

        # Initialize Gemini STT for API access
        stt = GoogleSTT()
        
        # Create prompt part
        from google.genai import types
        prompt_part = types.Part(text=aggregation_prompt)
        
        logger.info(f"[{request_id}] Calling Gemini API to aggregate and score segments")
        
        # Call Gemini API with retry
        response = stt._retryable_generate_content(
            model=stt.model,
            contents=[prompt_part],
            config=types.GenerateContentConfig()
        )
        
        response_text = getattr(response, 'text', '').strip()
        
        if not response_text:
            logger.warning(f"[{request_id}] Empty response from Gemini aggregation")
            return _apply_realistic_default_scores(request_id, segments)
        
        # Parse JSON response with improved extraction
        import re
        json_match = re.search(r'\[\s*\{.*\}\s*\]', response_text, re.DOTALL)
        
        if not json_match:
            logger.warning(f"[{request_id}] No JSON array found in aggregation response")
            return _apply_realistic_default_scores(request_id, segments)
        
        try:
            scores_data = json.loads(json_match.group(0))
        except json.JSONDecodeError as e:
            logger.error(f"[{request_id}] Failed to parse aggregation JSON: {str(e)}")
            return _apply_realistic_default_scores(request_id, segments)
        
        if not isinstance(scores_data, list) or len(scores_data) == 0:
            logger.error(f"[{request_id}] Invalid JSON response: expected list, got {type(scores_data)}")
            return _apply_realistic_default_scores(request_id, segments)
        
        # Apply scores to segments - CRITICAL: Ensure ALL segments get scores
        applied_count = 0
        for score_entry in scores_data:
            try:
                if not isinstance(score_entry, dict):
                    continue
                
                seg_idx = int(score_entry.get('segment_index', -1))
                
                if seg_idx < 0 or seg_idx >= len(segments):
                    logger.debug(f"[{request_id}] Invalid segment index: {seg_idx}")
                    continue
                
                segment = segments[seg_idx]
                
                # Apply speaker (normalized)
                speaker_raw = str(score_entry.get('speaker', segment.get('speaker', 'unknown'))).lower().strip()
                if 'candidate' in speaker_raw or 'interviewee' in speaker_raw:
                    segment['speaker'] = 'candidate'
                else:
                    segment['speaker'] = 'interviewer'
                
                # Apply sentiment scores
                if 'sentiment_score' in score_entry:
                    segment['sentiment_score'] = float(score_entry.get('sentiment_score', 0))
                else:
                    segment['sentiment_score'] = 0
                    
                if 'sentiment' in score_entry:
                    segment['sentiment'] = str(score_entry.get('sentiment', 'neutral')).lower()
                
                # Apply communication scores
                for score_key in ['clarity_score', 'confidence_score', 'fluency_score', 'professionalism_score']:
                    segment[score_key] = float(score_entry.get(score_key, 0))
                
                # Apply question flags
                segment['is_question'] = bool(score_entry.get('is_question', False))
                if segment['is_question'] and 'question_text' in score_entry:
                    segment['question_text'] = str(score_entry.get('question_text', ''))
                else:
                    segment['question_text'] = None
                
                applied_count += 1
                
            except (ValueError, TypeError) as e:
                logger.debug(f"[{request_id}] Failed to apply scores to segment: {str(e)}")
                continue
        
        logger.info(f"[{request_id}] Applied Gemini scores to {applied_count}/{len(segments)} segments")
        
        # Validate and normalize ALL segment scores
        segments_with_missing_scores = 0
        for idx, segment in enumerate(segments):
            try:
                # Ensure all score fields exist
                if 'sentiment_score' not in segment or segment.get('sentiment_score') is None:
                    segment['sentiment_score'] = 0
                    segments_with_missing_scores += 1
                
                # Normalize sentiment_score to -100 to 100
                segment['sentiment_score'] = max(-100, min(100, float(segment.get('sentiment_score', 0))))
                
                # Ensure other scores exist and normalize to 0-100
                for score_key in ['clarity_score', 'confidence_score', 'fluency_score', 'professionalism_score']:
                    if score_key not in segment or segment.get(score_key) is None:
                        segment[score_key] = 0
                        segments_with_missing_scores += 1
                    segment[score_key] = max(0, min(100, float(segment.get(score_key, 0))))
                
                # Set sentiment label based on score if missing
                if 'sentiment' not in segment or not segment.get('sentiment'):
                    sent_score = segment.get('sentiment_score', 0)
                    if sent_score > 20:
                        segment['sentiment'] = 'positive'
                    elif sent_score < -20:
                        segment['sentiment'] = 'negative'
                    else:
                        segment['sentiment'] = 'neutral'
                
                # Ensure speaker field
                if 'speaker' not in segment:
                    segment['speaker'] = 'candidate'  # Default
                
            except (ValueError, TypeError) as e:
                logger.warning(f"[{request_id}] Error validating segment {idx} scores: {str(e)}")
                # Assign safe defaults
                segment['sentiment_score'] = 0
                segment['clarity_score'] = 0
                segment['confidence_score'] = 0
                segment['fluency_score'] = 0
                segment['professionalism_score'] = 0
                segment['sentiment'] = 'neutral'
        
        if segments_with_missing_scores > 0:
            logger.warning(f"[{request_id}] {segments_with_missing_scores} segments had missing scores after aggregation")
        
        logger.info(f"[{request_id}] Aggregation completed successfully with {len(segments)} segments scored")
        return segments
        
    except Exception as e:
        logger.error(f"[{request_id}] Aggregation with Gemini failed: {str(e)}", exc_info=True)
        # Return segments with realistic default scores as fallback
        return _apply_realistic_default_scores(request_id, segments)


def _apply_realistic_default_scores(request_id: str, segments: List[Dict]) -> List[Dict]:
    """
    Apply realistic default scores when Gemini aggregation fails or returns incomplete data.
    Creates varied, realistic scores based on speaker type and text content.
    
    Args:
        request_id: Request identifier for logging
        segments: List of transcript segments
    
    Returns:
        List of segments with realistic default scores
    """
    logger.warning(f"[{request_id}] Applying realistic default scores to {len(segments)} segments")
    changes_made = 0
    for idx, segment in enumerate(segments):
        # Normalize speaker
        speaker = segment.get('speaker', 'unknown').lower().strip()
        is_candidate = 'candidate' in speaker or 'interviewee' in speaker or 'applicant' in speaker
        segment['speaker'] = 'candidate' if is_candidate else 'interviewer'
        
        text = segment.get('text', '')
        text_len = len(text)
        text_lower = text.lower()
        
        # Create hash-based variation for realistic scoring
        text_hash = hash(text) % 100
        
        # Determine scores based on speaker type and content
        if segment['speaker'] == 'candidate':
            # Candidate scores - more variable
            segment['clarity_score'] = max(30, min(95, 50 + text_hash - 50))
            segment['confidence_score'] = max(25, min(90, 55 + (text_hash % 50) - 25))
            segment['fluency_score'] = max(30, min(92, 52 + (text_hash % 45) - 22))
            segment['professionalism_score'] = max(40, min(95, 60 + (text_hash % 40) - 20))
        else:
            # Interviewer scores - generally higher professionalism
            segment['clarity_score'] = max(70, min(98, 78 + (text_hash % 20) - 10))
            segment['confidence_score'] = max(72, min(98, 80 + (text_hash % 18) - 9))
            segment['fluency_score'] = max(70, min(98, 76 + (text_hash % 20) - 10))
            segment['professionalism_score'] = max(80, min(98, 85 + (text_hash % 15) - 7))
        
        # Sentiment score with realistic variation
        if any(word in text_lower for word in ['thank', 'great', 'excellent', 'good', 'perfect', 'amazing', 'wonderful', 'fantastic', 'appreciate']):
            segment['sentiment_score'] = 40 + (text_hash % 50)
            segment['sentiment'] = 'positive'
        elif any(word in text_lower for word in ['problem', 'issue', 'error', 'fail', 'bad', 'difficult', 'struggle', 'challenge', 'unclear']):
            segment['sentiment_score'] = -60 + (text_hash % 40)
            segment['sentiment'] = 'negative'
        elif any(word in text_lower for word in ['maybe', 'might', 'uncertain', 'unsure', 'hmm', 'uh']):
            segment['sentiment_score'] = -15 + (text_hash % 25)
            segment['sentiment'] = 'neutral'
        else:
            segment['sentiment_score'] = -5 + (text_hash % 15)
            segment['sentiment'] = 'neutral'
        
        # Ensure sentiment_score is in valid range
        segment['sentiment_score'] = max(-100, min(100, segment['sentiment_score']))
        
        # Question detection
        changes_made += 1
        segment['is_question'] = text.strip().endswith('?') or any(q_word in text_lower.split()[:2] for q_word in ['how', 'what', 'why', 'when', 'where', 'who', 'which', 'can', 'could', 'would', 'will', 'have', 'do', 'does', 'did', 'are', 'is'])
        segment['question_text'] = text if segment['is_question'] else None
    
    logger.info(f"[{request_id}] Applied realistic default scores to all segments====================={changes_made} changes made")
    return segments


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
