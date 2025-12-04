"""
Models package for the Job Agent Service.

This package contains model configurations and integrations,
including Gemini AI model setup using Langchain.
"""

from app.models.gemini_model import GeminiModelConfig, configure_gemini_model

__all__ = ["GeminiModelConfig", "configure_gemini_model"]

