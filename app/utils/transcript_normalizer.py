"""
Transcript Normalization Module

This module provides utilities for cleaning and normalizing transcripts:
- Merge overlapping segments
- Normalize numbers ("five" → 5)
- Remove fillers ("uh", "umm")
- Standardize job terms
- Format timestamps

Author: [Supriyo Chowdhury]
Version: 1.0
Last Modified: [2024-12-15]
"""

import re
import logging
from typing import List, Dict
from datetime import timedelta

logger = logging.getLogger("app_logger")


class TranscriptNormalizer:
    """Transcript normalization and cleaning"""
    
    # Filler words to remove
    FILLER_WORDS = {
        'uh', 'um', 'umm', 'uhh', 'err', 'ah', 'ahh',
        'like', 'you know', 'i mean', 'basically', 'actually',
        'sort of', 'kind of'
    }
    
    # Number word mappings
    NUMBER_WORDS = {
        'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
        'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
        'ten': '10', 'eleven': '11', 'twelve': '12', 'thirteen': '13',
        'fourteen': '14', 'fifteen': '15', 'sixteen': '16', 'seventeen': '17',
        'eighteen': '18', 'nineteen': '19', 'twenty': '20', 'thirty': '30',
        'forty': '40', 'fifty': '50', 'sixty': '60', 'seventy': '70',
        'eighty': '80', 'ninety': '90', 'hundred': '100', 'thousand': '1000'
    }
    
    # Job/tech term standardization
    TECH_TERMS = {
        'python': 'Python',
        'javascript': 'JavaScript',
        'java script': 'JavaScript',
        'typescript': 'TypeScript',
        'react': 'React',
        'react js': 'React',
        'angular': 'Angular',
        'vue': 'Vue',
        'node': 'Node.js',
        'node js': 'Node.js',
        'nodejs': 'Node.js',
        'django': 'Django',
        'flask': 'Flask',
        'fastapi': 'FastAPI',
        'fast api': 'FastAPI',
        'sql': 'SQL',
        'mysql': 'MySQL',
        'postgresql': 'PostgreSQL',
        'postgres': 'PostgreSQL',
        'mongodb': 'MongoDB',
        'mongo db': 'MongoDB',
        'redis': 'Redis',
        'docker': 'Docker',
        'kubernetes': 'Kubernetes',
        'k8s': 'Kubernetes',
        'aws': 'AWS',
        'azure': 'Azure',
        'gcp': 'GCP',
        'google cloud': 'GCP',
        'machine learning': 'Machine Learning',
        'ml': 'Machine Learning',
        'artificial intelligence': 'AI',
        'deep learning': 'Deep Learning',
        'data science': 'Data Science',
        'devops': 'DevOps',
        'cicd': 'CI/CD',
        'ci cd': 'CI/CD',
        'api': 'API',
        'rest api': 'REST API',
        'restful': 'RESTful',
        'graphql': 'GraphQL',
        'git': 'Git',
        'github': 'GitHub',
        'gitlab': 'GitLab',
    }
    
    def __init__(self):
        pass
    
    def merge_segments(
        self,
        segments: List[Dict],
        gap_threshold: float = 1.0
    ) -> List[Dict]:
        """
        Merge segments from the same speaker if they're close together
        
        Args:
            segments: List of transcript segments
            gap_threshold: Maximum gap (seconds) to merge segments
        
        Returns:
            Merged segments
        """
        if not segments:
            return []
        
        try:
            merged = []
            current = segments[0].copy()
            
            for segment in segments[1:]:
                # Check if same speaker and gap is small
                same_speaker = current.get('speaker') == segment.get('speaker')
                gap = segment.get('start_time', 0) - current.get('end_time', 0)
                
                if same_speaker and gap <= gap_threshold:
                    # Merge with current segment
                    current['end_time'] = segment.get('end_time', current['end_time'])
                    current['text'] = current.get('text', '') + ' ' + segment.get('text', '')
                else:
                    # Save current and start new segment
                    merged.append(current)
                    current = segment.copy()
            
            # Add final segment
            merged.append(current)
            
            logger.info(f"Merged segments: {len(segments)} → {len(merged)}")
            
            return merged
            
        except Exception as e:
            logger.error(f"Failed to merge segments: {str(e)}")
            return segments
    
    def normalize_numbers(self, text: str) -> str:
        """
        Convert number words to digits
        
        Args:
            text: Input text
        
        Returns:
            Text with normalized numbers
        """
        try:
            words = text.split()
            normalized_words = []
            
            i = 0
            while i < len(words):
                word = words[i].lower().strip('.,!?')
                
                # Check for number words
                if word in self.NUMBER_WORDS:
                    # Handle compound numbers (e.g., "twenty five")
                    if i + 1 < len(words):
                        next_word = words[i + 1].lower().strip('.,!?')
                        if next_word in self.NUMBER_WORDS:
                            # Compound number
                            num1 = int(self.NUMBER_WORDS[word])
                            num2 = int(self.NUMBER_WORDS[next_word])
                            if num1 >= 20 and num2 < 10:
                                normalized_words.append(str(num1 + num2))
                                i += 2
                                continue
                    
                    # Single number word
                    normalized_words.append(self.NUMBER_WORDS[word])
                    i += 1
                else:
                    normalized_words.append(words[i])
                    i += 1
            
            return ' '.join(normalized_words)
            
        except Exception as e:
            logger.error(f"Failed to normalize numbers: {str(e)}")
            return text
    
    def remove_fillers(self, text: str) -> str:
        """
        Remove filler words from text
        
        Args:
            text: Input text
        
        Returns:
            Text without filler words
        """
        try:
            # Create pattern for filler words
            pattern = r'\b(' + '|'.join(re.escape(word) for word in self.FILLER_WORDS) + r')\b'
            
            # Remove fillers (case insensitive)
            cleaned = re.sub(pattern, '', text, flags=re.IGNORECASE)
            
            # Clean up extra spaces
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            
            return cleaned
            
        except Exception as e:
            logger.error(f"Failed to remove fillers: {str(e)}")
            return text
    
    def standardize_terms(self, text: str) -> str:
        """
        Standardize technical and job-related terms
        
        Args:
            text: Input text
        
        Returns:
            Text with standardized terms
        """
        try:
            result = text
            
            # Sort by length (longest first) to handle multi-word terms
            sorted_terms = sorted(self.TECH_TERMS.items(), key=lambda x: len(x[0]), reverse=True)
            
            for term, standard in sorted_terms:
                # Use word boundaries for exact matching
                pattern = r'\b' + re.escape(term) + r'\b'
                result = re.sub(pattern, standard, result, flags=re.IGNORECASE)
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to standardize terms: {str(e)}")
            return text
    
    def format_timestamp(self, seconds: float) -> str:
        """
        Format seconds to HH:MM:SS or MM:SS
        
        Args:
            seconds: Time in seconds
        
        Returns:
            Formatted timestamp string
        """
        try:
            td = timedelta(seconds=seconds)
            total_seconds = int(td.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            secs = total_seconds % 60
            
            if hours > 0:
                return f"{hours:02d}:{minutes:02d}:{secs:02d}"
            else:
                return f"{minutes:02d}:{secs:02d}"
            
        except Exception as e:
            logger.error(f"Failed to format timestamp: {str(e)}")
            return "00:00"
    
    def clean_text(self, text: str) -> str:
        """
        Apply all text cleaning operations
        
        Args:
            text: Input text
        
        Returns:
            Cleaned text
        """
        try:
            # Remove fillers
            text = self.remove_fillers(text)
            
            # Normalize numbers
            text = self.normalize_numbers(text)
            
            # Standardize terms
            text = self.standardize_terms(text)
            
            # Clean up punctuation and spacing
            text = re.sub(r'\s+([.,!?])', r'\1', text)  # Remove space before punctuation
            text = re.sub(r'\s+', ' ', text).strip()  # Normalize spaces
            
            # Capitalize first letter
            if text:
                text = text[0].upper() + text[1:]
            
            return text
            
        except Exception as e:
            logger.error(f"Failed to clean text: {str(e)}")
            return text
    
    def normalize(self, segments: List[Dict]) -> List[Dict]:
        """
        Complete normalization pipeline
        
        Args:
            segments: Raw transcript segments
        
        Returns:
            Normalized transcript segments
            
        Output format:
            [
                {
                    "speaker": "candidate",
                    "timestamp": "00:01:24",
                    "text": "I have 5 years of experience in Python and Django"
                },
                ...
            ]
        """
        try:
            logger.info(f"Starting transcript normalization: {len(segments)} segments")
            
            # Merge close segments
            merged = self.merge_segments(segments)
            
            # Clean and normalize each segment
            normalized = []
            for segment in merged:
                # Clean text
                cleaned_text = self.clean_text(segment.get('text', ''))
                
                # Skip empty segments
                if not cleaned_text.strip():
                    continue
                
                # Format timestamp
                start_time = segment.get('start_time', 0)
                timestamp = self.format_timestamp(start_time)
                
                # Map speaker to role (candidate/interviewer)
                speaker = segment.get('speaker', 'Speaker 1')
                speaker_label = self._map_speaker_to_role(speaker)
                
                normalized_segment = {
                    'speaker': speaker_label,
                    'timestamp': timestamp,
                    'text': cleaned_text,
                    'start_time': start_time,
                    'end_time': segment.get('end_time', start_time)
                }
                
                normalized.append(normalized_segment)
            
            logger.info(f"Normalization completed: {len(normalized)} segments")
            
            return normalized
            
        except Exception as e:
            logger.error(f"Transcript normalization failed: {str(e)}")
            raise
    
    def _map_speaker_to_role(self, speaker: str) -> str:
        """
        Map speaker labels to roles (candidate/interviewer)
        
        Assumes Speaker 1 is candidate, Speaker 2 is interviewer
        
        Args:
            speaker: Speaker label (e.g., "Speaker 1")
        
        Returns:
            Role label ("candidate" or "interviewer")
        """
        if 'speaker 1' in speaker.lower():
            return 'candidate'
        elif 'speaker 2' in speaker.lower():
            return 'interviewer'
        else:
            # Default to candidate for unknown speakers
            return 'candidate'
    
    def get_statistics(self, segments: List[Dict]) -> Dict:
        """
        Calculate transcript statistics
        
        Args:
            segments: Normalized transcript segments
        
        Returns:
            Statistics dictionary
        """
        try:
            if not segments:
                return {
                    'total_segments': 0,
                    'total_duration': 0,
                    'total_words': 0,
                    'speaker_breakdown': {}
                }
            
            # Calculate statistics
            total_words = sum(len(seg.get('text', '').split()) for seg in segments)
            total_duration = segments[-1].get('end_time', 0)
            
            # Speaker breakdown
            speaker_stats = {}
            for segment in segments:
                speaker = segment.get('speaker', 'unknown')
                if speaker not in speaker_stats:
                    speaker_stats[speaker] = {
                        'segments': 0,
                        'words': 0,
                        'duration': 0
                    }
                
                speaker_stats[speaker]['segments'] += 1
                speaker_stats[speaker]['words'] += len(segment.get('text', '').split())
                speaker_stats[speaker]['duration'] += (
                    segment.get('end_time', 0) - segment.get('start_time', 0)
                )
            
            stats = {
                'total_segments': len(segments),
                'total_duration': round(total_duration, 2),
                'total_words': total_words,
                'speaker_breakdown': speaker_stats
            }
            
            logger.info(f"Transcript statistics: {stats}")
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to calculate statistics: {str(e)}")
            return {}


# Convenience function
def normalize_transcript(segments: List[Dict]) -> Dict:
    """
    Normalize transcript segments
    
    Example:
        result = normalize_transcript(raw_segments)
        normalized_segments = result['segments']
        stats = result['statistics']
    
    Args:
        segments: Raw transcript segments from Google STT
    
    Returns:
        Dictionary with normalized segments and statistics
    """
    normalizer = TranscriptNormalizer()
    normalized = normalizer.normalize(segments)
    stats = normalizer.get_statistics(normalized)
    
    return {
        'segments': normalized,
        'statistics': stats
    }
