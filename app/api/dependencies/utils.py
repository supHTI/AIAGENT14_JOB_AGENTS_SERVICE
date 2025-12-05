"""
File Handler Service

This service handles file uploads and text extraction using external API.
"""

import time
import requests
from fastapi import HTTPException
from app.core.config import settings
import logging

logger = logging.getLogger("app_logger")

class FileHandler:
    
    @staticmethod
    def extract_text(file_bytes: bytes, filename: str, perform_ocr: bool) -> str:
        """
        Extract text from file using file handling API.

        Args:
            file_bytes: File content in bytes
            filename: Name of the uploaded file
            perform_ocr: Whether to perform OCR (for images)

        Returns:
            str: Extracted raw text (langchain_doc format)
        """
        start_time = time.time()

        try:
            files = {"file": (filename, file_bytes)}
            data = {
                "perform_ocr": "true" if perform_ocr else "false",
                "image_desc": "false"
            }

            logger.info(f"Calling file handler API for: {filename}, OCR: {perform_ocr}")
            
            response = requests.post(
                settings.FILE_HANDLING_API_URL,
                files=files,
                data=data,
                timeout=120
            )
            response.raise_for_status()
            result = response.json()

            # Extract raw_text or langchain_doc format
            raw_text = (
                result.get("raw_text") or
                result.get("text") or
                result.get("content") or
                result.get("langchain_doc") or
                ""
            ).strip()

            if not raw_text:
                raise ValueError("No text extracted from file")

            processing_time = int((time.time() - start_time) * 1000)
            logger.info(f"Text extracted successfully in {processing_time}ms, Length: {len(raw_text)} chars")

            return raw_text

        except requests.RequestException as e:
            logger.error(f"File handler API error: {e}")
            raise HTTPException(status_code=502, detail="File processing service unavailable")
        except Exception as e:
            logger.error(f"File extraction failed: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to extract text: {str(e)}")
