"""
Pipeline health report API.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database_layer.db_config import get_db
from app.schemas.reports import (
    DropoutResponse,
    ExportFormat,
    PipelineVelocityResponse,
)
from app.services.exporters import export_with_format
from app.services.reports import build_pipeline_velocity, build_pipeline_dropout
from app.services.emailer import send_report_email
from app.services import email_templates
from app.api.deps.auth import require_report_admin
from app.api.deps.reports import parse_report_filters
from app.api.deps.auth import get_user_email

router = APIRouter(prefix="/reports/pipeline", tags=["reports:pipeline"], dependencies=[Depends(require_report_admin)])


@router.get("/velocity", response_model=PipelineVelocityResponse)
def pipeline_velocity(
    background_tasks: BackgroundTasks,
    export_format: ExportFormat = Query(ExportFormat.pdf, description="xlsx|pdf"),
    filters = Depends(parse_report_filters),
    recipient: str = Depends(get_user_email),
    db: Session = Depends(get_db),
):
    data = build_pipeline_velocity(db, filters)
    items_dict = [item.model_dump() for item in data.items]
    summary_dict = {
        "stages": len(items_dict),
        "avg_hours": sum(i.get("avg_hours", 0) for i in items_dict) / len(items_dict) if items_dict else 0,
        "p50_hours": sum(i.get("p50_hours", 0) for i in items_dict) / len(items_dict) if items_dict else 0,
        "p90_hours": sum(i.get("p90_hours", 0) for i in items_dict) / len(items_dict) if items_dict else 0,
    }
    
    html = email_templates.render_pipeline_email(recipient, summary_dict, "Pipeline Velocity")
    content, filename, mime = export_with_format(
        export_format.value, "pipeline_velocity", summary_dict, items_dict, x_key="stage_name", y_key="avg_hours"
    )
    attachments = [(filename, content, mime)]
    background_tasks.add_task(
        send_report_email,
        "Pipeline Velocity Report",
        html,
        recipient,
        attachments,
    )
    return Response(content=content, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/dropout", response_model=DropoutResponse)
def pipeline_dropout(
    background_tasks: BackgroundTasks,
    export_format: ExportFormat = Query(ExportFormat.pdf, description="xlsx|pdf"),
    filters = Depends(parse_report_filters),
    recipient: str = Depends(get_user_email),
    db: Session = Depends(get_db),
):
    data = build_pipeline_dropout(db, filters)
    items_dict = [item.model_dump() for item in data.items]
    summary_dict = {
        "stages": len(items_dict),
        "avg_hours": 0,
        "p50_hours": 0,
        "p90_hours": 0,
    }
    
    html = email_templates.render_pipeline_email(recipient, summary_dict, "Pipeline Dropout")
    content, filename, mime = export_with_format(
        export_format.value, "pipeline_dropout", summary_dict, items_dict, x_key="stage_name", y_key="dropout_pct"
    )
    attachments = [(filename, content, mime)]
    background_tasks.add_task(
        send_report_email,
        "Pipeline Dropout Report",
        html,
        recipient,
        attachments,
    )
    return Response(content=content, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{filename}"'})

