"""
Recruiter/HR performance report API.
Includes login activity sourced from the sessions table.
"""

from __future__ import annotations

from datetime import datetime, date
import io

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database_layer.db_config import get_db
from app.schemas.reports import ExportFormat, RecruiterPerformanceResponse
from app.services.exporters import (
    export_with_format,
    export_recruiters_summary_pdf,
    export_recruiter_performance_pdf,
    export_multi_sheet_xlsx,
)
from app.services.reports.recruiters import (
    build_performance,
    build_recruiters_summary_report,
    build_recruiter_performance_report,
)
from app.services.emailer import send_report_email
from app.services import email_templates
from app.api.deps.auth import require_report_admin, validate_token
from app.api.deps.reports import parse_report_filters
from app.api.deps.auth import get_user_email
from app.database_layer.db_model import User

router = APIRouter(prefix="/reports/recruiters", tags=["reports:recruiters"], dependencies=[Depends(require_report_admin)])


@router.get("/performance", response_model=RecruiterPerformanceResponse)
def recruiter_performance(
    background_tasks: BackgroundTasks,
    export_format: ExportFormat = Query(ExportFormat.pdf, description="xlsx|pdf"),
    filters = Depends(parse_report_filters),
    recipient: str = Depends(get_user_email),
    db: Session = Depends(get_db),
):
    data = build_performance(db, filters)
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


@router.get("/summary")
def recruiters_summary_report(
    from_date: date = Query(..., description="Start date for the report (YYYY-MM-DD)"),
    to_date: date = Query(..., description="End date for the report (YYYY-MM-DD)"),
    export_format: ExportFormat = Query(ExportFormat.pdf, description="xlsx|pdf"),
    user: User = Depends(validate_token),
    db: Session = Depends(get_db),
):
    """
    Recruiters Summary Report - Returns a comprehensive summary of all recruiters with tag-based statuses,
    daily breakdowns, and performance metrics for the specified date range.
    """
    # Validate dates cannot be in the future
    today = date.today()
    if from_date > today:
        raise HTTPException(status_code=400, detail="from_date cannot be a future date")
    if to_date > today:
        raise HTTPException(status_code=400, detail="to_date cannot be a future date")
    if from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date cannot be greater than to_date")
    
    try:
        payload = build_recruiters_summary_report(db, from_date, to_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")
    
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    
    # Determine if it's a daily report
    is_daily = (from_date == to_date)
    if is_daily:
        date_str = from_date.strftime("%Y%m%d")
        base_name = f"recruiters_summary_daily_{date_str}_{timestamp}"
        title = f"HTI Recruiters Summary Report - {from_date.strftime('%d-%m-%Y')}"
    else:
        date_str = f"{from_date.strftime('%Y%m%d')}_{to_date.strftime('%Y%m%d')}"
        base_name = f"recruiters_summary_{date_str}_{timestamp}"
        title = f"HTI Recruiters Summary Report - {from_date.strftime('%d-%m-%Y')} to {to_date.strftime('%d-%m-%Y')}"

    if export_format == ExportFormat.pdf:
        content = export_recruiters_summary_pdf(
            title,
            payload.get("summary_tiles", []),
            payload.get("recruiters_summary", []),
            payload.get("daily_breakdown", []),
            payload.get("charts", {}),
            generated_by=user.name if user else "",
            date_range=(from_date, to_date),
        )
        filename = f"{base_name}.pdf"
        mime = "application/pdf"
    elif export_format == ExportFormat.xlsx:
        # Excel export
        sheets = {
            "Summary": [{"metric": k, "value": v} for k, v in payload.get("summary_tiles", [])],
            "Recruiters Summary": payload.get("recruiters_summary", []),
            "Daily Breakdown": payload.get("daily_breakdown", []),
            "Daily Status Trends": payload.get("charts", {}).get("daily_status_trends", []),
            "Daily Joined vs Rejected": payload.get("charts", {}).get("daily_joined_rejected", []),
            "Top Recruiters Performance": payload.get("charts", {}).get("top_recruiters_performance", []),
            "Recruiter Efficiency": payload.get("charts", {}).get("recruiter_efficiency", []),
            "Activity Distribution": payload.get("charts", {}).get("activity_distribution", []),
            "Performance Comparison": payload.get("charts", {}).get("performance_comparison", []),
            "Conversion Rates": payload.get("charts", {}).get("conversion_rates", []),
        }
        content = export_multi_sheet_xlsx(sheets)
        filename = f"{base_name}.xlsx"
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported export format: {export_format}")

    return StreamingResponse(
        io.BytesIO(content),
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/performance/{recruiter_id}")
def recruiter_performance_report(
    recruiter_id: int,
    from_date: date = Query(..., description="Start date for the report (YYYY-MM-DD)"),
    to_date: date = Query(..., description="End date for the report (YYYY-MM-DD)"),
    export_format: ExportFormat = Query(ExportFormat.pdf, description="xlsx|pdf"),
    user: User = Depends(validate_token),
    db: Session = Depends(get_db),
):
    """
    Individual Recruiter Performance Report - Returns detailed performance metrics for a specific recruiter
    including tag-based statuses, job assignments, and daily breakdowns for the specified date range.
    """
    # Validate dates cannot be in the future
    today = date.today()
    if from_date > today:
        raise HTTPException(status_code=400, detail="from_date cannot be a future date")
    if to_date > today:
        raise HTTPException(status_code=400, detail="to_date cannot be a future date")
    if from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date cannot be greater than to_date")
    
    try:
        payload = build_recruiter_performance_report(db, recruiter_id, from_date, to_date)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")
    
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    recruiter_name = payload.get("recruiter_metadata", {}).get("recruiter_name", f"Recruiter_{recruiter_id}")
    
    # Determine if it's a daily report
    is_daily = (from_date == to_date)
    if is_daily:
        date_str = from_date.strftime("%Y%m%d")
        base_name = f"recruiter_performance_{recruiter_id}_{date_str}_{timestamp}"
        title = f"HTI Recruiter Performance Report - {recruiter_name} - {from_date.strftime('%d-%m-%Y')}"
    else:
        date_str = f"{from_date.strftime('%Y%m%d')}_{to_date.strftime('%Y%m%d')}"
        base_name = f"recruiter_performance_{recruiter_id}_{date_str}_{timestamp}"
        title = f"HTI Recruiter Performance Report - {recruiter_name} - {from_date.strftime('%d-%m-%Y')} to {to_date.strftime('%d-%m-%Y')}"

    if export_format == ExportFormat.pdf:
        content = export_recruiter_performance_pdf(
            title,
            payload.get("summary_tiles", []),
            payload.get("recruiter_metadata", {}),
            payload.get("jobs_assigned", []),
            payload.get("daily_breakdown", []),
            payload.get("recruiter_activity_details", []),
            payload.get("login_logs", []),
            payload.get("charts", {}),
            generated_by=user.name if user else "",
            date_range=(from_date, to_date),
        )
        filename = f"{base_name}.pdf"
        mime = "application/pdf"
    elif export_format == ExportFormat.xlsx:
        # Excel export
        sheets = {
            "Summary": [{"metric": k, "value": v} for k, v in payload.get("summary_tiles", [])],
            "Jobs Assigned": payload.get("jobs_assigned", []),
            "Daily Breakdown": payload.get("daily_breakdown", []),
            "Daily Status Trends": payload.get("charts", {}).get("daily_status_trends", []),
            "Daily Joined vs Rejected": payload.get("charts", {}).get("daily_joined_rejected", []),
            "Jobs Performance": payload.get("charts", {}).get("jobs_performance", []),
            "Recruiter Activity Details": payload.get("recruiter_activity_details", []),
            "Login Logs": payload.get("login_logs", []),
        }
        content = export_multi_sheet_xlsx(sheets)
        filename = f"{base_name}.xlsx"
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported export format: {export_format}")

    return StreamingResponse(
        io.BytesIO(content),
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

