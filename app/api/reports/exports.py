"""
Consolidated export endpoint to deliver reports in CSV/XLSX/PDF and email them.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.database_layer.db_config import get_db
from app.schemas.reports import ExportRequest, ReportFilter
from app.services.exporters import export_with_format
from app.services.reports import (
    build_job_overview,
    build_job_funnel,
    build_recruiter_performance,
    build_pipeline_velocity,
    build_pipeline_dropout,
    build_clawback_overview,
)
from app.services.emailer import send_report_email
from app.services import email_templates
from app.api.deps.auth import require_report_admin, get_user_email

router = APIRouter(prefix="/reports", tags=["reports:exports"], dependencies=[Depends(require_report_admin)])


@router.post("/exports")
def export_report(
    payload: ExportRequest,
    background_tasks: BackgroundTasks,
    recipient: str = Depends(get_user_email),
    db: Session = Depends(get_db),
):
    fmt = payload.format.value
    filters = payload.filters or ReportFilter()

    report_type = payload.report_type
    title = report_type.replace("_", " ").title()
    summary = {}
    items = []
    template_html = ""
    export_kwargs = {"x_key": "title", "y_key": "openings"}

    if report_type in {"daily", "monthly", "jobs_overview", "job"}:
        data = build_job_overview(db, filters)
        summary = data.summary.model_dump()
        items = [i.model_dump() for i in data.items]
        template_html = email_templates.render_job_overview_email(recipient, summary)
        export_kwargs = {"x_key": "title", "y_key": "openings"}
    elif report_type in {"job_funnel", "funnel"}:
        if not payload.job_id:
            raise HTTPException(status_code=400, detail="job_id is required for funnel exports.")
        data = build_job_funnel(db, payload.job_id, filters)
        summary = data.model_dump()
        items = [summary]
        template_html = email_templates.render_job_funnel_email(recipient, summary)
        export_kwargs = {"x_key": "job_public_id", "y_key": "sourced"}
        title = f"Job {payload.job_id} Funnel"
    elif report_type in {"hr", "recruiter", "top_hr"}:
        data = build_recruiter_performance(db, filters)
        items = [i.model_dump() for i in data.items]
        summary = {
            "total_recruiters": len(items),
            "total_sourced": sum(i.get("sourced", 0) for i in items),
            "total_screened": sum(i.get("screened", 0) for i in items),
            "total_logins": sum(i.get("login_count", 0) for i in items),
        }
        template_html = email_templates.render_recruiter_email(recipient, summary)
        export_kwargs = {"x_key": "name", "y_key": "sourced"}
    elif report_type in {"pipeline_velocity", "pipeline"}:
        data = build_pipeline_velocity(db, filters)
        items = [i.model_dump() for i in data.items]
        summary = {
            "stages": len(items),
            "avg_hours": sum(i.get("avg_hours", 0) for i in items) / len(items) if items else 0,
            "p50_hours": sum(i.get("p50_hours", 0) for i in items) / len(items) if items else 0,
            "p90_hours": sum(i.get("p90_hours", 0) for i in items) / len(items) if items else 0,
        }
        template_html = email_templates.render_pipeline_email(recipient, summary, "Pipeline Velocity")
        export_kwargs = {"x_key": "stage_name", "y_key": "avg_hours"}
    elif report_type in {"pipeline_dropout", "dropout"}:
        data = build_pipeline_dropout(db, filters)
        items = [i.model_dump() for i in data.items]
        summary = {"stages": len(items), "avg_hours": 0, "p50_hours": 0, "p90_hours": 0}
        template_html = email_templates.render_pipeline_email(recipient, summary, "Pipeline Dropout")
        export_kwargs = {"x_key": "stage_name", "y_key": "dropout_pct"}
    elif report_type in {"clawback"}:
        data = build_clawback_overview()
        items = [i.model_dump() for i in data.items]
        summary = {"cases": len(items), "recovered": 0, "pending": len(items)}
        template_html = email_templates.render_clawback_email(recipient, summary)
        export_kwargs = {"x_key": "candidate_id", "y_key": "status"}
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported report_type {report_type}")

    content, filename, mime = export_with_format(fmt, title, summary, items, **export_kwargs)
    background_tasks.add_task(
        send_report_email,
        f"{title} Report",
        template_html,
        recipient,
        [(filename, content, mime)],
    )
    return Response(content=content, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{filename}"'})

