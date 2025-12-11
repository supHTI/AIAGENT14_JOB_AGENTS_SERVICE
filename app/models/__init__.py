"""
Models package for the Job Agent Service.

This package contains model configurations and integrations,
including Gemini AI model setup using Langchain.
"""

from app.models.gemini_model import GeminiModelConfig, configure_gemini_model
from app.models.job_agents import job_agent

__all__ = ["GeminiModelConfig", "configure_gemini_model", "job_agent"]

