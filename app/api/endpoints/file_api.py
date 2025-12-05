"""
File API Endpoints

This module contains API endpoints for file retrieval.

Author: [Supriyo Chowdhury]
Version: 1.0
Last Modified: [2024-12-19]
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from app.utils.file_storage import get_file_path
import logging
import os

logger = logging.getLogger("app_logger")

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{file_id}")
async def get_file(file_id: str):
    """
    Get file by file ID.
    
    Args:
        file_id (str): File ID
    
    Returns:
        FileResponse: The requested file
    """
    try:
        file_path = get_file_path(file_id)
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Determine media type based on file extension
        file_ext = os.path.splitext(file_path)[1].lower()
        media_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.html': 'text/html',
            '.svg': 'image/svg+xml'
        }
        media_type = media_types.get(file_ext, 'application/octet-stream')
        
        return FileResponse(
            file_path,
            media_type=media_type
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        logger.error(f"Error retrieving file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

