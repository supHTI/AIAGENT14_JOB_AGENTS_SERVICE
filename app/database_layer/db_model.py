"""
Database Models Module

This module defines the SQLAlchemy ORM models for:
- User: Stores user account information
- Session: Tracks user login sessions
- Role: Stores user roles
- JobOpenings: Stores job posting information
- JobPosts: Stores job post versions and instructions
- Company: Stores company information

The models establish the database schema and relationships.

Author: [Supriyo Chowdhury]
Version: 1.0
Last Modified: [2024-05-20]
"""

from sqlalchemy import Column, DateTime, Integer, String, Boolean, ForeignKey, TIMESTAMP, Text, DECIMAL, Date, SmallInteger, Enum, Index, TypeDecorator
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.mysql import TINYINT, INTEGER as MYSQL_INTEGER, LONGTEXT
from sqlalchemy.orm import relationship
from app.database_layer.db_config import Base
from app.core import settings
import logging
from sqlalchemy.sql import func
from datetime import datetime, timezone
import enum
import logging


logger = logging.getLogger("app_logger")

class Role(Base):
    """Role model for storing user roles"""
    __tablename__ = 'roles'

    logger.info("Configuring Role model fields")
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=True)
    logger.info("Role model configured successfully")
    
class User(Base):
    """User model for storing user account information"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(TIMESTAMP)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    updated_at = Column(TIMESTAMP)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  
    role_id = Column(Integer, ForeignKey('roles.id'), nullable=True, index=True)
    deleted_at = Column(DateTime)
    deleted_by = Column(Integer)

    # Explicit foreign key relationships
    role = relationship("Role", foreign_keys=[role_id])
    logger.info("User model configured successfully")

class Session(Base):
    """Session model for tracking user login sessions"""
    __tablename__ = 'sessions'

    logger.info("Configuring Session model fields")
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    login_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)
    user = relationship("User")
    logger.info("Session model configured successfully")
    
class JobOpenings(Base):
    """Job Openings model for storing job posting information"""
    __tablename__ = 'job_openings'

    logger.info("Configuring JobOpenings model fields")
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # External/public identifier
    job_id = Column(String(100), unique=True, nullable=False, index=True)
    
    # Foreign keys
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False, index=True)
    main_spoc_id = Column(Integer, ForeignKey('company_spoc.id'), nullable=True, index=True)
    internal_spoc_id = Column(Integer, ForeignKey('company_spoc.id'), nullable=True, index=True)
    pipeline_id = Column(Integer, ForeignKey('pipelines.id'), nullable=True, index=True)
    
    # Basic job information
    title = Column(String(150), nullable=False)
    location = Column(String(150), nullable=False)
    deadline = Column(Date, nullable=False)
    job_type = Column(String(50), nullable=False)  # FULL_TIME, PART_TIME, CONTRACT
    remote = Column(TINYINT(1), nullable=False, default=0)  # true/false
    openings = Column(Integer, nullable=False)  # number of vacancies
    work_mode = Column(String(30), nullable=True)  # ONSITE, REMOTE, HYBRID
    status = Column(String(30), nullable=False, default='ACTIVE')
    stage = Column(String(30), nullable=False, default='stage1')
    
    # Salary information
    salary_type = Column(String(30), nullable=True)  # YEARLY, MONTHLY, HOURLY
    currency = Column(String(3), nullable=True)  # ISO-4217
    min_salary = Column(DECIMAL(12, 2), nullable=True)
    max_salary = Column(DECIMAL(12, 2), nullable=True)
    
    # Requirements
    skills_required = Column(Text, nullable=True)
    min_exp = Column(DECIMAL(4, 1), nullable=True)
    max_exp = Column(DECIMAL(4, 1), nullable=True)
    min_age = Column(TINYINT, nullable=True)
    max_age = Column(TINYINT, nullable=True)
    education_qualification = Column(String(120), nullable=True)
    educational_specialization = Column(String(120), nullable=True)
    gender_preference = Column(String(20), nullable=True)
    communication = Column(TINYINT(1), nullable=True)
    cooling_period = Column(DECIMAL(4, 1), nullable=True)  # months
    
    # pipeline_id=Column(Integer, ForeignKey('pipelines.id'), nullable=True, index=True)
    
    # Additional fields
    bulk = Column(TINYINT(1), nullable=True)
    remarks = Column(String(255), nullable=True)
    
    # Audit fields
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    updated_at = Column(DateTime, nullable=True)
    updated_by = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(Integer, nullable=True)
    
    # Relationships (only User relationships since other tables don't exist yet)
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
    
    logger.info("JobOpenings model configured successfully")

class JobPosts(Base):
    """Job Posts model for storing job post versions and instructions"""
    __tablename__ = 'job_posts'

    logger.info("Configuring JobPosts model fields")
    
    # Primary key
    id = Column(MYSQL_INTEGER(unsigned=True), primary_key=True, index=True, autoincrement=True)
    
    # Foreign key to job_openings with CASCADE delete
    job_id = Column(MYSQL_INTEGER(unsigned=True), ForeignKey('job_openings.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Job post identifier
    job_post_id = Column(String(50), nullable=False, index=True)
    
    # Content fields
    instructions = Column(Text, nullable=True)
    ver = Column(Integer, nullable=True, index=True)
    updated_version = Column(Integer, nullable=True, index=True)
    dimension = Column(String(100), nullable=True)
    logo_url = Column(Text, nullable=True)
    type = Column(String(50), nullable=True)
    language = Column(String(100), nullable=True, default='English')
    cta = Column(TINYINT, nullable=True)
    task_id = Column(String(100), nullable=True, index=True)
    status = Column(String(50), nullable=True, default='pending')
    html_text = Column(LONGTEXT, nullable=True)  # Store generated HTML content
    
    # Timestamp fields
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True, index=True)
    
    # Audit fields with foreign keys to users
    created_by = Column(MYSQL_INTEGER(unsigned=True), ForeignKey('users.id'), nullable=False)
    updated_by = Column(MYSQL_INTEGER(unsigned=True), ForeignKey('users.id'), nullable=True)
    deleted_by = Column(MYSQL_INTEGER(unsigned=True), ForeignKey('users.id'), nullable=True)
    
    # Relationships
    job_opening = relationship("JobOpenings", foreign_keys=[job_id])
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
    deleter = relationship("User", foreign_keys=[deleted_by])
    
    logger.info("JobPosts model configured successfully")

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String(64), nullable=False, unique=True)
    company_name = Column(String(255), nullable=False)
    location = Column(String(255), nullable=False)
    city = Column(String(100))
    state = Column(String(100))
    country = Column(String(100))
    industry = Column(String(150), nullable=False)
    employee_count = Column(String(50))
    website = Column(String(2083))
    status = Column(String(50), default="Active")
    remarks = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.now(timezone.utc))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(TIMESTAMP, server_default=func.now(timezone.utc), onupdate=func.now(timezone.utc))
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships to User table for audit fields
    created_by_user = relationship("User", foreign_keys=[created_by])
    updated_by_user = relationship("User", foreign_keys=[updated_by])
    deleted_by_user = relationship("User", foreign_keys=[deleted_by])
    
    
    
class TaskLogs(Base):
    __tablename__ = "task_logs"
 
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(100), nullable=False)
    type = Column(String(100), nullable=False)
    key_id = Column(Integer, nullable=True)
    status = Column(String(50), nullable=True)
    error = Column(String(250), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)