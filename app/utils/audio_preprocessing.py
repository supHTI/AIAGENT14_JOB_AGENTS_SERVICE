"""
Audio Preprocessing Utilities

This module provides utilities for audio preprocessing including:
- Format normalization (WAV, 16kHz, mono)
- Silence trimming
- Noise reduction
- Channel separation

Author: [Supriyo Chowdhury]
Version: 1.0
Last Modified: [2024-12-15]
"""

from pydub import AudioSegment
from pydub.silence import detect_nonsilent
import logging
import io
import tempfile
import os

logger = logging.getLogger("app_logger")


class AudioPreprocessor:
    """Audio preprocessing pipeline for call recordings"""
    
    def __init__(self):
        self.target_sample_rate = 16000
        self.target_channels = 1
        self.target_format = "wav"
    
    def load_audio(self, audio_content: bytes, filename: str) -> AudioSegment:
        """
        Load audio from bytes content
        
        Args:
            audio_content: Raw audio file bytes
            filename: Original filename (used to determine format)
        
        Returns:
            AudioSegment object
        """
        try:
            # Determine format from filename
            file_ext = os.path.splitext(filename)[1].lower().lstrip('.')
            
            # Load audio from bytes
            audio = AudioSegment.from_file(io.BytesIO(audio_content), format=file_ext)
            
            logger.info(
                f"Loaded audio: {filename} - "
                f"Duration: {len(audio)/1000:.2f}s, "
                f"Channels: {audio.channels}, "
                f"Sample Rate: {audio.frame_rate}Hz"
            )
            
            return audio
            
        except Exception as e:
            logger.error(f"Failed to load audio: {str(e)}")
            raise
    
    def normalize_format(self, audio: AudioSegment) -> AudioSegment:
        """
        Normalize audio to standard format (16kHz, mono, WAV)
        
        Args:
            audio: Input AudioSegment
        
        Returns:
            Normalized AudioSegment
        """
        try:
            # Convert to mono if stereo
            if audio.channels > 1:
                logger.info(f"Converting from {audio.channels} channels to mono")
                audio = audio.set_channels(self.target_channels)
            
            # Resample to target rate
            if audio.frame_rate != self.target_sample_rate:
                logger.info(f"Resampling from {audio.frame_rate}Hz to {self.target_sample_rate}Hz")
                audio = audio.set_frame_rate(self.target_sample_rate)
            
            # Normalize volume
            audio = audio.normalize()
            
            logger.info(
                f"Audio normalized: "
                f"{self.target_sample_rate}Hz, "
                f"{self.target_channels} channel(s)"
            )
            
            return audio
            
        except Exception as e:
            logger.error(f"Failed to normalize audio format: {str(e)}")
            raise
    
    def trim_silence(
        self,
        audio: AudioSegment,
        silence_thresh: int = -40,
        min_silence_len: int = 500,
        padding: int = 200
    ) -> AudioSegment:
        """
        Trim silence from the beginning and end of audio
        
        Args:
            audio: Input AudioSegment
            silence_thresh: Silence threshold in dBFS (default: -40)
            min_silence_len: Minimum silence length in ms (default: 500)
            padding: Padding to keep around non-silent parts in ms (default: 200)
        
        Returns:
            Trimmed AudioSegment
        """
        try:
            # Detect non-silent parts
            nonsilent_ranges = detect_nonsilent(
                audio,
                min_silence_len=min_silence_len,
                silence_thresh=silence_thresh,
                seek_step=1
            )
            
            if not nonsilent_ranges:
                logger.warning("No non-silent audio detected, returning original")
                return audio
            
            # Get first and last non-silent positions
            start_trim = max(0, nonsilent_ranges[0][0] - padding)
            end_trim = min(len(audio), nonsilent_ranges[-1][1] + padding)
            
            # Trim audio
            trimmed_audio = audio[start_trim:end_trim]
            
            trimmed_duration = (end_trim - start_trim) / 1000
            original_duration = len(audio) / 1000
            
            logger.info(
                f"Trimmed silence: "
                f"{original_duration:.2f}s -> {trimmed_duration:.2f}s "
                f"(removed {original_duration - trimmed_duration:.2f}s)"
            )
            
            return trimmed_audio
            
        except Exception as e:
            logger.error(f"Failed to trim silence: {str(e)}")
            return audio  # Return original on error
    
    def reduce_noise(self, audio: AudioSegment) -> AudioSegment:
        """
        Apply basic noise reduction (optional)
        
        Note: For advanced noise reduction, consider using noisereduce library
        This implementation applies basic high-pass filter
        
        Args:
            audio: Input AudioSegment
        
        Returns:
            Noise-reduced AudioSegment
        """
        try:
            # Apply high-pass filter to remove low-frequency noise
            # This is a simple approach; for better results use noisereduce
            audio = audio.high_pass_filter(200)
            
            logger.info("Applied basic noise reduction (high-pass filter)")
            
            return audio
            
        except Exception as e:
            logger.warning(f"Failed to apply noise reduction: {str(e)}")
            return audio  # Return original on error
    
    def export_to_wav(self, audio: AudioSegment) -> bytes:
        """
        Export audio to WAV format bytes
        
        Args:
            audio: Input AudioSegment
        
        Returns:
            WAV file as bytes
        """
        try:
            # Export to bytes
            buffer = io.BytesIO()
            audio.export(
                buffer,
                format=self.target_format,
                parameters=["-ac", "1", "-ar", str(self.target_sample_rate)]
            )
            buffer.seek(0)
            wav_bytes = buffer.read()
            
            logger.info(f"Exported audio to WAV: {len(wav_bytes)} bytes")
            
            return wav_bytes
            
        except Exception as e:
            logger.error(f"Failed to export audio: {str(e)}")
            raise
    
    def process(
        self,
        audio_content: bytes,
        filename: str,
        apply_noise_reduction: bool = False,
        trim_silence_enabled: bool = True
    ) -> bytes:
        """
        Complete preprocessing pipeline
        
        Args:
            audio_content: Raw audio file bytes
            filename: Original filename
            apply_noise_reduction: Whether to apply noise reduction
            trim_silence_enabled: Whether to trim silence
        
        Returns:
            Preprocessed audio as WAV bytes
        """
        try:
            logger.info(f"Starting audio preprocessing: {filename}")
            
            # Load audio
            audio = self.load_audio(audio_content, filename)
            
            # Normalize format (16kHz, mono)
            audio = self.normalize_format(audio)
            
            # Trim silence
            if trim_silence_enabled:
                audio = self.trim_silence(audio)
            
            # Apply noise reduction (optional)
            if apply_noise_reduction:
                audio = self.reduce_noise(audio)
            
            # Export to WAV
            wav_bytes = self.export_to_wav(audio)
            
            logger.info(f"Audio preprocessing completed: {filename}")
            
            return wav_bytes
            
        except Exception as e:
            logger.error(f"Audio preprocessing failed: {str(e)}")
            raise


# Convenience function
def preprocess_audio(
    audio_content: bytes,
    filename: str,
    apply_noise_reduction: bool = False,
    trim_silence_enabled: bool = True
) -> bytes:
    """
    Preprocess audio file
    
    Example:
        audio_bytes = preprocess_audio(
            audio_content=raw_audio,
            filename="call.mp3",
            apply_noise_reduction=True
        )
    
    Args:
        audio_content: Raw audio file bytes
        filename: Original filename
        apply_noise_reduction: Whether to apply noise reduction
        trim_silence_enabled: Whether to trim silence
    
    Returns:
        Preprocessed audio as WAV bytes (16kHz, mono)
    """
    preprocessor = AudioPreprocessor()
    return preprocessor.process(
        audio_content,
        filename,
        apply_noise_reduction,
        trim_silence_enabled
    )
