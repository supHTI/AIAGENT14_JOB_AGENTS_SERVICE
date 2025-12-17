"""
Configuration Module

This module handles the configuration settings for the application, including environment variables,
logging setup, and various API keys and identifiers for external services.

Key components:
- Settings: Pydantic BaseSettings class for managing configuration
- Environment variable loading
- Logging setup

Dependencies:
- os for environment variable access
- pydantic_settings for settings management
- dotenv for .env file loading
- logging for application logging
"""

import os
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv
from typing import Optional
#from .logging import setup_logging
import logging
from urllib.parse import quote_plus

# Load environment variables from .env file
load_dotenv(override=True)

# Setup application logging
#setup_logging(override=True)
logger = logging.getLogger("app_logger")

 # Redis  ✅ FIXED
    # -------------------------
REDIS_HOST: str
REDIS_PORT: int
REDIS_DB: int = 0
REDIS_PASSWORD: Optional[str] = None  # ✅ IMPORTANT


class Settings(BaseSettings):
    """
    Settings class to manage application configuration.

    This class uses Pydantic's BaseSettings to handle configuration variables,
    including environment variables and default values.
    """
    
    try:
        # Basic configurations
        APP_NAME: str = "Job Agent Service"
        DEBUG: bool = False

        # Google API configurations (Gemini AI)
        GOOGLE_API_KEY: str = os.getenv('GOOGLE_API_KEY')
        logger.info("GOOGLE_API_KEY Retrieved")
        GOOGLE_MODEL_NAME:str=os.getenv('GOOGLE_MODEL_NAME')
        logger.info("GOOGLE_MODEL_NAME Retrieved")
        JOB_AGENT_LOG:str=os.getenv('JOB_AGENT_LOG')
        logger.info("JOB_AGENT_LOG Retrieved")
        FILE_HANDLING_API_KEY:str=os.getenv('FILE_HANDLING_API_KEY')
        logger.info("FILE_HANDLING_API_KEY Retrieved")
        
        AUTH_SERVICE_URL:str=os.getenv('AUTH_SERVICE_URL')
        logger.info("AUTH_SERVICE_URL Retrieved")

        ACCESS_TOKEN_EXPIRE_HOURS:str=os.getenv('ACCESS_TOKEN_EXPIRE_HOURS')
        logger.info("ACCESS_TOKEN_EXPIRE_HOURS Retrieved")
        JWT_SECRET_KEY:str=os.getenv('JWT_SECRET_KEY')
        logger.info("JWT_SECRET_KEY Retrieved")
        JWT_ALGORITHM:str=os.getenv('JWT_ALGORITHM')
        logger.info("JWT_ALGORITHM Retrieved")

        DB_HOST:str=os.getenv('DB_HOST')
        logger.info("DB_HOST Retrieved")
        DB_PORT:str=os.getenv('DB_PORT')
        logger.info("DB_PORT Retrieved")
        DB_NAME:str=os.getenv('DB_NAME')
        logger.info("DB_NAME Retrieved")
        DB_USER:str=os.getenv('DB_USER')
        logger.info("DB_USER Retrieved")
        DB_PASSWORD:str=os.getenv('DB_PASSWORD')
        logger.info("DB_PASSWORD Retrieved")

        PDFKIT_PATH:str=os.getenv('PDFKIT_PATH')
        logger.info("PDFKIT_PATH Retrieved")

        LOGO_PATH:str=os.getenv('LOGO_PATH')
        logger.info("LOGO_PATH Retrieved")
        
        REDIS_HOST: str = os.getenv('REDIS_HOST')
        logger.info("REDIS_HOST Retrieved")
        REDIS_PORT: str = os.getenv('REDIS_PORT')
        logger.info("REDIS_PORT Retrieved")
        REDIS_DB: str = os.getenv('REDIS_DB')
        logger.info("REDIS_DB Retrieved")
        REDIS_PASSWORD: str = os.getenv('REDIS_PASSWORD')
        logger.info("REDIS_PASSWORD Retrieved")

        IMAGE_PATH: str = os.getenv('IMAGE_PATH', './uploads/images')
        logger.info("IMAGE_PATH Retrieved")
        
        BASE_URL: str = os.getenv('BASE_URL', 'http://localhost:8000')
        logger.info("BASE_URL Retrieved")

        # Reporting configuration
        REPORT_DEFAULT_TZ: str = os.getenv('REPORT_DEFAULT_TZ', 'UTC')
        REPORT_EMAIL_FROM: str = os.getenv('REPORT_EMAIL_FROM', os.getenv('SMTP_EMAIL', ''))
        REPORT_EMAIL_FROM_NAME: str = os.getenv('REPORT_EMAIL_FROM_NAME', 'Job Agent Reports')

        # SMTP configuration for report delivery
        SMTP_SERVER: str = os.getenv('SMTP_SERVER', '')
        SMTP_PORT: int = int(os.getenv('SMTP_PORT', 587))
        SMTP_EMAIL: str | None = os.getenv('SMTP_EMAIL', '')
        SMTP_PASSWORD: str | None = os.getenv('SMTP_PASSWORD', '')
        SMTP_USE_TLS: bool = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'

        @property
        def DB_URI(self) -> str:
                    encoded_password = quote_plus(self.DB_PASSWORD)
                    uri = f"mysql+pymysql://{self.DB_USER}:{encoded_password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
                    logger.debug(f"Database URI (password masked): {uri.replace(encoded_password, '****')}")
                    return uri

        class Config:
            """
            Inner configuration class for Pydantic settings.
            Specifies the .env file location and encoding.
            """
            env_file = r".env"
            env_file_encoding = "utf-8"
    except Exception as e:
        logger.error("Error occurred while setting up config variables")

# Create an instance of the Settings class
settings = Settings()