"""
Gemini Extractor Agent Module

This module defines an agent for extracting structured information from
resume data using Google's Gemini AI model.

Key components:
- Resume_Extractor_Agent: Main class for handling resume information extraction
- LLM initialization using Google's Gemini AI
- Logging for tracking the extraction process

Dependencies:
- langchain_google_genai for interacting with Google's Gemini AI
- logging for application logging
- app.core for settings configuration
- app.prompt_template for prompt templates
"""

import json
import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from fastapi import HTTPException

from app.core import settings
from app.prompt_templates import job_agent_template

logger = logging.getLogger("app_logger")


class Job_Agent:
    """
    A class for extracting structured information from resumes using AI.

    This class initializes the AI model and provides methods for parsing resume data.
    """

    def __init__(self) -> None:
        """Initialize the Resume Extractor Agent."""
        pass

    def initialize(self) -> None:
        """
        Initialize the LLM model with the specified configuration.
        
        Raises:
            ValueError: If LLM initialization fails
        """
        try:
            self.llm = ChatGoogleGenerativeAI(
                model=settings.GOOGLE_MODEL_NAME,
                verbose=False,
                temperature=0.1,
                google_api_key=settings.GOOGLE_API_KEY
            )
            logger.info(f"LLM initialized successfully: {settings.GOOGLE_MODEL_NAME}")
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}")
            raise ValueError("LLM Configuration failed")
    
    def extract_job_data(self, jd_text: str) -> dict:
        """
        Extract structured information from resume data.

        Args:
            jd_text: Job description text for context

        Returns:
            dict: Structured JSON containing extracted resume details

        Raises:
            HTTPException: If extraction fails
        """
        self.initialize()

        try:
            # Get the prompt template
            prompt = job_agent_template.get_template()
            
            # Prepare input data
            input_data = {
                "jd_text": jd_text
            }
            
            # Create chain and invoke LLM
            chain = prompt | self.llm
            logger.info("Invoking Gemini AI for job agent...")
            output = chain.invoke(input_data)
            
            logger.info(f"Gemini AI response received")
            
            # Parse the response
            result_text = output.content.strip()
            
            # Clean markdown code blocks if present
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            
            result_text = result_text.strip()
            
            # Parse JSON
            extracted_data = json.loads(result_text)
            logger.info("Job agent data extracted and parsed successfully")
            
            return extracted_data

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e}")
            logger.error(f"Response text (first 500 chars): {output.content[:500]}")
            raise HTTPException(status_code=500, detail="Failed to parse AI response as JSON")
        except Exception as e:
            logger.error(f"Job agent extraction error: {e}")
            raise HTTPException(status_code=500, detail=f"Agent failed to extract data: {str(e)}")


# Initialize the agent
job_agent = Job_Agent()