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
            # Encode file bytes to base64
            file_content_b64 = base64.b64encode(file_bytes).decode('utf-8')
            
            # Prepare JSON payload
            payload = {
                "file": file_content_b64,
                "base64": True,
                "perform_ocr": perform_ocr,
                "image_desc": False
            }
            # Optionally include filename if the API supports it
            payload["filename"] = filename

            logger.info(f"Calling file handler API for: {filename}, OCR: {perform_ocr} (base64 mode)")
            
            response = requests.post(
                settings.FILE_HANDLING_API_KEY,
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            result = response.json()
            
            # Log the full response for debugging
            logger.info(f"File handler API full response: {result}")

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