"""
Configuration module for the application.
This module handles loading environment variables, setting up logging,
and defining application settings using Pydantic.

The module provides a Settings class that encapsulates all configuration 
parameters needed by the application, including API keys and server settings.

The module uses pydantic for settings management and validation.

Author: [Supriyo Chowdhury]
Version: 1.1
Last Modified: [2024-12-19]
"""

"""<-----------------------SERVER CONFIGURATION FILE [NOT FOR DEV]------------------------>"""

import os
from pydantic_settings import BaseSettings
from pydantic import Field
#from .logging import setup_logging
import logging
from urllib.parse import quote_plus

# Setup application logging
#setup_logging(override=True)
logger = logging.getLogger("app_logger")

class Settings(BaseSettings):
    """
    Settings class that manages all application configuration.
    
    Inherits from Pydantic BaseSettings to provide environment variable parsing
    and validation. Loads configuration from environment variables.
    
    Attributes:
        ANTHROPIC_API_KEY (str): API key for Anthropic services
        EUREKA_SERVER (str): URL of the Eureka server for service discovery
        APP_NAME (str): Name of the application
        LOCAL_IP (str): Local IP address for the application
        SERVER_PORT (int): Port number for the server
    """

    APP_NAME: str = Field("Job Agent Service", env="APP_NAME")
    DEBUG: bool = Field(False, env="DEBUG")

    GOOGLE_API_KEY: str = Field(..., env="GOOGLE_API_KEY")
    GOOGLE_MODEL_NAME: str = Field(..., env="GOOGLE_MODEL_NAME")
    JOB_AGENT_LOG: str = Field(..., env="JOB_AGENT_LOG")
    FILE_HANDLING_API_KEY: str = Field(..., env="FILE_HANDLING_API_KEY")
    AUTH_SERVICE_URL: str = Field(..., env="AUTH_SERVICE_URL")
    ACCESS_TOKEN_EXPIRE_HOURS: str = Field(..., env="ACCESS_TOKEN_EXPIRE_HOURS")
    JWT_SECRET_KEY: str = Field(..., env="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = Field(..., env="JWT_ALGORITHM")

    DB_HOST: str = Field(..., env="DB_HOST")
    DB_PORT: str = Field(..., env="DB_PORT")
    DB_NAME: str = Field(..., env="DB_NAME")
    DB_USER: str = Field(..., env="DB_USER")
    DB_PASSWORD: str = Field(..., env="DB_PASSWORD")

    PDFKIT_PATH: str = Field(..., env="PDFKIT_PATH")
    LOGO_PATH: str = Field(..., env="LOGO_PATH")
    
    REDIS_HOST: str = Field(..., env="REDIS_HOST")
    REDIS_PORT: str = Field(..., env="REDIS_PORT")
    REDIS_DB: str = Field(..., env="REDIS_DB")
    REDIS_PASSWORD: str = Field(..., env="REDIS_PASSWORD")
    
    IMAGE_PATH: str = Field(..., env="IMAGE_PATH")
    BASE_URL: str = Field(..., env="BASE_URL")

    # Reporting configuration
    REPORT_DEFAULT_TZ: str = Field("UTC", env="REPORT_DEFAULT_TZ")
    REPORT_EMAIL_FROM: str = Field(default_factory=lambda: os.getenv("SMTP_EMAIL", "eyeai@htinfosystems.com"), env="REPORT_EMAIL_FROM")
    REPORT_EMAIL_FROM_NAME: str = Field("EyeAI Reports", env="REPORT_EMAIL_FROM_NAME")

    # SMTP configuration for report delivery
    SMTP_SERVER: str = Field("", env="SMTP_SERVER")
    SMTP_PORT: int = Field(587, env="SMTP_PORT")
    SMTP_EMAIL: str | None = Field("", env="SMTP_EMAIL")
    SMTP_PASSWORD: str | None = Field("", env="SMTP_PASSWORD")
    SMTP_USE_TLS: bool = Field(True, env="SMTP_USE_TLS")

    @property
    def DB_URI(self) -> str:
                encoded_password = quote_plus(self.DB_PASSWORD)
                uri = f"mysql+pymysql://{self.DB_USER}:{encoded_password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
                logger.debug(f"Database URI (password masked): {uri.replace(encoded_password, '****')}")
                return uri

    class Config:
        """
        Inner configuration class for Pydantic settings.
        Specifies the environment variable prefix and validation behavior.
        """
        env_prefix = ""  # No prefix for environment variables

# Create an instance of the Settings class
try:
    settings = Settings()
    logger.info("Configuration loaded successfully.")
except Exception as e:
    logger.error(f"Error occurred while loading configuration: {e}")