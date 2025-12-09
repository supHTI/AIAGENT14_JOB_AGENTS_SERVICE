"""
Job Agent Main Application

FastAPI application for resume parsing service using Gemini AI.
"""

from fastapi import FastAPI
# Import routers explicitly to avoid importing app.api package which
# may perform eager imports and cause circular dependencies.
from app.api.endpoints.test_api import router as test_api_router
from app.api.endpoints.job_post_api import router as job_post_router
from app.api.endpoints.websocket_api import router as websocket_router
from app.api.endpoints.file_api import router as file_router
from app.api.endpoints.pdf_api import router as pdf_router
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints.job_agent_api import router as job_agent_router
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(
    title="Job Agent - Resume Parser",
    description="AI-powered resume extraction service using Gemini 2.0",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(test_api_router)
app.include_router(job_post_router)
app.include_router(websocket_router)
app.include_router(file_router)
app.include_router(pdf_router)
app.include_router(job_agent_router)






