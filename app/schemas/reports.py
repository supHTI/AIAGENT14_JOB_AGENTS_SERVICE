"""
Pydantic schemas for reporting endpoints.
These schemas capture filters, DTOs, and export request payloads for the report APIs.
"""

from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, EmailStr


class ExportFormat(str, Enum):
    """
    Supported export formats for report delivery.
    JSON/CSV were deprecated to simplify output options.
    """

    xlsx = "xlsx"
    pdf = "pdf"


class ReportFilter(BaseModel):
    date_from: Optional[date] = Field(None, description="Start date (inclusive)")
    date_to: Optional[date] = Field(None, description="End date (inclusive)")
    job_ids: Optional[List[int]] = Field(None, description="Comma-separated job IDs")
    job_public_ids: Optional[List[str]] = Field(None, description="Comma-separated public job IDs")
    company_ids: Optional[List[int]] = Field(None, description="Comma-separated company IDs")
    pipeline_ids: Optional[List[int]] = Field(None, description="Comma-separated pipeline IDs")
    pipeline_stage_ids: Optional[List[int]] = Field(None, description="Comma-separated pipeline stage IDs")
    pipeline_stage_status: Optional[str] = None
    recruiter_ids: Optional[List[int]] = Field(None, description="Comma-separated recruiter IDs")
    hr_ids: Optional[List[int]] = Field(None, description="Comma-separated HR IDs")
    status: Optional[str] = None
    location: Optional[str] = None
    remote: Optional[bool] = None
    work_mode: Optional[str] = None


class JobOverviewItem(BaseModel):
    job_id: int
    job_public_id: str
    title: str
    openings: int
    aging_days: int
    created_at: datetime
    status: str


class JobOverviewSummary(BaseModel):
    total_open_positions: int
    total_jobs: int
    avg_aging_days: float
    new_jobs: int


class JobOverviewResponse(BaseModel):
    summary: JobOverviewSummary
    items: List[JobOverviewItem]


class FunnelMetrics(BaseModel):
    job_id: int
    job_public_id: str
    sourced: int
    screened: int
    offers: int
    joins: int
    join_ratio: float


class RecruiterPerformanceItem(BaseModel):
    user_id: int
    name: Optional[str]
    sourced: int
    screened: int
    moves: int
    offers: int
    joins: int
    join_ratio: float
    login_count: int
    last_login_at: Optional[datetime]


class RecruiterPerformanceResponse(BaseModel):
    items: List[RecruiterPerformanceItem]


class PipelineVelocityItem(BaseModel):
    job_id: int
    pipeline_stage_id: int
    stage_name: Optional[str]
    avg_hours: float
    p50_hours: float
    p90_hours: float


class PipelineVelocityResponse(BaseModel):
    items: List[PipelineVelocityItem]


class DropoutMetric(BaseModel):
    pipeline_stage_id: int
    stage_name: Optional[str]
    entrants: int
    exits: int
    dropout_pct: float


class DropoutResponse(BaseModel):
    items: List[DropoutMetric]


class ClawbackOverviewItem(BaseModel):
    job_id: Optional[int]
    job_public_id: Optional[str]
    candidate_id: Optional[str]
    candidate_name: Optional[str]
    status: str
    notes: Optional[str] = None


class ClawbackOverviewResponse(BaseModel):
    items: List[ClawbackOverviewItem]
    message: Optional[str] = None


class ExportRequest(BaseModel):
    report_type: str = Field(..., description="daily|monthly|hr|job|top_hr|custom")
    format: ExportFormat = Field(..., description="xlsx|pdf")
    filters: Optional[ReportFilter] = None
    job_id: Optional[int] = None


class StatusMessage(BaseModel):
    status: str = Field(..., description="success|error")
    message: str

