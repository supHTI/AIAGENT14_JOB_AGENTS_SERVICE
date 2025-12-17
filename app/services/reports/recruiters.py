"""
Recruiter/HR performance report services.
"""

from __future__ import annotations

from typing import List

from app.repositories import get_recruiter_performance
from app.schemas.reports import RecruiterPerformanceItem, RecruiterPerformanceResponse, ReportFilter


def build_performance(db, filters: ReportFilter) -> RecruiterPerformanceResponse:
    items_raw = get_recruiter_performance(db, filters)
    items: List[RecruiterPerformanceItem] = [RecruiterPerformanceItem(**item) for item in items_raw]
    return RecruiterPerformanceResponse(items=items)

