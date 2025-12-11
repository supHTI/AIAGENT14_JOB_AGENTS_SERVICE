"""
Celery Tasks for Job Post Generation

This module contains Celery background tasks for generating job posts.

Author: [Supriyo Chowdhury]
Version: 1.0
Last Modified: [2024-12-19]
"""

from app.celery.celery_config import celery_app
from app.database_layer.db_config import SessionLocal
from app.database_layer.db_model import JobPosts, JobOpenings, Company
from app.models.gemini_model import configure_gemini_model
from app.prompt_templates.html_generation_prompt import get_html_generation_prompt
from app.prompt_templates.job_post_planning_prompt import get_job_post_planning_prompt
from app.utils.file_storage import save_uploaded_file, generate_file_id, get_file_url, ensure_directory_exists
from app.cache_db.redis_config import get_redis_client
from app.core import settings
import logging
import os
import uuid
import json
from datetime import datetime, timezone
from langchain_google_genai import ChatGoogleGenerativeAI
import google.generativeai as genai
from PIL import Image
import io
import base64
import requests

logger = logging.getLogger("app_logger")

def update_task_status(task_id: str, status: str, progress: int, message: str = "", step: str = ""):
    """
    Update task status in Redis and publish to pub/sub for real-time WebSocket updates.
    
    Args:
        task_id (str): Task ID
        status (str): Current status
        progress (int): Progress percentage (0-100)
        message (str): Status message
        step (str): Current step name (optional)
    """
    try:
        redis_client = get_redis_client()
        status_data = {
            "task_id": task_id,
            "status": status,
            "progress": progress,
            "message": message,
            "step": step,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Store status in Redis with expiry
        redis_client.setex(
            f"task_status:{task_id}",
            3600,  # 1 hour expiry
            json.dumps(status_data)
        )
        
        # Publish to Redis pub/sub for real-time WebSocket updates
        redis_client.publish(
            f"task_status_updates:{task_id}",
            json.dumps(status_data)
        )
        
        logger.info(f"Task {task_id} status updated: {status} ({progress}%) - {message}")
    except Exception as e:
        logger.error(f"Error updating task status: {e}", exc_info=True)

@celery_app.task(bind=True, name="generate_job_post_task", queue="job_queue")
def generate_job_post_task(self, task_data: dict):
    """
    Generate job post HTML in background.
    
    Args:
        task_data (dict): Task data containing all job post information
    
    Returns:
        dict: Result with job_post_id and status
    """
    task_id = task_data.get("task_id")
    job_post_db_id = task_data.get("job_post_db_id")
    job_post_id = task_data.get("job_post_id")
    job_id = task_data.get("job_id")
    
    db = SessionLocal()
    job_post = None  # Initialize to avoid NameError in exception handler
    
    try:
        # Step 1: Initialize task
        update_task_status(task_id, "processing", 5, "Initializing task", "initialization")
        
        # Update DB status
        job_post = db.query(JobPosts).filter(JobPosts.id == job_post_db_id).first()
        if job_post:
            job_post.status = "processing"
            db.commit()
        
        # Step 2: Fetch job and company details
        update_task_status(task_id, "processing", 15, "Fetching job details from database", "fetch_job_details")
        job = db.query(JobOpenings).filter(JobOpenings.id == job_id).first()
        if not job:
            raise Exception("Job opening not found")
        
        update_task_status(task_id, "processing", 20, "Fetching company information", "fetch_company_details")
        company = db.query(Company).filter(Company.id == job.company_id).first()
        company_name = company.company_name if company else "Unknown Company"
        
        # Step 3: Prepare salary info
        update_task_status(task_id, "processing", 25, "Preparing job information", "prepare_job_info")
        salary_info = "Not specified"
        show_salary = task_data.get("salary_info", True)
        if show_salary:
            if job.min_salary and job.max_salary:
                currency = job.currency or "USD"
                salary_info = f"{currency} {job.min_salary} - {currency} {job.max_salary}"
            elif job.min_salary:
                currency = job.currency or "USD"
                salary_info = f"{currency} {job.min_salary}+"
        
        # Step 4: Planning agent (runs regardless of generate_image flag)
        job_post_plan = None
        image_urls = task_data.get("image_urls", [])
        dimension_info = task_data.get("dimension", {})
        contact_details = task_data.get("contact_details", "")
        
        update_task_status(task_id, "processing", 30, "Planning job post structure with AI", "planning_agent")
        try:
            # Get planning prompt (without deadline and skills_required)
            planning_prompt = get_job_post_planning_prompt(
                job_title=job.title,
                company_name=company_name,
                location=job.location,
                job_type=job.job_type,
                work_mode=job.work_mode or "Not specified",
                skills_required="",  # Not included in planning
                min_exp=float(job.min_exp) if job.min_exp else 0,
                max_exp=float(job.max_exp) if job.max_exp else 0,
                salary_info=salary_info,
                deadline="",  # Not included in planning
                additional_info=job.remarks or "",
                type=task_data.get("type", "professional"),
                dimension_name=dimension_info.get("name", "Instagram"),
                width=dimension_info.get("width", 1080),
                height=dimension_info.get("height", 1080),
                instructions=task_data.get("instructions", ""),
                show_salary=show_salary,
                show_contact=bool(contact_details)
            )
            
            # Get Gemini model for planning
            planning_model = configure_gemini_model(temperature=0.7)
            planning_response = planning_model.invoke(planning_prompt)
            planning_text = planning_response.content if hasattr(planning_response, 'content') else str(planning_response)
            
            # Clean JSON response
            if "```json" in planning_text:
                planning_text = planning_text.split("```json")[1].split("```")[0].strip()
            elif "```" in planning_text:
                planning_text = planning_text.split("```")[1].split("```")[0].strip()
            
            # Parse JSON
            job_post_plan = json.loads(planning_text)
            logger.info(f"Job post plan generated: {json.dumps(job_post_plan, indent=2)}")
            
            # Generate image only if generate_image is True
            if task_data.get("generate_image", False):
                update_task_status(task_id, "processing", 35, "Generating image with AI", "generate_image_processing")
                generated_image_url = generate_image_with_ai(
                    job_id,
                    job_post_plan.get("image_prompt", task_data.get("instructions", "")),
                    task_data.get("type", "professional"),
                    dimension_info.get("width", 1080),
                    dimension_info.get("height", 1080)
                )
                if generated_image_url:
                    image_urls.append(generated_image_url)
                    update_task_status(task_id, "processing", 40, "Image generated successfully", "generate_image_complete")
                else:
                    update_task_status(task_id, "processing", 40, "Image generation failed", "generate_image_failed")
            else:
                update_task_status(task_id, "processing", 35, "Image generation skipped (generate_image=false)", "generate_image_skipped")
                    
        except Exception as e:
            logger.error(f"Error in planning or image generation: {e}", exc_info=True)
            update_task_status(task_id, "processing", 40, "Planning failed, continuing without plan", "planning_failed")
            # Continue without plan
        
        # Step 5: Prepare HTML generation prompt
        update_task_status(task_id, "processing", 45, "Preparing HTML generation prompt", "prepare_html_prompt")
        dimension_info = task_data.get("dimension", {})
        contact_details = task_data.get("contact_details", "")
        
        # Enhance instructions with planning agent output if available
        enhanced_instructions = task_data.get("instructions", "")
        if job_post_plan:
            plan_instructions = f"""
Design Requirements from Planning Agent:
- Layout: {json.dumps(job_post_plan.get('layout', {}), indent=2)}
- Color Template: {json.dumps(job_post_plan.get('color_template', {}), indent=2)}
- Show Details: {json.dumps(job_post_plan.get('show_details', {}), indent=2)}
- Social Media: {', '.join(job_post_plan.get('social_media', []))}
- Hero UI: {job_post_plan.get('hero_ui', False)}

Original Instructions: {enhanced_instructions}
"""
            enhanced_instructions = plan_instructions
        
        prompt = get_html_generation_prompt(
            dimension_name=dimension_info.get("name", "Instagram"),
            width=dimension_info.get("width", 1080),
            height=dimension_info.get("height", 1080),
            job_title=job.title,
            company_name=company_name,
            location=job.location,
            job_type=job.job_type,
            work_mode=job.work_mode or "Not specified",
            skills_required=job.skills_required or "Not specified",
            min_exp=float(job.min_exp) if job.min_exp else 0,
            max_exp=float(job.max_exp) if job.max_exp else 0,
            salary_info=salary_info if show_salary else "Not specified",
            deadline=job.deadline.strftime("%Y-%m-%d") if job.deadline else "Not specified",
            additional_info=job.remarks or "",
            type=task_data.get("type", "professional"),
            language=task_data.get("language", "English"),
            logo_url=task_data.get("logo_url", ""),
            image_urls=image_urls,
            cta_required=task_data.get("cta", False),
            instructions=enhanced_instructions,
            contact_details=contact_details,
            job_post_plan=job_post_plan
        )
        
        # Step 6: Get Gemini model
        update_task_status(task_id, "processing", 50, "Configuring AI model", "configure_ai_model")
        model = configure_gemini_model()
        
        # Step 7: Generate HTML with AI
        update_task_status(task_id, "processing", 60, "Generating HTML content with AI", "generate_html_ai")
        response = model.invoke(prompt)
        html_content = response.content if hasattr(response, 'content') else str(response)
        
        # Step 8: Clean HTML content
        update_task_status(task_id, "processing", 75, "Cleaning and formatting HTML", "clean_html")
        if "```html" in html_content:
            html_content = html_content.split("```html")[1].split("```")[0].strip()
        elif "```" in html_content:
            html_content = html_content.split("```")[1].split("```")[0].strip()
        
        # Step 9: Save HTML to file
        update_task_status(task_id, "processing", 85, "Saving HTML file to storage", "save_html_file")
        html_file_id = generate_file_id(job_id, "html")
        html_file_path = os.path.join(settings.IMAGE_PATH, f"{html_file_id}.html")
        
        # Ensure directory exists
        ensure_directory_exists(settings.IMAGE_PATH)
        
        with open(html_file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        html_url = get_file_url(html_file_id)
        
        # Step 10: Update database
        update_task_status(task_id, "processing", 90, "Updating database records", "update_database")
        if job_post:
            job_post.status = "completed"
            job_post.html_text = html_content  # Store HTML in database
            job_post.updated_at = datetime.now(timezone.utc)
            db.commit()
        
        # Step 11: Task completed
        update_task_status(task_id, "completed", 100, "Job post generated successfully", "completed")
        
        return {
            "job_post_id": job_post_id,
            "status": "completed",
            "html_url": html_url,
            "html_file_id": html_file_id
        }
        
    except Exception as e:
        logger.error(f"Error in generate_job_post_task: {e}", exc_info=True)
        
        # Update status to failed
        update_task_status(task_id, "failed", 0, f"Error: {str(e)}", "error")
        
        # Update DB status
        if job_post:
            job_post.status = "failed"
            db.commit()
        
        raise
    
    finally:
        db.close()


def generate_image_with_ai(job_id: int, image_prompt: str, type: str, width: int = 1080, height: int = 1080) -> str:
    """
    Generate image using Gemini Nano Banana (gemini-2.5-flash-image).
    
    Args:
        job_id (int): Job ID
        image_prompt (str): Detailed prompt for image generation
        type (str): Type of design
        width (int): Image width in pixels
        height (int): Image height in pixels
    
    Returns:
        str: URL of generated image (saved locally)
    """
    try:
        # Use Gemini API for image generation (Nano Banana)
        # Reference: https://ai.google.dev/gemini-api/docs/image-generation
        
        # Calculate aspect ratio
        aspect_ratio = width / height if height > 0 else 1.0
        
        # Map to closest supported aspect ratio
        # Supported ratios: 1:1, 2:3, 3:2, 3:4, 4:3, 4:5, 5:4, 9:16, 16:9, 21:9
        if 0.9 <= aspect_ratio <= 1.1:
            aspect_ratio_str = "1:1"
        elif 0.6 <= aspect_ratio <= 0.7:
            aspect_ratio_str = "2:3"
        elif 1.4 <= aspect_ratio <= 1.5:
            aspect_ratio_str = "3:2"
        elif 0.7 <= aspect_ratio <= 0.8:
            aspect_ratio_str = "3:4"
        elif 1.2 <= aspect_ratio <= 1.3:
            aspect_ratio_str = "4:3"
        elif 0.8 <= aspect_ratio <= 0.9:
            aspect_ratio_str = "4:5"
        elif 1.2 <= aspect_ratio <= 1.3:
            aspect_ratio_str = "5:4"
        elif 0.5 <= aspect_ratio <= 0.6:
            aspect_ratio_str = "9:16"
        elif 1.7 <= aspect_ratio <= 1.8:
            aspect_ratio_str = "16:9"
        elif 2.2 <= aspect_ratio <= 2.3:
            aspect_ratio_str = "21:9"
        else:
            aspect_ratio_str = "1:1"  # Default
        
        # Enhanced prompt
        enhanced_prompt = f"""
        {image_prompt}
        
        Style: {type}
        The image should be professional, high-quality, and suitable for a job posting.
        Ensure good composition, lighting, and visual appeal.
        """
        
        # Try using the new google.genai package first, fallback to REST API
        try:
            from google import genai as google_genai
            from google.genai import types
            
            client = google_genai.Client(api_key=settings.GOOGLE_API_KEY)
            
            response = client.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=[enhanced_prompt],
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"]
                )
            )
            
            # Extract image from response
            for part in response.parts:
                if hasattr(part, 'inline_data') and part.inline_data:
                    image_data = part.inline_data.data
                    # Save image
                    image_file_id = generate_file_id(job_id, "generated_image")
                    image_path = os.path.join(settings.IMAGE_PATH, f"{image_file_id}.png")
                    ensure_directory_exists(settings.IMAGE_PATH)
                    
                    # Decode base64 and save
                    if isinstance(image_data, str):
                        image_bytes = base64.b64decode(image_data)
                    else:
                        image_bytes = image_data
                    
                    with open(image_path, "wb") as f:
                        f.write(image_bytes)
                    
                    # Return URL
                    return get_file_url(image_file_id)
                    
        except ImportError:
            # Fallback to REST API if google.genai not available
            logger.info("Using REST API for image generation")
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"
            
            headers = {
                "x-goog-api-key": settings.GOOGLE_API_KEY,
                "Content-Type": "application/json"
            }
            
            payload = {
                "contents": [{
                    "parts": [
                        {"text": enhanced_prompt}
                    ]
                }],
                "generationConfig": {
                    "responseModalities": ["IMAGE"]
                }
            }
            
            response = requests.post(api_url, headers=headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            # Extract image from response
            if "candidates" in result and len(result["candidates"]) > 0:
                content = result["candidates"][0].get("content", {})
                parts = content.get("parts", [])
                
                for part in parts:
                    if "inlineData" in part:
                        image_data = part["inlineData"]["data"]
                        
                        # Save image
                        image_file_id = generate_file_id(job_id, "generated_image")
                        image_path = os.path.join(settings.IMAGE_PATH, f"{image_file_id}.png")
                        ensure_directory_exists(settings.IMAGE_PATH)
                        
                        # Decode base64 and save
                        image_bytes = base64.b64decode(image_data)
                        with open(image_path, "wb") as f:
                            f.write(image_bytes)
                        
                        # Return URL
                        return get_file_url(image_file_id)
        
        logger.warning("No image data found in response")
        return None
        
    except Exception as e:
        logger.error(f"Error generating image: {e}", exc_info=True)
        return None

