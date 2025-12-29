"""
Gemini Speech-to-Text Integration with Sentiment & Communication Analysis
"""

from google.genai import types
from google import genai as gg
import logging
import os
from typing import List, Dict
import io
import re
import json
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.genai.errors import ServerError, ClientError

logger = logging.getLogger("app_logger")


class GoogleSTT:
    """Gemini Audio transcription service"""
    
    def __init__(self):
        """Initialize Gemini client using GOOGLE_API_KEY or GEMINI_API_KEY"""
        try:
            # Prefer GOOGLE_API_KEY if present (google.genai client may also look for it)
            api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            used_key = "GOOGLE_API_KEY" if os.getenv("GOOGLE_API_KEY") else ("GEMINI_API_KEY" if os.getenv("GEMINI_API_KEY") else None)

            if not api_key or not used_key:
                raise RuntimeError(
                    "No API key found. Set either GOOGLE_API_KEY or GEMINI_API_KEY in the environment for Gemini transcription."
                )

            # Masked logging to avoid leaking secret
            masked = (api_key[:4] + "****") if len(api_key) > 4 else "****"
            logger.info(f"Using {used_key} for Gemini client (masked={masked})")

            self.client = gg.Client(api_key=api_key)
            self.model = "gemini-2.5-flash"
            logger.info(f"Initialized Gemini STT with model: {self.model}")

        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {str(e)}")
            raise
    
    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10),
           retry=retry_if_exception_type(ServerError))
    def _retryable_generate_content(self, model, contents, config):
        """Wrapper for retrying Gemini API calls."""
        return self.client.models.generate_content(
            model=model,
            contents=contents,
            config=config
        )

    def transcribe(self, audio_content: bytes) -> List[Dict]:
        """
        Transcribe audio using Gemini API with sentiment and communication analysis
        
        Args:
            audio_content: Audio data in WAV format (16kHz, mono)
        
        Returns:
            List of transcript segments with timestamps, sentiment, and communication metrics
        """
        try:
            logger.info(f"Starting Gemini transcription - Audio size: {len(audio_content) / (1024*1024):.2f} MB")
            
            # Check file size - split if too large (>15MB)
            if len(audio_content) > 15 * 1024 * 1024:
                logger.warning(f"Audio file is large, chunking for processing...")
                large_result = self._transcribe_large_audio(audio_content)
                segments = large_result.get('segments', [])
                chunk_summaries = large_result.get('chunk_summaries', [])
                try:
                    final_summary = self._final_summary_from_chunks(chunk_summaries) if chunk_summaries else {}
                except Exception as e:
                    logger.warning(f"Final summary creation failed: {str(e)} - falling back to aggregator")
                    final_summary = self._merge_chunk_summaries_locally(chunk_summaries)

                return {'segments': segments, 'chunk_summaries': chunk_summaries, 'final_summary': final_summary}
            
            # Detect mime type from audio content
            mime_type = self._detect_mime_type(audio_content)
            logger.info(f"Detected mime type: {mime_type}")
            
            # Create audio part
            audio_part = types.Part.from_bytes(data=audio_content, mime_type=mime_type)
            
            # Create advanced prompt for structured analysis
            prompt_text = self._get_analysis_prompt()
            prompt_part = types.Part(text=prompt_text)
            
            contents = [audio_part, prompt_part]
            gen_cfg = types.GenerateContentConfig()
            
            # Call Gemini API with retry logic
            logger.info("Sending audio to Gemini API for transcription and analysis...")
            try:
                response = self._retryable_generate_content(
                    model=self.model,
                    contents=contents,
                    config=gen_cfg
                )
            except ClientError as ce:
                # ClientError often indicates invalid or missing API key
                logger.error(f"Gemini API client error: {str(ce)}")
                raise RuntimeError(
                    "Gemini transcription failed due to API key/authentication error. "
                    "Ensure GOOGLE_API_KEY or GEMINI_API_KEY is set and valid in the worker environment. "
                    "Original error: " + str(ce)
                ) from ce
            
            # Extract and parse response
            response_text = getattr(response, "text", "").strip()
            
            if not response_text:
                logger.warning("Empty response received from Gemini")
                return {'segments': [], 'chunk_summaries': [], 'final_summary': {}}
            
            logger.info(f"Raw response length: {len(response_text)} characters")
            
            # Parse structured JSON response (single chunk)
            chunk_obj = self._parse_analysis_response(response_text)

            if isinstance(chunk_obj, dict):
                segments = chunk_obj.get('segments', [])
                chunk_summaries = [{
                    'chunk_id': chunk_obj.get('chunk_id'),
                    'short_summary': chunk_obj.get('chunk_summary', {}).get('short_summary', ''),
                    'key_topics': chunk_obj.get('chunk_summary', {}).get('key_topics', []),
                    'key_questions': chunk_obj.get('chunk_summary', {}).get('key_questions', []),
                    'segments_preview': [s.get('text', '')[:100] for s in chunk_obj.get('segments', [])[:3]]
                }]
            else:
                segments = chunk_obj
                chunk_summaries = []

            # If there are multiple chunks (handled in _transcribe_large_audio), final summary will be created
            final_summary = {}
            if chunk_summaries:
                try:
                    final_summary = self._final_summary_from_chunks(chunk_summaries)
                except Exception as e:
                    logger.warning(f"Final summary creation failed: {str(e)}")
                    final_summary = {}

            logger.info(f"Transcription completed: {len(segments)} segments with analysis")
            
            # If we have chunk_summaries (could be from large audio), attempt final summary
            if not chunk_summaries:
                # small file, chunk_summaries may already be empty
                final_summary = final_summary or {}
            else:
                try:
                    final_summary = self._final_summary_from_chunks(chunk_summaries)
                except Exception as e:
                    logger.warning(f"Final summary creation failed: {str(e)} - falling back to aggregator")
                    final_summary = self._merge_chunk_summaries_locally(chunk_summaries)

            return {'segments': segments, 'chunk_summaries': chunk_summaries, 'final_summary': final_summary}
            
        except ServerError as e:
            logger.error(f"Gemini transcription failed with server error: {str(e)}")
            raise

        except Exception as e:
            logger.error(f"Gemini transcription failed: {str(e)}")
            raise
    
    def _detect_mime_type(self, audio_content: bytes) -> str:
        """Detect audio mime type from content"""
        # Check magic bytes
        if audio_content[:4] == b'RIFF' and audio_content[8:12] == b'WAVE':
            return "audio/wav"
        elif audio_content[:3] == b'ID3' or audio_content[:2] == b'\xff\xfb':
            return "audio/mp3"
        elif audio_content[:4] == b'OggS':
            return "audio/ogg"
        else:
            # Default to WAV since we preprocess to WAV
            return "audio/wav"
    
    def _get_analysis_prompt(self) -> str:
        """
        Generate advanced prompt for structured analysis output
        
        Returns:
            Detailed prompt for Gemini to analyze call recording
        """
        return """Analyze this interview call recording and provide a structured JSON analysis with complete segment-level detail.

IMPORTANT: Return ONLY valid JSON, no markdown, no additional text.

CRITICAL REQUIREMENTS:
1. Each segment MUST represent one distinct speaker turn (do NOT merge speaker turns together).
2. Preserve all individual speaker statements as separate segments - one segment per person speaking.
3. Do NOT merge multiple statements from the same speaker into one large segment.
4. Every segment must have complete fields: segment_id, speaker, start_time, end_time, text (full content), sentiment, sentiment_score (0-100), clarity_score (0-100), confidence_score (0-100), fluency_score (0-100), professionalism_score (0-100), is_question (boolean), question_text (or null).
5. Sentiment score and all quality scores MUST be non-zero and realistic (not 0, not 50 for all).
6. Provide per-chunk `chunk_summary` with: chunk_id, total_segments, key_topics (max 10), key_questions (max 10), short_summary (max 300 chars).
7. Include `overall_analysis` with conversation_summary and key_findings.

Return response in this JSON structure:
{
  "chunk_id": <number>,
  "total_segments": <number>,
  "chunk_summary": {
    "short_summary": "...",
    "key_topics": ["topic1", "topic2"],
    "key_questions": ["q1", "q2"]
  },
  "overall_analysis": {
    "conversation_summary": "...",
    "key_findings": []
  },
  "segments": [<segment objects - one per speaker turn, with all fields and realistic non-zero scores>]
}

Focus on: Accurate speaker separation | Complete segment detail | Realistic sentiment/quality scores | No over-merging."""
    
    def _get_score_annotation_prompt(self, segments: List[Dict]) -> str:
        """Generate prompt to request score annotation for segments missing scores."""
        segment_texts = "\n".join([
            f"Seg {i}: Speaker={s.get('speaker', '?')}, Text=\"{s.get('text', '')[:80]}...\""
            for i, s in enumerate(segments)
        ])
        
        return f"""Rate each segment below on these scales (0-100):
- sentiment_score: -100 to 100, where negative=negative sentiment, 0=neutral, positive=positive sentiment
- clarity_score: How clear/articulate is the speech? (0=very unclear, 100=crystal clear)
- confidence_score: How confident does the speaker sound? (0=very uncertain, 100=very confident)
- fluency_score: How fluent/smooth is the speech? (0=stuttering/choppy, 100=very smooth)
- professionalism_score: How professional is the tone? (0=casual/rude, 100=very professional)

Segments:
{segment_texts}

Return ONLY this JSON structure (no markdown, no extra text):
{{
  "segments": [
    {{"segment_index": 0, "sentiment_score": X, "clarity_score": Y, "confidence_score": Z, "fluency_score": W, "professionalism_score": V}},
    ...
  ]
}}

Be realistic and vary scores - not all should be 50 or the same value."""
    
    def _annotate_segments_with_gemini(self, segments: List[Dict]) -> List[Dict]:
        """Call Gemini to annotate segments with proper scores."""
        if not segments:
            return segments
        
        try:
            prompt_text = self._get_score_annotation_prompt(segments)
            prompt_part = types.Part(text=prompt_text)
            
            logger.info("Calling Gemini to annotate segment scores...")
            response = self._retryable_generate_content(
                model=self.model,
                contents=[prompt_part],
                config=types.GenerateContentConfig()
            )
            
            response_text = getattr(response, 'text', '').strip()
            
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                scores_data = json.loads(json_match.group(0))
                
                # Apply scores to segments
                for score_entry in scores_data.get('segments', []):
                    idx = score_entry.get('segment_index', -1)
                    if 0 <= idx < len(segments):
                        segments[idx].update({
                            'sentiment_score': max(-100, min(100, float(score_entry.get('sentiment_score', 0)))),
                            'clarity_score': max(0, min(100, float(score_entry.get('clarity_score', 50)))),
                            'confidence_score': max(0, min(100, float(score_entry.get('confidence_score', 50)))),
                            'fluency_score': max(0, min(100, float(score_entry.get('fluency_score', 50)))),
                            'professionalism_score': max(0, min(100, float(score_entry.get('professionalism_score', 50))))
                        })
                
                logger.info(f"Successfully annotated {len(segments)} segments with Gemini scores")
                return segments
        except Exception as e:
            logger.error(f"Gemini annotation failed: {str(e)}")
        
        return segments
    
    def _extract_json_from_text(self, text: str) -> Dict:
        """Extracts a JSON object from text if present.
        Handles ```json blocks and inline JSON by balancing braces starting from a marker like '"chunk_summary"' or '"chunk_id"'.
        Returns parsed dict or None."""
        # Handle code fence first
        m = re.search(r'```(?:json)?\s*(\{.*\})\s*```', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                return None
        # Fallback: look for a JSON object containing "chunk_summary" or "chunk_id"
        marker = re.search(r'\{.*?(?:"chunk_summary"|"chunk_id").*', text, re.DOTALL)
        if marker:
            start = text.find('{', marker.start())
            if start == -1:
                return None
            depth = 0
            for i in range(start, len(text)):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        candidate = text[start:i+1]
                        try:
                            return json.loads(candidate)
                        except Exception:
                            return None
        return None

    def _annotate_segments_with_gemini(self, segments: List[Dict]) -> List[Dict]:
        """Ask Gemini to annotate segments with realistic scores. Returns segments with scores applied."""
        if not segments:
            return segments
        try:
            # Build a compact prompt
            lines = []
            for i, s in enumerate(segments):
                excerpt = s.get('text','').replace('\n',' ').strip()[:120]
                lines.append(f"Seg {i}: {excerpt}")
            prompt = (
                "For each segment below, return a JSON array with objects {segment_index, sentiment_score, clarity_score, confidence_score, fluency_score, professionalism_score}."
                "\nProvide realistic scores (0-100). Do not return any other text.\n\nSegments:\n" + "\n".join(lines)
            )
            prompt_part = types.Part(text=prompt)
            resp = self._retryable_generate_content(model=self.model, contents=[prompt_part], config=types.GenerateContentConfig())
            resp_text = getattr(resp,'text','').strip()
            jm = re.search(r'\{.*\}', resp_text, re.DOTALL)
            if jm:
                data = json.loads(jm.group(0))
                for entry in data.get('segments', []):
                    idx = entry.get('segment_index')
                    if idx is None or idx < 0 or idx >= len(segments):
                        continue
                    seg = segments[idx]
                    for key in ('sentiment_score','clarity_score','confidence_score','fluency_score','professionalism_score'):
                        if key in entry:
                            try:
                                seg[key] = float(entry[key])
                            except Exception:
                                pass
                logger.info(f"Annotated {len(segments)} segments via Gemini for scores")
                return segments
        except Exception as e:
            logger.warning(f"Failed to annotate segments via Gemini: {str(e)}")
        # nothing applied
        return segments

    def _parse_analysis_response(self, response_text: str) -> List[Dict]:
        """
        Parse JSON response from Gemini and extract segments with an
        alysis
        
        Args:
            response_text: Raw response from Gemini
        
        Returns:
            List of segments with analysis data
        """
        try:
            # Try to extract JSON from response (handle markdown code blocks)
            json_match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', response_text, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(1)
                logger.debug("Found JSON in markdown code block")
            else:
                # Try to find JSON object directly
                json_start = response_text.find('{')
                json_end = response_text.rfind('}')
                
                if json_start != -1 and json_end != -1:
                    json_str = response_text[json_start:json_end+1]
                    logger.debug("Found JSON object in response")
                else:
                    logger.warning("No JSON found in response, using fallback parsing")
                    return self._text_to_segments(response_text)
            
            # Parse JSON
            data = json.loads(json_str)
            logger.info(f"Successfully parsed JSON response for chunk {data.get('chunk_id', 'unknown')} with {data.get('total_segments', 0)} segments")
            
            # Sanitize and preserve full segment details; extract embedded chunk JSON if present
            segments = []
            raw_segments = data.get('segments', [])
            extracted_chunk_json = None

            for segment in raw_segments:
                raw_text = (segment.get('text', '') or '').strip()
                # First, try to extract any embedded JSON in this segment's text
                extracted = self._extract_json_from_text(raw_text)
                if extracted and not extracted_chunk_json:
                    extracted_chunk_json = extracted
                    # Remove the JSON portion from text by replacing the JSON substring if found
                    # best-effort: remove the first '{' to the matching '}' occurrence
                    brace_start = raw_text.find('{')
                    if brace_start != -1:
                        # attempt to remove by finding matching brace
                        depth = 0
                        end_idx = None
                        for i in range(brace_start, len(raw_text)):
                            if raw_text[i] == '{':
                                depth += 1
                            elif raw_text[i] == '}':
                                depth -= 1
                                if depth == 0:
                                    end_idx = i
                                    break
                        if end_idx:
                            raw_text = (raw_text[:brace_start] + raw_text[end_idx+1:]).strip()

                # Normalize whitespace
                text = re.sub(r"\s+", " ", raw_text)

                # Build processed segment, ensuring numeric defaults
                processed_segment = {
                    "segment_id": int(segment.get('segment_id', 0)),
                    "speaker": (segment.get('speaker', 'Speaker 1') or 'Speaker 1').lower(),
                    "start_time": float(segment.get('start_time', 0)),
                    "end_time": float(segment.get('end_time', 0)),
                    "text": text,
                    "sentiment": segment.get('sentiment', 'neutral'),
                    "sentiment_score": float(segment.get('sentiment_score', 0)) if segment.get('sentiment_score') is not None else 0,
                    "clarity_score": float(segment.get('clarity_score', 0)) if segment.get('clarity_score') is not None else 0,
                    "confidence_score": float(segment.get('confidence_score', 0)) if segment.get('confidence_score') is not None else 0,
                    "fluency_score": float(segment.get('fluency_score', 0)) if segment.get('fluency_score') is not None else 0,
                    "professionalism_score": float(segment.get('professionalism_score', 0)) if segment.get('professionalism_score') is not None else 0,
                    "is_question": bool(segment.get('is_question', False)),
                    "question_text": (segment.get('question_text') or None)
                }

                # Validate timestamps
                try:
                    if processed_segment['end_time'] < processed_segment['start_time']:
                        # swap if obviously out of order
                        st = processed_segment['start_time']
                        processed_segment['start_time'] = processed_segment['end_time']
                        processed_segment['end_time'] = st
                        logger.debug(f"Swapped timestamps for segment {processed_segment['segment_id']}")
                except Exception:
                    pass

                segments.append(processed_segment)

            # If embedded chunk JSON was found, use its summaries
            if extracted_chunk_json:
                chunk_summary = extracted_chunk_json.get('chunk_summary', data.get('chunk_summary', {}))
                overall_analysis = extracted_chunk_json.get('overall_analysis', data.get('overall_analysis', {}))
                logger.info("Extracted chunk JSON from segment text and applied to chunk_summary/overall_analysis")
            else:
                chunk_summary = data.get('chunk_summary') or {
                    'short_summary': '',
                    'key_topics': data.get('key_topics', []),
                    'key_questions': data.get('key_questions', [])
                }
                overall_analysis = data.get('overall_analysis', {})

            # If many segments are missing scores, request Gemini to annotate (preferred to random defaults)
            missing_scores = sum(1 for s in segments if not s.get('sentiment_score'))
            if missing_scores > 0:
                logger.warning(f"Found {missing_scores}/{len(segments)} segments with missing scores; requesting Gemini annotation")
                segments = self._annotate_segments_with_gemini(segments)

            # Final sanitization: ensure numeric ranges and sentiment labels
            for s in segments:
                try:
                    s['sentiment_score'] = max(-100, min(100, float(s.get('sentiment_score', 0))))
                except Exception:
                    s['sentiment_score'] = 0
                for k in ['clarity_score','confidence_score','fluency_score','professionalism_score']:
                    try:
                        s[k] = max(0, min(100, float(s.get(k, 0))))
                    except Exception:
                        s[k] = 0

            # Return a detailed chunk object
            chunk_obj = {
                'chunk_id': data.get('chunk_id', 0),
                'total_segments': data.get('total_segments', len(segments)),
                'chunk_summary': chunk_summary,
                'overall_analysis': overall_analysis,
                'segments': segments
            }

            # log overall analysis keys to avoid large dumps
            if data.get('overall_analysis'):
                logger.debug(f"Overall analysis keys: {list(data.get('overall_analysis', {}).keys())}")

            return chunk_obj
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {str(e)}")
            logger.debug(f"Response text: {response_text[:500]}...")
            # Fallback to simple text parsing
            return self._text_to_segments(response_text)
        except Exception as e:
            logger.error(f"Error parsing analysis response: {str(e)}")
            return self._text_to_segments(response_text)
    
    def _text_to_segments(self, text: str) -> List[Dict]:
        """
        Fallback: Convert plain text to segment format with default scores
        
        Args:
            text: Plain text transcript
        
        Returns:
            List of segments with default analysis values
        """
        # Split text into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        segments = []
        current_time = 0.0
        
        for idx, sentence in enumerate(sentences):
            if not sentence.strip():
                continue
            
            # Estimate duration based on word count (rough estimate: ~2 words per second)
            words = sentence.split()
            duration = max(1.0, len(words) * 0.5)
            short_text = re.sub(r"\s+", " ", sentence.strip())[:150]
            
            segment = {
                "segment_id": idx,
                "speaker": "Speaker 1",
                "start_time": current_time,
                "end_time": current_time + duration,
                "text": short_text,
                "sentiment": "neutral",
                "sentiment_score": 50,
                "clarity_score": 75,
                "confidence_score": 70,
                "fluency_score": 75,
                "professionalism_score": 70,
                "is_question": short_text.endswith('?'),
                "question_text": short_text if short_text.endswith('?') else None
            }
            
            segments.append(segment)
            current_time += duration
        
        logger.info(f"Created {len(segments)} segments from fallback parsing")
        return segments

    def _final_summary_from_chunks(self, chunk_summaries: List[Dict]) -> Dict:
        """
        Create a final compact summary by passing chunk summaries to Gemini
        Returns a dict with final summary fields
        """
        try:
            # Build concise prompt with chunk summaries
            prompt_parts = ["Create a final JSON summary of this interview by aggregating the chunk summaries. "
                            "Return ONLY JSON with fields: conversation_summary, overall_analysis, "
                            "call_summary, key_highlights, concerns, recommended_next_steps, candidate_questions. "
                            "Be concise."]

            for c in chunk_summaries:
                prompt_parts.append(f"Chunk {c.get('chunk_id')}: {c.get('short_summary','')}")
                # include key topics and questions
                if c.get('key_topics'):
                    prompt_parts.append(f"Topics: {', '.join(c.get('key_topics', [])[:5])}")
                if c.get('key_questions'):
                    prompt_parts.append(f"Questions: {', '.join(c.get('key_questions', [])[:5])}")

            prompt_text = "\n".join(prompt_parts)
            prompt_part = types.Part(text=prompt_text)

            response = self._retryable_generate_content(
                model=self.model,
                contents=[prompt_part],
                config=types.GenerateContentConfig()
            )

            response_text = getattr(response, 'text', '').strip()
            # extract JSON
            json_match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_start = response_text.find('{')
                json_end = response_text.rfind('}')
                if json_start != -1 and json_end != -1:
                    json_str = response_text[json_start:json_end+1]
                else:
                    raise ValueError('No JSON found in final summary response')

            final_data = json.loads(json_str)
            return final_data

        except Exception as e:
            logger.error(f"Final summary creation failed: {str(e)}")
            # fallback: simple aggregator
            return self._merge_chunk_summaries_locally(chunk_summaries)

    def _merge_chunk_summaries_locally(self, chunk_summaries: List[Dict]) -> Dict:
        """Fallback aggregator that merges chunk summaries into a final summary"""
        try:
            short_summaries = [c.get('short_summary','') for c in chunk_summaries if c.get('short_summary')]
            key_topics = []
            key_questions = []
            for c in chunk_summaries:
                key_topics.extend(c.get('key_topics', []))
                key_questions.extend(c.get('key_questions', []))

            # simple dedupe
            key_topics = list(dict.fromkeys(key_topics))[:10]
            key_questions = list(dict.fromkeys(key_questions))[:10]

            return {
                'conversation_summary': ' '.join(short_summaries)[:500],
                'overall_analysis': {
                    'key_topics': key_topics,
                    'key_findings': []
                },
                'call_summary': {
                    'short_summary': ' '.join(short_summaries)[:300],
                    'key_topics': key_topics,
                    'key_questions': key_questions
                },
                'key_highlights': [],
                'concerns': [],
                'recommended_next_steps': [],
                'candidate_questions': key_questions
            }

        except Exception as e:
            logger.error(f"Local merging failed: {str(e)}")
            return {
                'conversation_summary': '',
                'overall_analysis': {},
                'call_summary': {},
                'key_highlights': [],
                'concerns': [],
                'recommended_next_steps': [],
                'candidate_questions': []
            }
    
    def _transcribe_large_audio(self, audio_content: bytes) -> List[Dict]:
        """
        Transcribe large audio files by splitting into chunks with analysis
        
        Args:
            audio_content: Audio data in WAV format
        
        Returns:
            List of transcript segments with analysis
        """
        try:
            # For large files, split into smaller chunks
            # WAV format: 44-byte header + audio data
            # Split data into ~10MB chunks to avoid API limits
            chunk_size = 10 * 1024 * 1024  # 10MB chunks
            wav_header = audio_content[:44]  # Standard WAV header
            audio_data = audio_content[44:]  # Audio data after header
            
            all_segments = []
            chunk_summaries = []
            time_offset = 0.0
            chunk_num = 1
            
            # Process chunks
            for i in range(0, len(audio_data), chunk_size):
                chunk_data = audio_data[i:i + chunk_size]
                
                # Reconstruct WAV chunk with header
                chunk_bytes = wav_header + chunk_data
                
                chunk_size_mb = len(chunk_bytes) / (1024 * 1024)
                logger.info(f"Processing chunk {chunk_num}, size: {chunk_size_mb:.2f} MB")
                
                # Detect mime type
                mime_type = self._detect_mime_type(chunk_bytes)
                
                # Create audio part
                audio_part = types.Part.from_bytes(data=chunk_bytes, mime_type=mime_type)
                
                # Create advanced prompt
                prompt_text = self._get_analysis_prompt()
                prompt_part = types.Part(text=prompt_text)
                
                contents = [audio_part, prompt_part]
                gen_cfg = types.GenerateContentConfig()
                
                # Transcribe chunk with retry logic
                logger.info(f"Sending chunk {chunk_num} to Gemini API for analysis...")
                try:
                    response = self._retryable_generate_content(
                        model=self.model,
                        contents=contents,
                        config=gen_cfg
                    )
                except ClientError as ce:
                    logger.error(f"Gemini API client error on chunk {chunk_num}: {str(ce)}")
                    raise RuntimeError(
                        "Gemini transcription failed due to API key/authentication error while processing a chunk. "
                        "Ensure GOOGLE_API_KEY or GEMINI_API_KEY is set and valid in the worker environment. "
                        "Original error: " + str(ce)
                    ) from ce
                
                # Extract and parse response
                response_text = getattr(response, "text", "").strip()
                
                if response_text:
                    # Parse JSON response and get compact chunk data
                    chunk_obj = self._parse_analysis_response(response_text)

                    # If parse returned a chunk_obj, merge segments & collect chunk summaries
                    if isinstance(chunk_obj, dict):
                        # Adjust timestamps for segments
                        for segment in chunk_obj.get('segments', []):
                            segment['start_time'] += time_offset
                            segment['end_time'] += time_offset
                            all_segments.append(segment)

                        # Save chunk summaries for final summary stage
                        chunk_summaries.append({
                            'chunk_id': chunk_obj.get('chunk_id'),
                            'short_summary': chunk_obj.get('chunk_summary', {}).get('short_summary', ''),
                            'key_topics': chunk_obj.get('chunk_summary', {}).get('key_topics', []),
                            'key_questions': chunk_obj.get('chunk_summary', {}).get('key_questions', []),
                            'segments_preview': [s.get('text', '')[:100] for s in chunk_obj.get('segments', [])[:3]]
                        })
                    else:
                        # Fallback: chunk_obj is list of segments (old behaviour)
                        for segment in chunk_obj:
                            segment['start_time'] += time_offset
                            segment['end_time'] += time_offset
                            all_segments.append(segment)

                # Update time offset for next chunk
                # Assuming 16kHz mono, 2 bytes per sample: duration = bytes / (16000 * 2)
                chunk_duration_seconds = len(chunk_data) / (16000 * 2)
                time_offset += chunk_duration_seconds
                chunk_num += 1
            
            logger.info(f"Large audio transcription completed: {len(all_segments)} total segments")
            
            return {
                'segments': all_segments,
                'chunk_summaries': chunk_summaries
            }
            
        except Exception as e:
            logger.error(f"Large audio transcription failed: {str(e)}")
            raise


def transcribe_audio(audio_content: bytes) -> Dict:
    """
    Transcribe audio using Gemini API

    Args:
        audio_content: Audio data in WAV format (16kHz, mono)

    Returns:
        dict with keys: segments (list), chunk_summaries (list), final_summary (dict)
    """
    stt = GoogleSTT()
    return stt.transcribe(audio_content)
