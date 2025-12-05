# # from app.api.endpoints import test_api_router
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi import FastAPI, APIRouter
# from app.api.endpoints import job_agents_api

# app = FastAPI(
#     title="Job Agent Service",
#     version="1.0.0",
#     description="Job Agent Service API",
#     docs_url="/model/api/docs"
# )
# # Configure CORS middleware to allow cross-origin requests
# origins = ["*"]  # Allow requests from all origins
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=origins,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # Include test API router
# # app.include_router(test_api_router)


# # Set up resume analyzer router
# job_agents = APIRouter()
# job_agents.include_router(job_agents_api.router)




"""
Job Agent Main Application

FastAPI application for resume parsing service using Gemini AI.
"""

from fastapi import FastAPI
from app.api import test_api_router, job_post_router, websocket_router, file_router, pdf_router
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






