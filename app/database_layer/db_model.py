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

from sqlalchemy import Column, DateTime, Integer, String, Boolean, ForeignKey, TIMESTAMP, Text, DECIMAL, Date, SmallInteger, Enum, Index, TypeDecorator, UniqueConstraint
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
    created_at = Column(TIMESTAMP, server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  
    role_id = Column(Integer, ForeignKey('roles.id'), nullable=True, index=True)
    deleted_at = Column(DateTime)
    deleted_by = Column(Integer)
    enable = Column(SmallInteger, nullable=False, default=1)

    # Explicit foreign key relationships
    role = relationship("Role", foreign_keys=[role_id])
    logger.info("User model configured successfully")




# ---------------------------------------------------------
# NOTIFICATION USERS
# ---------------------------------------------------------

class NotificationUser(Base):
    __tablename__ = "notification_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    created_by = Column(Integer, nullable=False)

    user = relationship("User", backref="notification_users")

class UserJobsAssigned(Base):
    """Mapping users assigned to specific job openings"""
    __tablename__ = 'user_jobs_assigned'
    __table_args__ = (
        UniqueConstraint('job_id', 'user_id', name='uq_job_user'),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey('job_openings.id'), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    assigned_at = Column(TIMESTAMP, server_default=func.now())

    job = relationship("JobOpenings", foreign_keys=[job_id])
    user = relationship("User", foreign_keys=[user_id])
    logger.info("UserJobsAssigned model configured successfully")

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


class JDStatus(enum.Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"


class JD(Base):
    """Model for storing job descriptions"""
    __tablename__ = 'job_descriptions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    jd_id = Column(String(255), nullable=False)  # public job reference
    jd_version = Column(Integer, nullable=False, default=1)
    update_version = Column(Integer, nullable=False, default=1)
    job_id = Column(Integer, ForeignKey("job_openings.id"), nullable=True)
    status = Column(SAEnum(JDStatus, name="jd_status"), nullable=False, default=JDStatus.ACTIVE)
    position = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=True)
    location = Column(String(255), nullable=False)
    jd = Column(Text, nullable=False)
    created_on = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = Column(DateTime, nullable=True, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    user_id = Column(Integer, nullable=False)
    enhanced_jd = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    updated_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    deleted_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    deleted_on = Column(DateTime, nullable=True)
    
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
    updated_at = Column(DateTime, nullable=True, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
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
    spocs = relationship("CompanySpoc", back_populates="company")
    

    
class TaskLogs(Base):
    __tablename__ = "task_logs"
 
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(100), nullable=False)
    type = Column(String(100), nullable=False)
    key_id = Column(Integer, nullable=True)
    status = Column(String(50), nullable=True)
    error = Column(String(250), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class CompanySpoc(Base):
    """Company point-of-contact details"""
    __tablename__ = "company_spoc"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    spoc_name = Column(String(150), nullable=True)
    spoc_email = Column(String(254), nullable=True)
    spoc_ph_number = Column(String(20), nullable=True)
    escalation_matrix = Column(Integer, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, nullable=True)

    company = relationship("Company", foreign_keys=[company_id], back_populates="spocs")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
    deleter = relationship("User", foreign_keys=[deleted_by])
    logger.info("CompanySpoc model configured successfully")


class Candidates(Base):
    """Candidate master data"""
    __tablename__ = "candidates"
    __table_args__ = (
        UniqueConstraint("candidate_email", "candidate_phone_number", name="unique_email_phone"),
    )

    candidate_id = Column(String(50), primary_key=True)
    candidate_email = Column(String(255), nullable=True)
    candidate_name = Column(String(255), nullable=True)
    candidate_phone_number = Column(String(100), nullable=True)
    creation_source = Column(String(20), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    job_profile = Column(String(255), nullable=True)
    candidate_linkedIn = Column(String(255), nullable=True)
    portfolio = Column(String(255), nullable=True)
    experience = Column(DECIMAL(4, 2), nullable=True)
    home_town = Column(String(255), nullable=True)
    current_location = Column(String(255), nullable=True)
    preferred_location = Column(String(255), nullable=True)
    current_salary = Column(DECIMAL(15, 2), nullable=True)
    current_salary_curr = Column(String(10), nullable=True)
    expected_salary = Column(DECIMAL(15, 2), nullable=True)
    expected_salary_curr = Column(String(10), nullable=True)
    employment_status = Column(String(50), nullable=True)
    employment_type = Column(String(50), nullable=True)
    current_work_mode = Column(String(50), nullable=True)
    skills = Column(Text, nullable=True)
    dob = Column(Date, nullable=True)
    age = Column(Integer, nullable=True)
    on_notice = Column(TINYINT(1), nullable=True, default=0)
    available_from = Column(Date, nullable=True)
    year_of_graduation = Column(SmallInteger, nullable=True)
    work_mode_prefer = Column(String(50), nullable=True)
    profile_source = Column(String(100), nullable=True)
    employment_gap = Column(String(100), nullable=True)
    industries_worked_on = Column(Text, nullable=True)
    gender = Column(String(10), nullable=True)
    current_company = Column(String(255), nullable=True)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)

    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
    assignee = relationship("User", foreign_keys=[assigned_to])
    logger.info("Candidates model configured successfully")


class CandidateStatus(Base):
    """Latest status per candidate"""
    __tablename__ = "candidate_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(String(50), ForeignKey("candidates.candidate_id", ondelete="CASCADE"), nullable=False, unique=True)
    candidate_status = Column(Text, nullable=False)
    remarks = Column(Text, nullable=True)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    candidate = relationship("Candidates", foreign_keys=[candidate_id])
    logger.info("CandidateStatus model configured successfully")


class CandidateActivityType(enum.Enum):
    general = "general"
    pipeline = "pipeline"
    accepted = "accepted"
    status = "status"


class CandidateActivity(Base):
    """Activity log per candidate"""
    __tablename__ = "candidate_activity"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(String(50), ForeignKey("candidates.candidate_id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False, index=True)
    remark = Column(Text, nullable=True)
    type = Column(SAEnum(CandidateActivityType), nullable=False)
    key_id = Column(String(100), nullable=False, default="100")
    created_at = Column(TIMESTAMP, server_default=func.now(), index=True)
    
    candidate = relationship("Candidates", foreign_keys=[candidate_id])
    user = relationship("User", foreign_keys=[user_id])
    logger.info("CandidateActivity model configured successfully")


class CandidateJobs(Base):
    """Mapping candidates to jobs"""
    __tablename__ = "candidate_jobs"
    __table_args__ = (
        UniqueConstraint("job_id", "candidate_id", name="uq_job_candidate"),
    )

    id = Column(MYSQL_INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    job_id = Column(MYSQL_INTEGER(unsigned=True), ForeignKey("job_openings.id"), nullable=False, index=True)
    candidate_id = Column(String(50), ForeignKey("candidates.candidate_id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    job = relationship("JobOpenings", foreign_keys=[job_id])
    candidate = relationship("Candidates", foreign_keys=[candidate_id])
    creator = relationship("User", foreign_keys=[created_by])
    logger.info("CandidateJobs model configured successfully")


class CandidateJobStatusType(enum.Enum):
    joined = "joined"
    rejected = "rejected"
    dropped = "dropped"


class CandidateJobStatus(Base):
    """Lifecycle status for a candidate-job mapping"""
    __tablename__ = "candidate_job_status"

    id = Column(MYSQL_INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    candidate_job_id = Column(MYSQL_INTEGER(unsigned=True), ForeignKey("candidate_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(SAEnum(CandidateJobStatusType), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    joined_at = Column(DateTime, nullable=True, index=True)
    rejected_at = Column(DateTime, nullable=True, index=True)
    cooling_period_closed = Column(DateTime, nullable=True)
    candidate_job = relationship("CandidateJobs", foreign_keys=[candidate_job_id])
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
    logger.info("CandidateJobStatus model configured successfully")


class CandidatePipelineStatus(Base):
    """Tracks pipeline stage per candidate-job"""
    __tablename__ = "candidate_pipeline_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_job_id = Column(MYSQL_INTEGER(unsigned=True), ForeignKey("candidate_jobs.id"), nullable=False, index=True)
    pipeline_stage_id = Column(Integer, ForeignKey("pipeline_stages.id"), nullable=False, index=True)
    status = Column(String(100), nullable=True)
    latest = Column(TINYINT(1), nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    candidate_job = relationship("CandidateJobs", foreign_keys=[candidate_job_id])
    creator = relationship("User", foreign_keys=[created_by])
    pipeline_stage = relationship("PipelineStage", foreign_keys=[pipeline_stage_id])
    logger.info("CandidatePipelineStatus model configured successfully")


class Pipeline(Base):
    """Pipeline header"""
    __tablename__ = "pipelines"

    id = Column(Integer, primary_key=True, index=True)
    pipeline_id = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(100))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer, nullable=True)
    updated_at = Column(DateTime, nullable=True, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    updated_by = Column(Integer, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(Integer, nullable=True)
    remarks = Column(Text)


class PipelineStage(Base):
    """Stages within a pipeline"""
    __tablename__ = "pipeline_stages"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(String(255))
    color_code = Column(String(10))
    order = Column(Integer, nullable=False)
    end_stage = Column(Boolean, default=False)
    pipeline_id = Column(Integer, ForeignKey("pipelines.id"), nullable=False)

    stage_statuses = relationship("PipelineStageStatus", back_populates="pipeline_stage")


class PipelineStageStatus(Base):
    """Selectable status options per pipeline stage"""
    __tablename__ = "pipeline_stage_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pipeline_stage_id = Column(Integer, ForeignKey("pipeline_stages.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False)
    option = Column(String(100))
    color_code = Column(String(20))
    order = Column(Integer)

    pipeline_stage = relationship("PipelineStage", back_populates="stage_statuses")


class PipelineStageSpoc(Base):
    """Assign SPOC to a pipeline stage for a job"""
    __tablename__ = "pipeline_stage_spoc"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(100), nullable=False, index=True)  # public job id
    pipeline_stage_id = Column(Integer, ForeignKey("pipeline_stages.id"), nullable=False, index=True)
    spoc_id = Column(Integer, ForeignKey("company_spoc.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, nullable=True, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint("job_id", "pipeline_stage_id", name="uq_job_stage_spoc"),)

    stage = relationship("PipelineStage")
    spoc = relationship("CompanySpoc")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

# Performance-oriented indexes for frequent report queries
Index("ix_sessions_user_login", Session.user_id, Session.login_at)
Index("ix_candidate_activity_type_created", CandidateActivity.type, CandidateActivity.created_at)
Index("ix_candidate_job_status_type_created", CandidateJobStatus.type, CandidateJobStatus.created_at)
Index(
    "ix_candidate_pipeline_latest",
    CandidatePipelineStatus.candidate_job_id,
    CandidatePipelineStatus.pipeline_stage_id,
    CandidatePipelineStatus.latest,
)
