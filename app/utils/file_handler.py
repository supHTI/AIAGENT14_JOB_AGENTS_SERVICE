"""
File Handler Service

This service handles file uploads and text extraction using external API.
"""

import time
import requests
import base64
from fastapi import HTTPException
from app.core import settings
import logging

logger = logging.getLogger("app_logger")

class FileHandler:
    
    @staticmethod
    def extract_text(file_content_b64: str, filename: str, perform_ocr: bool, task_id: str) -> str:
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
            # Local import to avoid circular dependency during module import
            from app.api.dependencies.progress import report_progress

            payload = {
                "file": file_content_b64,
                "base64": True,
                "perform_ocr": perform_ocr,
                "image_desc": False
            }
            # Optionally include filename if the API supports it
            payload["filename"] = filename

            logger.info(f"Calling file handler API for: {filename}, OCR: {perform_ocr} (base64 mode)")
            report_progress(task_id, "PROGRESS", 50, "Extracting file data")
            
            response = requests.post(
                settings.FILE_HANDLING_API_KEY,
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            result = response.json()
            
            # Log the full response for debugging
            logger.info(f"File handler API full response: {result}")
            report_progress(task_id, "PROGRESS", 65, "File data extracted")

            # Extract text from documents' page_content
            raw_text_parts = []
            documents = result.get('documents', [])
            for doc in documents:
                page_content = doc.get('page_content', '')
                if page_content:
                    raw_text_parts.append(page_content.strip())
            
            raw_text = '\n\n'.join(raw_text_parts).strip()

            # Fallback to other possible fields if no documents
            if not raw_text:
                raw_text = (
                    result.get("raw_text") or
                    result.get("text") or
                    result.get("content") or
                    result.get("langchain_doc") or
                    ""
                ).strip()
            report_progress(task_id, "PROGRESS", 67, "Text extracted from file")
            if not raw_text:
                raise ValueError("No text extracted from file")

            processing_time = int((time.time() - start_time) * 1000)
            logger.info(f"Text extracted successfully in {processing_time}ms, Length: {len(raw_text)} chars")
            report_progress(task_id, "PROGRESS", 70, "Text extracted successfully")
            return raw_text

        except requests.RequestException as e:
            logger.error(f"File handler API error: {e}")
            raise HTTPException(status_code=502, detail="File processing service unavailable")
        except Exception as e:
            logger.error(f"File extraction failed: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to extract text: {str(e)}")
        
file_handler = FileHandler()