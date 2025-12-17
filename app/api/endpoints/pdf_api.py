"""
Download API Endpoints

This module contains API endpoints for downloading job posts as PDF, JPG, or PNG.

Author: [Supriyo Chowdhury]
Version: 2.0
Last Modified: [2024-12-19]
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
import pdfkit
import tempfile
import os
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Literal
from io import BytesIO

from app.database_layer.db_config import get_db
from app.database_layer.db_model import JobPosts
from app.core import settings
from app.utils.dimension_mapping import get_dimension, DIMENSION_MAP

logger = logging.getLogger("app_logger")

router = APIRouter(prefix="/download", tags=["download"])

# Thread pool executor for blocking operations
executor = ThreadPoolExecutor(max_workers=4)


def _generate_pdf_sync(html_content: str, width: int, height: int, pdfkit_config=None) -> bytes:
    """
    Synchronous PDF generation function to run in thread pool.
    
    Args:
        html_content: HTML content to convert
        width: Width in pixels
        height: Height in pixels
        pdfkit_config: pdfkit configuration
    
    Returns:
        bytes: PDF file bytes
    """
    try:
        # Determine orientation
        is_portrait = height > width
        is_landscape = width > height
        
        # Configure pdfkit options with custom dimensions
        # Convert pixels to inches (assuming 96 DPI)
        width_in = width / 96.0
        height_in = height / 96.0
        
        # Determine page size based on dimensions
        # For very specific dimensions, use custom size
        # For standard sizes, use closest match
        if is_portrait:
            page_size = 'A4'  # Default portrait
            orientation = 'Portrait'
        elif is_landscape:
            page_size = 'A4'  # Default landscape
            orientation = 'Landscape'
        else:
            page_size = 'A4'  # Square
            orientation = 'Portrait'
        
        options = {
            'page-width': f'{width_in}in',
            'page-height': f'{height_in}in',
            'orientation': orientation,
            'margin-top': '0',
            'margin-right': '0',
            'margin-bottom': '0',
            'margin-left': '0',
            'encoding': "UTF-8",
            'no-outline': None,
            'enable-local-file-access': None,
            'disable-smart-shrinking': None,
            'disable-javascript': None,
            'quiet': None,
            'print-media-type': None,
            'dpi': 96,  # Match pixel to inch conversion
        }
        
        # Ensure HTML has proper viewport and sizing
        # Inject CSS if needed to ensure proper dimensions
        if '<style>' in html_content:
            # Add viewport and sizing CSS
            sizing_css = f"""
            <style>
            @page {{
                size: {width_in}in {height_in}in;
                margin: 0;
            }}
            html, body {{
                width: {width}px;
                height: {height}px;
                margin: 0;
                padding: 0;
                overflow: hidden;
            }}
            </style>
            """
            html_content = html_content.replace('<style>', sizing_css + '<style>', 1)
        else:
            # Add style tag if not present
            sizing_css = f"""
            <style>
            @page {{
                size: {width_in}in {height_in}in;
                margin: 0;
            }}
            html, body {{
                width: {width}px;
                height: {height}px;
                margin: 0;
                padding: 0;
                overflow: hidden;
            }}
            </style>
            """
            if '</head>' in html_content:
                html_content = html_content.replace('</head>', sizing_css + '</head>', 1)
            elif '<body>' in html_content:
                html_content = html_content.replace('<body>', sizing_css + '<body>', 1)
            else:
                # Add at the beginning if no head/body
                html_content = sizing_css + html_content
        
        # Create temporary HTML file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as temp_html:
            temp_html.write(html_content)
            temp_html_path = temp_html.name
        
        try:
            # Generate PDF
            pdf_bytes = pdfkit.from_file(
                temp_html_path,
                False,  # Don't save to file, return bytes
                options=options,
                configuration=pdfkit_config
            )
            return pdf_bytes
        finally:
            # Clean up temporary HTML file
            if os.path.exists(temp_html_path):
                os.unlink(temp_html_path)
                
    except Exception as e:
        logger.error(f"Error in PDF generation: {e}", exc_info=True)
        raise


def _generate_image_sync(html_content: str, width: int, height: int, format: str = 'png', base_url: str = None) -> bytes:
    """
    Synchronous image generation function to run in thread pool.
    Uses Playwright if available, otherwise falls back to imgkit.
    
    Args:
        html_content: HTML content to convert
        width: Width in pixels
        height: Height in pixels
        format: Image format ('png' or 'jpeg')
        base_url: Base URL for resolving relative image paths
    
    Returns:
        bytes: Image file bytes
    """
    try:
        # Convert relative image URLs to absolute URLs and fix incorrect paths
        if base_url:
            import re
            from urllib.parse import urljoin, urlparse
            
            # Fix incorrect /api/files/ paths to /files/
            html_content = re.sub(r'(src="[^"]*)/api/files/([^"]+")', r'\1/files/\2', html_content)
            html_content = re.sub(r'(url\(["\']?[^"\']*)/api/files/([^"\']+["\']?\))', r'\1/files/\2', html_content)
            
            # Pattern to match img src attributes
            def replace_img_src(match):
                src = match.group(1)
                # Skip if already absolute URL
                parsed = urlparse(src)
                if parsed.netloc:
                    # Fix /api/files/ in absolute URLs
                    if '/api/files/' in src:
                        src = src.replace('/api/files/', '/files/')
                    return f'src="{src}"'
                # Convert relative to absolute
                absolute_url = urljoin(base_url, src)
                return f'src="{absolute_url}"'
            
            # Replace img src attributes
            html_content = re.sub(r'src="([^"]+)"', replace_img_src, html_content)
            
            # Also handle background-image in style attributes
            def replace_bg_image(match):
                url_match = re.search(r'url\(["\']?([^"\']+)["\']?\)', match.group(0))
                if url_match:
                    bg_url = url_match.group(1)
                    parsed = urlparse(bg_url)
                    if parsed.netloc:
                        # Fix /api/files/ in absolute URLs
                        if '/api/files/' in bg_url:
                            bg_url = bg_url.replace('/api/files/', '/files/')
                            return match.group(0).replace(url_match.group(1), bg_url)
                        return match.group(0)
                    else:
                        # Convert relative to absolute
                        absolute_url = urljoin(base_url, bg_url)
                        return match.group(0).replace(bg_url, absolute_url)
                return match.group(0)
            
            html_content = re.sub(r'background-image:\s*url\([^)]+\)', replace_bg_image, html_content)
        # Try Playwright first (better quality and dimension control)
        try:
            from playwright.sync_api import sync_playwright
            from playwright._impl._errors import Error as PlaywrightError
            
            with sync_playwright() as p:
                try:
                    browser = p.chromium.launch(headless=True)
                except PlaywrightError as e:
                    if "Executable doesn't exist" in str(e) or "browser" in str(e).lower():
                        error_msg = "Playwright browsers not installed. Please run: playwright install chromium"
                        logger.error(error_msg)
                        raise RuntimeError(error_msg)
                    raise
                
                # Create context with longer timeout for image loading
                context = browser.new_context(
                    viewport={'width': width, 'height': height},
                    ignore_https_errors=True  # Allow self-signed certificates if any
                )
                
                page = context.new_page()
                
                # Set longer timeout for network requests
                page.set_default_timeout(30000)  # 30 seconds
                page.set_default_navigation_timeout(30000)
                
                # Set content and wait for network to be idle
                page.set_content(html_content, wait_until='networkidle', timeout=30000)
                
                # Wait for all images to load explicitly with better error handling
                try:
                    # Count images before waiting
                    image_count = page.evaluate("document.images.length")
                    logger.info(f"Found {image_count} images in HTML, waiting for them to load...")
                    
                    # Wait for all images to load
                    page.evaluate("""
                        async () => {
                            const images = Array.from(document.images);
                            const loadPromises = images.map((img, index) => {
                                return new Promise((resolve) => {
                                    // If image is already loaded
                                    if (img.complete && img.naturalWidth > 0) {
                                        resolve({index, status: 'loaded', src: img.src});
                                        return;
                                    }
                                    
                                    // Wait for load or error
                                    const timeout = setTimeout(() => {
                                        resolve({index, status: 'timeout', src: img.src});
                                    }, 15000); // 15 second timeout per image
                                    
                                    img.addEventListener('load', () => {
                                        clearTimeout(timeout);
                                        resolve({index, status: 'loaded', src: img.src});
                                    }, {once: true});
                                    
                                    img.addEventListener('error', () => {
                                        clearTimeout(timeout);
                                        resolve({index, status: 'error', src: img.src});
                                    }, {once: true});
                                });
                            });
                            
                            const results = await Promise.all(loadPromises);
                            return results;
                        }
                    """)
                    
                    # Log image loading results
                    image_results = page.evaluate("""
                        () => Array.from(document.images).map((img, i) => ({
                            index: i,
                            src: img.src,
                            complete: img.complete,
                            naturalWidth: img.naturalWidth,
                            naturalHeight: img.naturalHeight
                        }))
                    """)
                    
                    loaded_count = sum(1 for img in image_results if img['naturalWidth'] > 0)
                    logger.info(f"Image loading complete: {loaded_count}/{len(image_results)} images loaded successfully")
                    
                    # Log any failed images
                    failed_images = [img for img in image_results if img['naturalWidth'] == 0]
                    if failed_images:
                        logger.warning(f"Some images failed to load: {[img['src'] for img in failed_images]}")
                    
                except Exception as e:
                    logger.warning(f"Error waiting for images: {e}, continuing anyway...")
                
                # Additional wait for any background images in CSS and final rendering
                page.wait_for_timeout(2000)  # Wait 2 seconds for any CSS background images and final rendering
                
                # Take screenshot
                screenshot_bytes = page.screenshot(
                    type=format,
                    full_page=False,
                    clip={'x': 0, 'y': 0, 'width': width, 'height': height}
                )
                
                context.close()
                browser.close()
                return screenshot_bytes
                
        except ImportError:
            logger.warning("Playwright not available, trying imgkit fallback")
            # Fallback to imgkit if Playwright not available
            try:
                import imgkit
                
                options = {
                    'width': width,
                    'height': height,
                    'format': format,
                    'quality': 100,
                    'enable-local-file-access': None,
                }
                
                # Create temporary HTML file
                with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as temp_html:
                    temp_html.write(html_content)
                    temp_html_path = temp_html.name
                
                try:
                    # Generate image
                    img_bytes = imgkit.from_file(
                        temp_html_path,
                        False,
                        options=options
                    )
                    return img_bytes
                finally:
                    if os.path.exists(temp_html_path):
                        os.unlink(temp_html_path)
                        
            except ImportError:
                # Final fallback: Use PIL with HTML rendering (basic)
                from PIL import Image, ImageDraw, ImageFont
                from io import BytesIO
                
                logger.warning("Neither Playwright nor imgkit available, using basic PIL fallback")
                # Create a basic image with the HTML content as text (very basic fallback)
                img = Image.new('RGB', (width, height), color='white')
                draw = ImageDraw.Draw(img)
                
                # This is a very basic fallback - just shows a message
                # In production, you should install Playwright or imgkit
                try:
                    font = ImageFont.truetype("arial.ttf", 20)
                except:
                    font = ImageFont.load_default()
                
                text = "Image generation requires Playwright or imgkit.\nPlease install: pip install playwright"
                draw.text((10, 10), text, fill='black', font=font)
                
                output = BytesIO()
                img_format = 'PNG' if format == 'png' else 'JPEG'
                img.save(output, format=img_format)
                return output.getvalue()
                
    except Exception as e:
        logger.error(f"Error in image generation: {e}", exc_info=True)
        raise


@router.get("/job-post/{job_post_id}")
async def download_job_post(
    job_post_id: str,
    type: Literal["pdf", "jpg", "png"] = Query(..., description="Download type: pdf, jpg, or png"),
    db: Session = Depends(get_db)
):
    """
    Download job post as PDF, JPG, or PNG maintaining original dimensions.
    
    Args:
        job_post_id: Job post identifier
        type: Download type - pdf, jpg, or png
        db: Database session
    
    Returns:
        File download response with appropriate content type
    """
    try:
        # Fetch job post
        job_post = db.query(JobPosts).filter(
            JobPosts.job_post_id == job_post_id,
            JobPosts.deleted_at.is_(None)
        ).first()
        
        if not job_post:
            raise HTTPException(status_code=404, detail="Job post not found")
        
        # Check if HTML text exists
        if not job_post.html_text:
            raise HTTPException(
                status_code=400, 
                detail="HTML content not available for this job post. The job post may still be processing."
            )
        
        # Check if job post is completed
        if job_post.status != "completed":
            raise HTTPException(
                status_code=400,
                detail=f"Job post is not completed yet. Current status: {job_post.status}"
            )
        
        # Get dimensions from job post
        dimension_name = job_post.dimension or "Instagram"
        dimension_info = None
        
        # Try to find dimension in mapping
        for key, value in DIMENSION_MAP.items():
            if value["name"] == dimension_name:
                dimension_info = value
                break
        
        # If not found, try to get from dimension mapping function
        if not dimension_info:
            dimension_info = get_dimension(dimension_name)
        
        width = dimension_info.get("width", 1080)
        height = dimension_info.get("height", 1080)
        
        logger.info(f"Generating {type.upper()} for job_post_id={job_post_id} with dimensions {width}x{height}")
        
        # Get PDFKIT_PATH from settings if available
        pdfkit_config = None
        if type == "pdf":
            try:
                if hasattr(settings, 'PDFKIT_PATH') and settings.PDFKIT_PATH:
                    pdfkit_config = pdfkit.configuration(wkhtmltopdf=settings.PDFKIT_PATH)
            except Exception as e:
                logger.warning(f"Could not configure pdfkit with PDFKIT_PATH: {e}. Using default configuration.")
        
        # Generate file based on type
        if type == "pdf":
            # Run PDF generation in thread pool to avoid blocking
            file_bytes = await asyncio.get_event_loop().run_in_executor(
                executor,
                _generate_pdf_sync,
                job_post.html_text,
                width,
                height,
                pdfkit_config
            )
            media_type = "application/pdf"
            file_extension = "pdf"
            
        elif type in ["jpg", "png"]:
            # Run image generation in thread pool to avoid blocking
            image_format = "jpeg" if type == "jpg" else "png"
            # Get base URL for resolving relative image paths
            base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
            file_bytes = await asyncio.get_event_loop().run_in_executor(
                executor,
                _generate_image_sync,
                job_post.html_text,
                width,
                height,
                image_format,
                base_url
            )
            media_type = f"image/{image_format}"
            file_extension = type
            
        else:
            raise HTTPException(status_code=400, detail=f"Invalid type: {type}. Must be pdf, jpg, or png")
        
        # Return file as response
        return Response(
            content=file_bytes,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename=job_post_{job_post_id}.{file_extension}"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in download generation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating {type}: {str(e)}")


@router.get("/job-post/{job_post_id}/preview")
async def preview_job_post_html(
    job_post_id: str,
    db: Session = Depends(get_db)
):
    """
    Preview job post HTML content.
    
    Args:
        job_post_id: Job post identifier
        db: Database session
    
    Returns:
        HTML content as response
    """
    try:
        # Fetch job post
        job_post = db.query(JobPosts).filter(
            JobPosts.job_post_id == job_post_id,
            JobPosts.deleted_at.is_(None)
        ).first()
        
        if not job_post:
            raise HTTPException(status_code=404, detail="Job post not found")
        
        if not job_post.html_text:
            raise HTTPException(
                status_code=400,
                detail="HTML content not available for this job post."
            )
        
        # Return HTML as response
        return Response(
            content=job_post.html_text,
            media_type="text/html"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving HTML: {e}")
        raise HTTPException(status_code=500, detail=str(e))



 
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from collections import defaultdict
import logging
from app.database_layer.db_config import get_db
from app.database_layer.db_model import Candidates, CandidateJobs, CandidateJobStatus, User
from app.services.emailer import EmailService
from app.celery.tasks.cooling_period_tasks import send_daily_cooling_period_reminders

logger = logging.getLogger("app_logger")
 
router = APIRouter()
 
@router.get("/candidate_metrics")
def candidate_metrics(db: Session = Depends(get_db)):
    today = datetime.utcnow()
   
    # Total candidates
    total_candidates = db.query(Candidates).count()
    print("Total candidates:", total_candidates)
   
    # Candidates with joined status - joined with candidate details
    joined_candidates_data = (
        db.query(
            Candidates.candidate_id,
            Candidates.candidate_name,
            Candidates.candidate_email,
            Candidates.candidate_phone_number,
            CandidateJobStatus.cooling_period_closed,
            Candidates.assigned_to,
        )
        .join(CandidateJobs, CandidateJobs.candidate_id == Candidates.candidate_id)
        .join(CandidateJobStatus, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(CandidateJobStatus.type == "JOINED")
        .all()
    )
    print("Joined candidates data:", joined_candidates_data)
   
    # Group candidates by assigned_to user
    user_candidates = defaultdict(list)
    
    result_candidate = []
    for row in joined_candidates_data:
        remaining_days = None
        if row.cooling_period_closed:
            remaining_days = (row.cooling_period_closed - today).days
            if remaining_days < 0:
                remaining_days = 0
        
        candidate_info = {
            "candidate_id": row.candidate_id,
            "candidate_name": row.candidate_name,
            "candidate_email": row.candidate_email,
            "candidate_phone_number": row.candidate_phone_number,
            "assigned_to": row.assigned_to,
            "cooling_period_remaining_days": remaining_days,
        }
        
        result_candidate.append(candidate_info)
        
        # Group by assigned_to user
        if row.assigned_to:
            user_candidates[row.assigned_to].append(candidate_info)
    
    # Fetch user details and prepare grouped data
    grouped_by_user = {}
    for user_id, candidates in user_candidates.items():
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            grouped_by_user[user.email] = {
                "user_id": user_id,
                "user_name": user.username,
                "user_email": user.email,
                "candidates": candidates
            }
 
    return {
        "total_candidates": total_candidates,
        "joined_candidates": result_candidate,
        "grouped_by_user": grouped_by_user
    }


@router.post("/send_cooling_period_reminders")
def send_cooling_period_reminders(db: Session = Depends(get_db)):
    """
    Send cooling period reminder emails to assigned users.
    Each user gets one email with all their assigned candidates.
    """
    try:
        today = datetime.utcnow()
        
        # Fetch candidates with joined status
        joined_candidates_data = (
            db.query(
                Candidates.candidate_id,
                Candidates.candidate_name,
                Candidates.candidate_email,
                Candidates.candidate_phone_number,
                CandidateJobStatus.cooling_period_closed,
                Candidates.assigned_to,
            )
            .join(CandidateJobs, CandidateJobs.candidate_id == Candidates.candidate_id)
            .join(CandidateJobStatus, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(CandidateJobStatus.type == "JOINED")
            .distinct()  # Ensure unique candidates
            .all()
        )
        
        # Group candidates by assigned_to user
        user_candidates = defaultdict(list)
        seen_candidates = set()  # Track unique candidates per user
        
        for row in joined_candidates_data:
            remaining_days = None
            if row.cooling_period_closed:
                remaining_days = (row.cooling_period_closed - today).days
                if remaining_days < 0:
                    remaining_days = 0
            
            candidate_key = (row.assigned_to, row.candidate_id)
            
            # Only add if not already seen for this user
            if candidate_key not in seen_candidates:
                seen_candidates.add(candidate_key)
                
                candidate_info = {
                    "candidate_id": row.candidate_id,
                    "candidate_name": row.candidate_name,
                    "candidate_email": row.candidate_email,
                    "candidate_phone_number": row.candidate_phone_number,
                    "cooling_period_remaining_days": remaining_days,
                }
                
                if row.assigned_to:
                    user_candidates[row.assigned_to].append(candidate_info)
        
        # Send emails to each assigned user
        email_service = EmailService()
        email_results = []
        
        for user_id, candidates in user_candidates.items():
            # Fetch user details
            user = db.query(User).filter(User.id == user_id).first()
            
            if not user or not user.email:
                logger.warning(f"User {user_id} not found or has no email. Skipping.")
                email_results.append({
                    "user_id": user_id,
                    "status": "failed",
                    "reason": "User not found or no email"
                })
                continue
            
            # Send email with all candidates for this user
            try:
                success = email_service.send_cooling_period_reminder(
                    to_email=user.email,
                    recipient_name=user.username or "User",
                    candidates=candidates
                )
                
                email_results.append({
                    "user_id": user_id,
                    "user_email": user.email,
                    "candidate_count": len(candidates),
                    "status": "sent" if success else "failed",
                    "candidates": [c["candidate_name"] for c in candidates]
                })
                
                logger.info(f"Email {'sent' if success else 'failed'} to {user.email} with {len(candidates)} candidate(s)")
                
            except Exception as e:
                logger.error(f"Error sending email to {user.email}: {str(e)}")
                email_results.append({
                    "user_id": user_id,
                    "user_email": user.email,
                    "status": "failed",
                    "reason": str(e)
                })
        
        return {
            "message": "Cooling period reminder emails processing completed",
            "total_users_notified": len(email_results),
            "email_results": email_results,
            "details": user_candidates
        }
        
    except Exception as e:
        logger.error(f"Error in send_cooling_period_reminders: {str(e)}")
        return {
            "message": "Error sending reminders",
            "error": str(e)
        }


@router.post("/trigger_daily_cooling_period_reminders")
def trigger_daily_cooling_period_reminders():
    """
    Manually trigger the daily cooling period reminder email task via Celery.
    This endpoint queues the task to run in the background.
    
    Returns:
        dict: Task ID and status information
    """
    try:
        # Trigger the Celery task
        task = send_daily_cooling_period_reminders.apply_async()
        
        return {
            "message": "Daily cooling period reminder task has been queued",
            "task_id": task.id,
            "status": "queued",
            "note": "The task will be processed by Celery workers. Use the task_id to check status."
        }
        
    except Exception as e:
        logger.error(f"Error triggering daily cooling period reminders: {str(e)}")
        return {
            "message": "Error triggering task",
            "error": str(e)
        }


@router.get("/check_cooling_period_task/{task_id}")
def check_cooling_period_task(task_id: str):
    """
    Check the status of a cooling period reminder task.
    
    Args:
        task_id: The Celery task ID
    
    Returns:
        dict: Task status and result information
    """
    try:
        from celery.result import AsyncResult
        from app.celery.celery_config import celery_app
        
        task_result = AsyncResult(task_id, app=celery_app)
        
        response = {
            "task_id": task_id,
            "status": task_result.state,
            "ready": task_result.ready(),
            "successful": task_result.successful() if task_result.ready() else None,
        }
        
        # Add result if task is completed
        if task_result.ready():
            if task_result.successful():
                response["result"] = task_result.result
            else:
                response["error"] = str(task_result.info)
        
        return response
        
    except Exception as e:
        logger.error(f"Error checking task status: {str(e)}")
        return {
            "task_id": task_id,
            "error": str(e)
        }
