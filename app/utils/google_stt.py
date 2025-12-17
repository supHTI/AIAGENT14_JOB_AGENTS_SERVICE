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

logger = logging.getLogger("app_logger")


class GoogleSTT:
    """Gemini Audio transcription service"""
    
    def __init__(self):
        """Initialize Gemini client"""
        try:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY not set in environment")
            
            self.client = gg.Client(api_key=api_key)
            self.model = "gemini-2.5-flash"
            logger.info(f"Initialized Gemini STT with model: {self.model}")
                
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {str(e)}")
            raise
    
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
            
            # Call Gemini API
            logger.info("Sending audio to Gemini API...")
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=gen_cfg
            )
            
            # Extract text from response
            transcript_text = getattr(response, "text", "").strip()
            
            if not transcript_text:
                logger.warning("Empty transcript received from Gemini")
                return []
            
            logger.info(f"Transcription completed: {len(transcript_text)} characters")
            
            # Convert to segment format
            segments = self._text_to_segments(transcript_text)
            
            return segments
            
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
        from pydub import AudioSegment
        
        try:
            # Load audio
            audio = AudioSegment.from_wav(io.BytesIO(audio_content))
            
            # Calculate chunk duration (aim for ~10MB chunks)
            chunk_duration_ms = 5 * 60 * 1000  # 5 minutes per chunk
            
            all_segments = []
            time_offset = 0.0
            
            # Split and process chunks
            for i in range(0, len(audio), chunk_duration_ms):
                chunk = audio[i:i + chunk_duration_ms]
                
                # Export chunk to WAV bytes
                chunk_buffer = io.BytesIO()
                chunk.export(chunk_buffer, format="wav")
                chunk_bytes = chunk_buffer.getvalue()
                
                chunk_size_mb = len(chunk_bytes) / (1024 * 1024)
                logger.info(f"Processing chunk {i//chunk_duration_ms + 1}, size: {chunk_size_mb:.2f} MB")
                
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
                
                # Transcribe chunk
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=gen_cfg
                )
                
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
                time_offset += len(chunk) / 1000.0
            
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
