"""
Transcript Chunking Strategy Module

This module implements intelligent chunking strategies for transcript processing:
- Token-aware chunking for LLM context limits
- Context-preserving segmentation
- Speaker-aware chunking
- Domain-specific extraction

Author: [Supriyo Chowdhury]
Version: 1.0
Last Modified: [2024-12-15]
"""

import logging
from typing import List, Dict, Optional
import tiktoken

logger = logging.getLogger("app_logger")


class TranscriptChunker:
    """Intelligent transcript chunking for LLM processing"""
    
    def __init__(
        self,
        max_tokens: int = 4000,
        overlap_tokens: int = 200,
        encoding_name: str = "cl100k_base"
    ):
        """
        Initialize transcript chunker
        
        Args:
            max_tokens: Maximum tokens per chunk
            overlap_tokens: Number of tokens to overlap between chunks
            encoding_name: Tokenizer encoding name (cl100k_base for GPT-4)
        """
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        
        try:
            self.encoding = tiktoken.get_encoding(encoding_name)
        except Exception as e:
            logger.warning(f"Failed to load tiktoken encoding: {str(e)}, using approximate method")
            self.encoding = None
    
    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text
        
        Args:
            text: Input text
        
        Returns:
            Token count
        """
        try:
            if self.encoding:
                return len(self.encoding.encode(text))
            else:
                # Approximate: 1 token ≈ 4 characters
                return len(text) // 4
        except Exception as e:
            logger.warning(f"Token counting failed: {str(e)}")
            return len(text) // 4
    
    def chunk_by_tokens(
        self,
        segments: List[Dict],
        include_metadata: bool = True
    ) -> List[Dict]:
        """
        Chunk transcript segments based on token limits
        
        Args:
            segments: Normalized transcript segments
            include_metadata: Include metadata in each chunk
        
        Returns:
            List of chunks with metadata
            
        Example output:
            [
                {
                    "chunk_id": 1,
                    "text": "...",
                    "tokens": 3500,
                    "segments": [...],
                    "start_time": 0.0,
                    "end_time": 120.5,
                    "speakers": ["candidate", "interviewer"]
                },
                ...
            ]
        """
        if not segments:
            return []
        
        try:
            logger.info(f"Starting token-based chunking: {len(segments)} segments")
            
            chunks = []
            current_chunk = {
                "chunk_id": 1,
                "text": "",
                "tokens": 0,
                "segments": [],
                "speakers": set()
            }
            
            for segment in segments:
                segment_text = segment.get('text', '')
                segment_tokens = self.count_tokens(segment_text)
                
                # Check if adding this segment exceeds limit
                if current_chunk["tokens"] + segment_tokens > self.max_tokens and current_chunk["segments"]:
                    # Save current chunk
                    self._finalize_chunk(current_chunk, include_metadata)
                    chunks.append(current_chunk)
                    
                    # Start new chunk with overlap
                    overlap_segments = self._get_overlap_segments(
                        current_chunk["segments"],
                        self.overlap_tokens
                    )
                    
                    current_chunk = {
                        "chunk_id": len(chunks) + 1,
                        "text": " ".join(s.get('text', '') for s in overlap_segments),
                        "tokens": sum(self.count_tokens(s.get('text', '')) for s in overlap_segments),
                        "segments": overlap_segments,
                        "speakers": {s.get('speaker') for s in overlap_segments}
                    }
                
                # Add segment to current chunk
                current_chunk["segments"].append(segment)
                current_chunk["text"] += " " + segment_text if current_chunk["text"] else segment_text
                current_chunk["tokens"] += segment_tokens
                current_chunk["speakers"].add(segment.get('speaker'))
            
            # Add final chunk
            if current_chunk["segments"]:
                self._finalize_chunk(current_chunk, include_metadata)
                chunks.append(current_chunk)
            
            logger.info(f"Created {len(chunks)} chunks from {len(segments)} segments")
            
            return chunks
            
        except Exception as e:
            logger.error(f"Chunking failed: {str(e)}")
            raise
    
    def _finalize_chunk(self, chunk: Dict, include_metadata: bool):
        """Add metadata to chunk"""
        if include_metadata and "segments" in chunk and chunk["segments"]:
            chunk["start_time"] = chunk["segments"][0].get('start_time', 0)
            chunk["end_time"] = chunk["segments"][-1].get('end_time', 0)
            chunk["speakers"] = list(chunk.get("speakers", set()))
            chunk["segment_count"] = len(chunk["segments"])
    
    def _get_overlap_segments(
        self,
        segments: List[Dict],
        overlap_tokens: int
    ) -> List[Dict]:
        """
        Get segments for overlap between chunks
        
        Args:
            segments: Previous chunk's segments
            overlap_tokens: Number of tokens to overlap
        
        Returns:
            List of segments for overlap
        """
        if not segments:
            return []
        
        overlap_segments = []
        current_tokens = 0
        
        # Work backwards from end of segments
        for segment in reversed(segments):
            segment_tokens = self.count_tokens(segment.get('text', ''))
            
            if current_tokens + segment_tokens > overlap_tokens:
                break
            
            overlap_segments.insert(0, segment)
            current_tokens += segment_tokens
        
        return overlap_segments
    
    def get_chunk_summary(self, chunks: List[Dict]) -> Dict:
        """
        Get summary statistics for chunks
        
        Args:
            chunks: List of chunks
        
        Returns:
            Summary statistics
        """
        if not chunks:
            return {
                "total_chunks": 0,
                "total_tokens": 0,
                "avg_tokens_per_chunk": 0,
                "min_tokens": 0,
                "max_tokens": 0
            }
        
        token_counts = [chunk.get('tokens', 0) for chunk in chunks]
        
        return {
            "total_chunks": len(chunks),
            "total_tokens": sum(token_counts),
            "avg_tokens_per_chunk": sum(token_counts) // len(token_counts),
            "min_tokens": min(token_counts),
            "max_tokens": max(token_counts),
            "chunk_details": [
                {
                    "chunk_id": chunk.get('chunk_id'),
                    "tokens": chunk.get('tokens'),
                    "speakers": chunk.get('speakers', []),
                    "duration": chunk.get('end_time', 0) - chunk.get('start_time', 0)
                }
                for chunk in chunks
            ]
        }


# Convenience functions
def chunk_transcript(
    segments: List[Dict],
    strategy: str = "tokens",
    max_tokens: int = 4000,
    overlap_tokens: int = 200
) -> Dict:
    """
    Chunk transcript using token-based strategy
    
    Example:
        result = chunk_transcript(
            segments=normalized_segments,
            max_tokens=4000,
            overlap_tokens=200
        )
        chunks = result['chunks']
        summary = result['summary']
    
    Args:
        segments: Normalized transcript segments
        strategy: Only 'tokens' supported (kept for compatibility)
        max_tokens: Maximum tokens per chunk
        overlap_tokens: Number of tokens to overlap between chunks
    
    Returns:
        Dictionary with chunks and summary
    """
    chunker = TranscriptChunker(max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    chunks = chunker.chunk_by_tokens(segments)
    summary = chunker.get_chunk_summary(chunks)
    
    return {
        "chunks": chunks,
        "summary": summary,
        "strategy": strategy
    }
