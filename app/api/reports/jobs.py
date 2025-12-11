"""
Job report API endpoints.
Supports JSON plus CSV/XLSX/PDF exports and emails every response.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database_layer.db_config import get_db
from app.schemas.reports import ExportFormat, StatusMessage
from app.services.exporters import (
    export_job_details_pdf,
    export_jobs_overview_pdf,
    export_multi_sheet_xlsx,
)
from app.services.reports.jobs import build_job_details_report, build_jobs_overview_report
from app.services.emailer import send_report_email
from app.services import email_templates
from app.api.deps.auth import require_report_admin
from app.api.deps.reports import parse_date_filters
from app.api.deps.auth import get_user_email, validate_token

from app.database_layer.db_model import User

router = APIRouter(prefix="/reports/jobs", tags=["reports:jobs"], dependencies=[Depends(require_report_admin)])


@router.get("/overview", response_model=StatusMessage)
def jobs_overview(
    background_tasks: BackgroundTasks,
    export_format: ExportFormat = Query(ExportFormat.pdf, description="xlsx|pdf"),
    filters = Depends(parse_date_filters),
    recipient: str = Depends(get_user_email),
    user: User = Depends(validate_token),
    db: Session = Depends(get_db),
):
    payload = build_jobs_overview_report(db, filters)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    base_name = f"job_overview_{timestamp}"

    if export_format == ExportFormat.pdf:
        content = export_jobs_overview_pdf(
            "High Tech Infosystems Jobs Overview Report",
            payload["summary_tiles"],
            payload["positions_at_risk"],
            payload["charts"],
            payload["table"],
            generated_by=user.name,
            date_range=(filters.date_from, filters.date_to),
        )
        filename = f"{base_name}.pdf"
        mime = "application/pdf"
    else:
        sheets = {
            "Summary": [{"metric": k, "value": v} for k, v in payload["summary_tiles"]],
            "Positions at risk": payload["positions_at_risk"],
            "Jobs": payload["table"],
            "Jobs per company": payload["charts"].get("jobs_per_company", []),
            "New jobs timeline": payload["charts"].get("new_jobs_daily", []),
            "Candidates per job": payload["charts"].get("candidates_per_job", []),
            "Clawback per job": payload["charts"].get("clawback_per_job", []),
            "Accepted per job": payload["charts"].get("accepted_per_job", []),
        }
        content = export_multi_sheet_xlsx(sheets)
        filename = f"{base_name}.xlsx"
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    email_summary = {k: v for k, v in payload["summary_tiles"]}
    html = email_templates.render_job_overview_email(recipient, email_summary)
    attachments = [(filename, content, mime)]
    try:
        send_report_email("Jobs Overview Report", html, recipient, attachments)
        return StatusMessage(status="success", message="Jobs overview report emailed.")
    except Exception as exc:
        return StatusMessage(status="error", message=f"Email send failed: {exc}")


@router.get("/{job_id}/details", response_model=StatusMessage)
def job_details(
    job_id: int,
    background_tasks: BackgroundTasks,
    export_format: ExportFormat = Query(ExportFormat.pdf, description="xlsx|pdf"),
    filters = Depends(parse_date_filters),
    recipient: str = Depends(get_user_email),
    user: User = Depends(validate_token),
    db: Session = Depends(get_db),
):
    try:
        payload = build_job_details_report(db, job_id, filters)
    except ValueError:
        raise HTTPException(status_code=404, detail="Job not found")
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    job_metadata = payload.get("job_metadata", {})
    job_title = job_metadata.get("job_title", f"Job {job_id}")
    safe_title = job_title.replace(" ", "_")
    base_name = f"{safe_title}_{timestamp}"
    title = f"HTI {job_title} Position Report"

    if export_format == ExportFormat.pdf:
        content = export_job_details_pdf(
            title,
            payload["summary_tiles"],
            payload["stage_flow"],
            payload["stage_times"],
            payload["hr_activities"],
            payload["candidate_rows"],
            payload["funnel"],
            payload["extras"],
            job_metadata=job_metadata,
            generated_by=user.name if user else "",
            date_range=(filters.date_from, filters.date_to),
        )
        filename = f"{base_name}.pdf"
        mime = "application/pdf"
    else:
        sheets = {
            "Summary": [{"metric": k, "value": v} for k, v in payload["summary_tiles"]],
            "Stage flow": payload["stage_flow"],
            "Stage times": payload["stage_times"],
            "HR activities": payload["hr_activities"],
            "Candidates": payload["candidate_rows"],
            "Pipeline velocity": payload["extras"].get("pipeline_velocity", []),
            "Best HR": payload.get("best_hr", []),
        }
        content = export_multi_sheet_xlsx(sheets)
        filename = f"{base_name}.xlsx"
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    html = email_templates.render_job_details_email(recipient, dict(payload["summary_tiles"]))
    attachments = [(filename, content, mime)]
    try:
        send_report_email(title, html, recipient, attachments)
        return StatusMessage(status="success", message="Job details report emailed.")
    except Exception as exc:
        return StatusMessage(status="error", message=f"Email send failed: {exc}")