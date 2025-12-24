"""
Gemini Speech-to-Text Integration
"""

from google.genai import types
from google import genai as gg
import logging
import os
from typing import List, Dict
import io
import re
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
        Transcribe audio using Gemini API
        
        Args:
            audio_content: Audio data in WAV format (16kHz, mono)
        
        Returns:
            List of transcript segments with timestamps
        """
        try:
            logger.info(f"Starting Gemini transcription - Audio size: {len(audio_content) / (1024*1024):.2f} MB")
            
            # Check file size - split if too large (>15MB)
            if len(audio_content) > 15 * 1024 * 1024:
                logger.warning(f"Audio file is large, chunking for processing...")
                return self._transcribe_large_audio(audio_content)
            
            # Detect mime type from audio content
            mime_type = self._detect_mime_type(audio_content)
            logger.info(f"Detected mime type: {mime_type}")
            
            # Create audio part
            audio_part = types.Part.from_bytes(data=audio_content, mime_type=mime_type)
            
            # Create prompt
            prompt_text = (
                "Transcribe this audio to plain English text. "
                "Only output the transcribed text, nothing else. "
                "Be accurate and include all spoken words."
            )
            prompt_part = types.Part(text=prompt_text)
            
            contents = [audio_part, prompt_part]
            gen_cfg = types.GenerateContentConfig()
            
            # Call Gemini API with retry logic
            logger.info("Sending audio to Gemini API...")
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
            
            # Extract text from response
            transcript_text = getattr(response, "text", "").strip()
            
            if not transcript_text:
                logger.warning("Empty transcript received from Gemini")
                return []
            
            logger.info(f"Transcription completed: {len(transcript_text)} characters")
            
            # Convert to segment format
            segments = self._text_to_segments(transcript_text)
            
            return segments
            
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
    
    def _text_to_segments(self, text: str) -> List[Dict]:
        """Convert plain text to segment format"""
        # Split text into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        segments = []
        current_time = 0.0
        
        for sentence in sentences:
            if not sentence.strip():
                continue
            
            # Estimate duration based on word count (rough estimate: ~2 words per second)
            words = sentence.split()
            duration = max(1.0, len(words) * 0.5)
            
            segment = {
                "speaker": "Speaker 1",
                "start_time": current_time,
                "end_time": current_time + duration,
                "text": sentence.strip()
            }
            
            segments.append(segment)
            current_time += duration
        
        logger.info(f"Created {len(segments)} segments from transcript")
        return segments
    
    def _transcribe_large_audio(self, audio_content: bytes) -> List[Dict]:
        """
        Transcribe large audio files by splitting into chunks
        
        Args:
            audio_content: Audio data in WAV format
        
        Returns:
            List of transcript segments
        """
        try:
            # For large files, split into smaller chunks
            # WAV format: 44-byte header + audio data
            # Split data into ~10MB chunks to avoid API limits
            chunk_size = 10 * 1024 * 1024  # 10MB chunks
            wav_header = audio_content[:44]  # Standard WAV header
            audio_data = audio_content[44:]  # Audio data after header
            
            all_segments = []
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
                
                # Create prompt
                prompt_text = (
                    "Transcribe this audio to plain English text. "
                    "Only output the transcribed text, nothing else. "
                    "Be accurate and include all spoken words."
                )
                prompt_part = types.Part(text=prompt_text)
                
                contents = [audio_part, prompt_part]
                gen_cfg = types.GenerateContentConfig()
                
                # Transcribe chunk with retry logic
                logger.info(f"Sending chunk {chunk_num} to Gemini API...")
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
                
                # Extract text
                transcript_text = getattr(response, "text", "").strip()
                
                if transcript_text:
                    # Convert to segments and adjust timestamps
                    chunk_segments = self._text_to_segments(transcript_text)
                    
                    for segment in chunk_segments:
                        segment['start_time'] += time_offset
                        segment['end_time'] += time_offset
                    
                    all_segments.extend(chunk_segments)
                
                # Update time offset for next chunk
                # Assuming 16kHz mono, 2 bytes per sample: duration = bytes / (16000 * 2)
                chunk_duration_seconds = len(chunk_data) / (16000 * 2)
                time_offset += chunk_duration_seconds
                chunk_num += 1
            
            logger.info(f"Large audio transcription completed: {len(all_segments)} total segments")
            
            return all_segments
            
        except Exception as e:
            logger.error(f"Large audio transcription failed: {str(e)}")
            raise
    
    # Removed old Google STT methods - no longer needed


def transcribe_audio(audio_content: bytes) -> List[Dict]:
    """
    Transcribe audio using Gemini API
    
    Args:
        audio_content: Audio data in WAV format (16kHz, mono)
    
    Returns:
        List of transcript segments with timestamps
    """
    stt = GoogleSTT()
    return stt.transcribe(audio_content)
