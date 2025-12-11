"""
Recruiter/HR performance report API.
Includes login activity sourced from the sessions table.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database_layer.db_config import get_db
from app.schemas.reports import ExportFormat, RecruiterPerformanceResponse
from app.services.exporters import export_with_format
from app.services.reports import build_recruiter_performance
from app.services.emailer import send_report_email
from app.services import email_templates
from app.api.deps.auth import require_report_admin
from app.api.deps.reports import parse_report_filters
from app.api.deps.auth import get_user_email

router = APIRouter(prefix="/reports/recruiters", tags=["reports:recruiters"], dependencies=[Depends(require_report_admin)])


@router.get("/performance", response_model=RecruiterPerformanceResponse)
def recruiter_performance(
    background_tasks: BackgroundTasks,
    export_format: ExportFormat = Query(ExportFormat.pdf, description="xlsx|pdf"),
    filters = Depends(parse_report_filters),
    recipient: str = Depends(get_user_email),
    db: Session = Depends(get_db),
):
    data = build_recruiter_performance(db, filters)
    items_dict = [item.model_dump() for item in data.items]
    summary_dict = {
        "total_recruiters": len(items_dict),
        "total_sourced": sum(i.get("sourced", 0) for i in items_dict),
        "total_screened": sum(i.get("screened", 0) for i in items_dict),
        "total_logins": sum(i.get("login_count", 0) for i in items_dict),
    }
    
    html = email_templates.render_recruiter_email(recipient, summary_dict)
    content, filename, mime = export_with_format(
        export_format.value, "recruiter_performance", summary_dict, items_dict, x_key="name", y_key="sourced"
    )
    attachments = [(filename, content, mime)]
    background_tasks.add_task(
        send_report_email,
        "Recruiter Performance Report",
        html,
        recipient,
        attachments,
    )
    return Response(content=content, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{filename}"'})

