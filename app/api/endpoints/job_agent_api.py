"""
Job Agent API Endpoints

This module defines the REST API endpoints for the job agent service.
"""

from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from typing import Optional
from app.models.job_agents import resume_extractor_agent
from app.api.dependencies.utils import FileHandler
from app.services.gemini_extractor_agent import resume_extractor_agent
from app.core.config import settings
import logging

logger = logging.getLogger("app_logger")

router = APIRouter(tags=["Job Agent"])

# Image file extensions
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.heic', '.svg'}

def is_image_file(filename: str) -> bool:
    """Check if uploaded file is an image based on extension."""
    if not filename:
        return False
    return any(filename.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)


@router.post("/job_agent", response_model=JobAgentResponse)
async def job_agent(
    jd_text: str = Form(..., description="Job Description text (mandatory)"),
    file: UploadFile = File(..., description="Resume file upload (mandatory)"),
    image_train: Optional[bool] = Form(None, description="Enable OCR for images (auto-detected)")
):
    """
    Job Agent Endpoint - Extract structured information from resume.
    
    **Logic Flow:**
    1. If file is uploaded -> send to file handler API to extract raw_text/langchain_doc
    2. If file is image -> automatically set image_train=True
    3. If image_train=True -> file handler performs OCR
    4. Pass extracted text + jd_text to Gemini AI
    5. Gemini extracts structured fields and returns JSON
    
    Args:
        jd_text: Job description text (required)
        file: Resume file (PDF/DOC/DOCX/Image) (required)
        image_train: Enable OCR (optional, auto-true for images)
    
    Returns:
        JobAgentResponse with extracted structured data
    """
    
    # Validate inputs
    if not jd_text or not jd_text.strip():
        raise HTTPException(
            status_code=400,
            detail="jd_text is required and cannot be empty"
        )
    
    if not file or not file.filename:
        raise HTTPException(
            status_code=400,
            detail="file is required"
        )
    
    try:
        # Read file content
        file_content = await file.read()
        if not file_content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        
        # Check if file is an image - auto-set image_train to True
        is_image = is_image_file(file.filename)
        if is_image:
            image_train = True
            logger.info(f"Image file detected: {file.filename}. Auto-setting image_train=True")
        elif image_train is None:
            image_train = False
        
        logger.info(f"Processing file: {file.filename}, image_train={image_train}")
        
        # Step 1: Extract text from file using file handler API
        logger.info("Step 1: Extracting text from file...")
        extracted_text = FileHandler.extract_text(
            file_bytes=file_content,
            filename=file.filename,
            perform_ocr=image_train
        )
        
        # Step 2: Pass extracted text to Gemini for structured extraction
        logger.info("Step 2: Processing with Gemini AI...")
        structured_data = resume_extractor_agent.extract_resume_data(
            resume_data=extracted_text,
            jd_text=jd_text.strip()
        )
        
        # Return response
        return JobAgentResponse(
            success=True,
            data=structured_data,
            metadata={
                "filename": file.filename,
                "file_type": "image" if is_image else "document",
                "image_train": image_train,
                "ocr_performed": image_train,
                "jd_provided": True,
                "environment": settings.ENVIRONMENT,
                "ai_model": settings.GEMINI_MODEL_NAME
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Job agent processing failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Processing failed: {str(e)}"
        )
