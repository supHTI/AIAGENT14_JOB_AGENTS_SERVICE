"""
Pipeline health report services.
"""

from __future__ import annotations

from typing import List

from app.repositories import get_pipeline_velocity, get_pipeline_dropout
from app.schemas.reports import DropoutMetric, DropoutResponse, PipelineVelocityItem, PipelineVelocityResponse, ReportFilter


def build_velocity(db, filters: ReportFilter) -> PipelineVelocityResponse:
    items_raw = get_pipeline_velocity(db, filters)
    items: List[PipelineVelocityItem] = [PipelineVelocityItem(**item) for item in items_raw]
    return PipelineVelocityResponse(items=items)


def build_dropout(db, filters: ReportFilter) -> DropoutResponse:
    items_raw = get_pipeline_dropout(db, filters)
    items: List[DropoutMetric] = [DropoutMetric(**item) for item in items_raw]
    return DropoutResponse(items=items)

