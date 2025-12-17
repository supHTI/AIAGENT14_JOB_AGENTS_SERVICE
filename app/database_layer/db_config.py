"""
Database Configuration Module

This module handles database connection setup and configuration
for the Job Service application.

Author: [Supriyo Chowdhury]
Version: 1.0
Last Modified: [2024-05-20]
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core import settings
import logging

logger = logging.getLogger("app_logger")

# Create the SQLAlchemy engine
try:
    engine = create_engine(
        settings.DB_URI,
        echo=settings.DEBUG,  # Set to True for SQL query logging
        pool_pre_ping=True,   # Verify connections before use
        pool_recycle=3600,    # Recycle connections every hour
    )
    logger.info("Database engine created successfully")
except Exception as e:
    logger.error(f"Failed to create database engine: {e}")
    raise

# Create the SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create the Base class for declarative models
Base = declarative_base()

def get_db():
    """
    Dependency function to get database session.
    This function provides a database session and ensures it's properly closed.
    
    Yields:
        Session: SQLAlchemy database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """
    Initialize the database by creating all tables.
    This function should be called when the application starts.
    """
    try:
        # Import all models to ensure they are registered with Base
        from app.database_layer.db_model import User, Role, Session, JobOpenings
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

