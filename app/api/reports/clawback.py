"""
Clawback overview API (stub).
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database_layer.db_config import get_db
from app.schemas.reports import ClawbackOverviewResponse, ExportFormat
from app.services.exporters import export_with_format
from app.services.reports import build_clawback_overview
from app.services.emailer import send_report_email
from app.services import email_templates
from app.api.deps.auth import require_report_admin
from app.api.deps.reports import parse_report_filters
from app.api.deps.auth import get_user_email

router = APIRouter(prefix="/reports/clawbacks", tags=["reports:clawbacks"], dependencies=[Depends(require_report_admin)])


@router.get("/overview", response_model=ClawbackOverviewResponse)
def clawback_overview(
    background_tasks: BackgroundTasks,
    export_format: ExportFormat = Query(ExportFormat.pdf, description="xlsx|pdf"),
    filters = Depends(parse_report_filters),
    recipient: str = Depends(get_user_email),
    db: Session = Depends(get_db),
):
    _ = db  # unused placeholder until clawback data source is available
    _ = filters  # unused placeholder
    data = build_clawback_overview()
    items_dict = [item.model_dump() for item in data.items]
    summary_dict = {"cases": len(items_dict), "recovered": 0, "pending": len(items_dict)}
    
    html = email_templates.render_clawback_email(recipient, summary_dict)
    content, filename, mime = export_with_format(
        export_format.value, "clawback_overview", summary_dict, items_dict, x_key="candidate_id", y_key="status"
    )
    attachments = [(filename, content, mime)]
    background_tasks.add_task(
        send_report_email,
        "Clawback Overview Report",
        html,
        recipient,
        attachments,
    )
    return Response(content=content, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{filename}"'})

