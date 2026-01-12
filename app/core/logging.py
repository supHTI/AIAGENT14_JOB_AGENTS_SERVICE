"""
Logging Configuration Module

This module sets up logging for the entire application. It provides functionality to configure
logging using a YAML file or basic configuration, and includes a custom ContextFilter class
for adding unique run identifiers to log records.

Key components:
- ContextFilter: Custom logging filter for adding run IDs (currently not in use)
- setup_logging: Function to configure logging based on a YAML file or default settings
- Logging configuration using YAML or basic config
- Error handling for logging setup

Dependencies:
- logging: Python's built-in logging module
- yaml: For parsing YAML configuration files
- pathlib: For file path handling
- uuid: For generating unique identifiers
"""

import logging
import logging.config
import os
import yaml
from pathlib import Path
from uuid import uuid4
# from app.core.config_dev  import settings
import os

ENV = os.getenv("APP_ENV", "dev")  # Default to 'dev'

if ENV == "prod":
    from .config_prod import settings
else:
    from .config_dev import settings

class ContextFilter(logging.Filter):
    """
    Custom logging filter to add a unique run identifier to log records.
    
    This class is currently not in use but can be activated to add run IDs to logs.

    Attributes:
        run_id (uuid): A unique identifier for the current run.
    """
    def __init__(self, name='', run_id=None):

        super().__init__(name)
        self.run_id = run_id or uuid4()

    def filter(self, record):
        """
        Adds the run_id to the log record.

        Args:
            record (LogRecord): The log record to be modified.

        Returns:
            bool: Always returns True to include the record in the log.
        """
        record.run_id = self.run_id
        return True
# from app.core import settings
def setup_logging(
    default_path='logging.yaml',
    default_level=logging.DEBUG,
    log_dir=settings.JOB_AGENT_LOG
):
    """
    Sets up logging configuration for the application.

    This function attempts to load a YAML configuration file for logging.
    If the file is not found, it falls back to basic logging configuration.

    Args:
        default_path (str): Path to the YAML logging configuration file.
        default_level (int): Default logging level to use if config file is not found.
        log_dir (str): Directory where logs should be stored.

    Returns:
        None
    """
    try:
        # Ensure the log directory exists
        os.makedirs(log_dir, exist_ok=True)

        # Define the log file's full path
        log_file_path = os.path.join(log_dir, "job_agents_service.log")

        # Load YAML configuration
        path = Path(default_path)
        if path.exists():
            with open(path, 'rt') as f:
                config = yaml.safe_load(f.read())

                # Dynamically update the file handler's filename
                if 'handlers' in config and 'file' in config['handlers']:
                    config['handlers']['file']['filename'] = log_file_path

                # Apply the updated logging configuration
                logging.config.dictConfig(config)
                logging.info(f"Logging configured using YAML file at {path}")
        else:
            # Fallback to basic configuration
            logging.basicConfig(
                level=default_level,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                handlers=[
                    logging.FileHandler(log_file_path),
                    logging.StreamHandler()
                ]
            )
            logging.warning(f"Logging configuration file not found at {path}. Using basic config.")
        
    except Exception as e:
        # Log any errors during setup
        logging.basicConfig(level=default_level)
        logging.error(f"Error occurred during logging setup: {str(e)}", exc_info=True)
log = setup_logging()