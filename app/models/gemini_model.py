"""
Gemini Model Configuration Module

This module provides a class and functions to configure and initialize the Gemini model
using Langchain. It handles the setup of the Google Gemini AI model with proper
configuration from environment settings.

Key components:
- GeminiModelConfig: Class to configure and initialize Gemini model
- configure_gemini_model: Function to create and return a configured Gemini model instance
- Logger integration for tracking model initialization and usage

Dependencies:
- langchain_google_genai: For Google Gemini integration with Langchain
- app.core.config_dev/config_prod: For API key and model name configuration
- logging: For application logging
"""

import os
import logging
from typing import Optional
from langchain_google_genai import ChatGoogleGenerativeAI

# Determine environment and import appropriate settings
ENV = os.getenv("APP_ENV", "dev")

if ENV == "prod":
    from app.core.config_prod import settings
else:
    from app.core.config_dev import settings

# Setup logger
logger = logging.getLogger("app_logger")


class GeminiModelConfig:
    """
    Configuration class for Google Gemini model using Langchain.
    
    This class handles the initialization and configuration of the Gemini model
    using the API key and model name from the application settings.
    
    Attributes:
        api_key (str): Google API key for Gemini
        model_name (str): Name of the Gemini model to use
        model (ChatGoogleGenerativeAI): Initialized Langchain Gemini model instance
    """
    
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        """
        Initialize the GeminiModelConfig with API key and model name.
        
        Args:
            api_key (str, optional): Google API key. If not provided, uses settings.GOOGLE_API_KEY
            model_name (str, optional): Model name. If not provided, uses settings.GOOGLE_MODEL_NAME
        """
        try:
            self.api_key = api_key or settings.GOOGLE_API_KEY
            self.model_name = model_name or settings.GOOGLE_MODEL_NAME
            
            if not self.api_key:
                raise ValueError("Google API key is required but not found in settings")
            if not self.model_name:
                raise ValueError("Google model name is required but not found in settings")
            
            logger.info(f"Initializing Gemini model: {self.model_name}")
            logger.debug("API key retrieved successfully")
            
            # Initialize the Gemini model using Langchain
            self.model = ChatGoogleGenerativeAI(
                model=self.model_name,
                google_api_key=self.api_key,
                temperature=0.7,
                convert_system_message_to_human=True
            )
            
            logger.info(f"Gemini model '{self.model_name}' initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing Gemini model: {str(e)}", exc_info=True)
            raise
    
    def get_model(self) -> ChatGoogleGenerativeAI:
        """
        Get the configured Gemini model instance.
        
        Returns:
            ChatGoogleGenerativeAI: The initialized Langchain Gemini model instance
        """
        if not hasattr(self, 'model') or self.model is None:
            logger.error("Model not initialized. Cannot retrieve model instance.")
            raise ValueError("Model not initialized. Please check initialization.")
        
        logger.debug("Retrieving Gemini model instance")
        return self.model
    
    def update_temperature(self, temperature: float):
        """
        Update the temperature setting for the model.
        
        Args:
            temperature (float): New temperature value (0.0 to 1.0)
        """
        try:
            if not (0.0 <= temperature <= 1.0):
                raise ValueError("Temperature must be between 0.0 and 1.0")
            
            logger.info(f"Updating model temperature to {temperature}")
            self.model = ChatGoogleGenerativeAI(
                model=self.model_name,
                google_api_key=self.api_key,
                temperature=temperature,
                convert_system_message_to_human=True
            )
            logger.info(f"Temperature updated successfully to {temperature}")
            
        except Exception as e:
            logger.error(f"Error updating temperature: {str(e)}", exc_info=True)
            raise


def configure_gemini_model(
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: float = 0.7
) -> ChatGoogleGenerativeAI:
    """
    Configure and return a Gemini model instance using Langchain.
    
    This is a convenience function that creates a GeminiModelConfig instance
    and returns the configured model.
    
    Args:
        api_key (str, optional): Google API key. If not provided, uses settings.GOOGLE_API_KEY
        model_name (str, optional): Model name. If not provided, uses settings.GOOGLE_MODEL_NAME
        temperature (float): Temperature setting for the model (default: 0.7)
    
    Returns:
        ChatGoogleGenerativeAI: Configured Gemini model instance
    
    Example:
        >>> model = configure_gemini_model()
        >>> response = model.invoke("Hello, how are you?")
    """
    try:
        logger.info("Configuring Gemini model using configure_gemini_model function")
        
        config = GeminiModelConfig(api_key=api_key, model_name=model_name)
        
        if temperature != 0.7:
            config.update_temperature(temperature)
        
        logger.info("Gemini model configured successfully")
        return config.get_model()
        
    except Exception as e:
        logger.error(f"Error configuring Gemini model: {str(e)}", exc_info=True)
        raise

