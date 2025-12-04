from fastapi import FastAPI
from app.api import test_api_router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Job Agent Service",
    version="1.0.0",
    description="Job Agent Service API",
    docs_url="/model/api/docs"
)
# Configure CORS middleware to allow cross-origin requests
origins = ["*"]  # Allow requests from all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include test API router
app.include_router(test_api_router)






