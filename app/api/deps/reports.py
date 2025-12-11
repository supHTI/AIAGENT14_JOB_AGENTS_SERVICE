"""
Helper dependencies for report endpoints.
Parses query parameters into ReportFilter and extracts user email from JWT.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import Depends, Query

from app.schemas.reports import ReportFilter
from app.api.deps.auth import get_user_email


def parse_date_filters(
    date_from: Optional[date] = Query(None, description="Start date (inclusive)"),
    date_to: Optional[date] = Query(None, description="End date (inclusive)"),
) -> ReportFilter:
    """Lightweight date-only filter dependency."""
    return ReportFilter(date_from=date_from, date_to=date_to)


def parse_report_filters(
    date_from: Optional[date] = Query(None, description="Start date (inclusive)"),
    date_to: Optional[date] = Query(None, description="End date (inclusive)"),
    job_ids: Optional[str] = Query(None, description="Comma-separated job IDs"),
    job_public_ids: Optional[str] = Query(None, description="Comma-separated public job IDs"),
    company_ids: Optional[str] = Query(None, description="Comma-separated company IDs"),
    pipeline_ids: Optional[str] = Query(None, description="Comma-separated pipeline IDs"),
    pipeline_stage_ids: Optional[str] = Query(None, description="Comma-separated pipeline stage IDs"),
    pipeline_stage_status: Optional[str] = Query(None),
    recruiter_ids: Optional[str] = Query(None, description="Comma-separated recruiter IDs"),
    hr_ids: Optional[str] = Query(None, description="Comma-separated HR IDs"),
    status: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    remote: Optional[bool] = Query(None),
    work_mode: Optional[str] = Query(None),
) -> ReportFilter:
    """
    Parse query parameters into ReportFilter.
    Handles comma-separated list values.
    """
    def _parse_list(value: Optional[str]) -> Optional[list]:
        if not value:
            return None
        try:
            # Try parsing as comma-separated integers
            return [int(x.strip()) for x in value.split(",") if x.strip()]
        except ValueError:
            # If not integers, return as string list
            return [x.strip() for x in value.split(",") if x.strip()]

    def _parse_str_list(value: Optional[str]) -> Optional[list[str]]:
        if not value:
            return None
        return [x.strip() for x in value.split(",") if x.strip()]

    return ReportFilter(
        date_from=date_from,
        date_to=date_to,
        job_ids=_parse_list(job_ids),
        job_public_ids=_parse_str_list(job_public_ids),
        company_ids=_parse_list(company_ids),
        pipeline_ids=_parse_list(pipeline_ids),
        pipeline_stage_ids=_parse_list(pipeline_stage_ids),
        pipeline_stage_status=pipeline_stage_status,
        recruiter_ids=_parse_list(recruiter_ids),
        hr_ids=_parse_list(hr_ids),
        status=status,
        location=location,
        remote=remote,
        work_mode=work_mode,
    )



