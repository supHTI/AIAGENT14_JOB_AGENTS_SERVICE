"""
Job Agent Main Application

FastAPI application for resume parsing service using Gemini AI.
"""

from fastapi import FastAPI

from app.api import (
    test_api_router,
    job_post_router,
    websocket_router,
    file_router,
    pdf_router,
    call_router,
    jobs_report_router,
    recruiters_report_router,
    pipeline_report_router,
    clawback_report_router,
    exports_report_router,
)

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
    docs_url="/model/api/docs",
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
app.include_router(job_agent_router)
app.include_router(test_api_router)
app.include_router(job_post_router)
app.include_router(websocket_router)
app.include_router(file_router)
app.include_router(pdf_router)
app.include_router(call_router)

app.include_router(jobs_report_router)
app.include_router(recruiters_report_router)
app.include_router(pipeline_report_router)
app.include_router(clawback_report_router)
app.include_router(exports_report_router)







