"""
Clawback report services (stubbed until data source is available).
"""

from __future__ import annotations

from app.schemas.reports import ClawbackOverviewItem, ClawbackOverviewResponse


def build_overview() -> ClawbackOverviewResponse:
    items = [
        ClawbackOverviewItem(
            job_id=None,
            job_public_id=None,
            candidate_id=None,
            candidate_name=None,
            status="Data source not available",
            notes="Implement when clawback table is ready.",
        )
    ]
    return ClawbackOverviewResponse(items=items, message="Clawback data not available in current schema.")

