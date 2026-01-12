"""
File Storage Utility Module

This module handles file storage operations including saving files,
generating unique file names, and retrieving file paths.

Author: [Supriyo Chowdhury]
Version: 1.0
Last Modified: [2024-12-19]
"""

import os
import uuid
from datetime import datetime
from pathlib import Path
from fastapi import UploadFile
from PIL import Image
import logging
from app.core import settings

logger = logging.getLogger("app_logger")

def ensure_directory_exists(directory_path: str):
    """
    Ensure that a directory exists, create if it doesn't.
    
    Args:
        directory_path (str): Path to the directory
    """
    Path(directory_path).mkdir(parents=True, exist_ok=True)

def generate_file_id(job_id: int, file_type: str = "file") -> str:
    """
    Generate a unique file ID.
    
    Args:
        job_id (int): Job ID
        file_type (str): Type of file (logo, image, etc.)
    
    Returns:
        str: Unique file ID in format: uuid_job_id_datetime
    """
    unique_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_id = f"{unique_id}_{job_id}_{timestamp}"
    return file_id

def save_uploaded_file(file: UploadFile, job_id: int, file_type: str = "image") -> tuple[str, str]:
    """
    Save an uploaded file to the storage directory.
    
    Args:
        file (UploadFile): Uploaded file object
        job_id (int): Job ID
        file_type (str): Type of file (logo, image, etc.)
    
    Returns:
        tuple: (file_id, file_path)
    """
    try:
        # Ensure directory exists
        ensure_directory_exists(settings.IMAGE_PATH)
        
        # Generate file ID
        file_id = generate_file_id(job_id, file_type)
        
        # Get file extension
        file_extension = os.path.splitext(file.filename)[1] if file.filename else ".jpg"
        
        # Create full file path
        file_path = os.path.join(settings.IMAGE_PATH, f"{file_id}{file_extension}")
        
        # Save file
        with open(file_path, "wb") as buffer:
            content = file.file.read()
            buffer.write(content)
        
        logger.info(f"File saved successfully: {file_path}")
        return file_id, file_path
        
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        raise

def validate_image_file(file: UploadFile, max_size_mb: int = 5, max_width: int = 5000, max_height: int = 5000) -> tuple[bool, str]:
    """
    Validate an image file.
    
    Args:
        file (UploadFile): Uploaded file object
        max_size_mb (int): Maximum file size in MB
        max_width (int): Maximum image width
        max_height (int): Maximum image height
    
    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        # Check file size
        file.file.seek(0, os.SEEK_END)
        file_size = file.file.tell()
        file.file.seek(0)
        
        max_size_bytes = max_size_mb * 1024 * 1024
        if file_size > max_size_bytes:
            return False, f"File size exceeds {max_size_mb}MB limit"
        
        # Check if it's an image
        try:
            image = Image.open(file.file)
            width, height = image.size
            
            if width > max_width or height > max_height:
                return False, f"Image dimensions exceed {max_width}x{max_height} limit"
            
            # Reset file pointer
            file.file.seek(0)
            return True, ""
            
        except Exception as e:
            return False, f"Invalid image file: {str(e)}"
            
    except Exception as e:
        return False, f"Error validating file: {str(e)}"

def get_file_path(file_id: str) -> str:
    """
    Get file path from file ID.
    
    Args:
        file_id (str): File ID
    
    Returns:
        str: Full file path
    """
    # Search for file with this ID in the directory
    if not os.path.exists(settings.IMAGE_PATH):
        raise FileNotFoundError(f"Storage directory does not exist: {settings.IMAGE_PATH}")
    
    for filename in os.listdir(settings.IMAGE_PATH):
        if filename.startswith(file_id):
            return os.path.join(settings.IMAGE_PATH, filename)
    
    raise FileNotFoundError(f"File with ID {file_id} not found")

def get_file_url(file_id: str) -> str:
    """
    Get file URL from file ID.
    
    Args:
        file_id (str): File ID
    
    Returns:
        str: Full file URL
    """
    return f"{settings.BASE_URL}/files/{file_id}"

