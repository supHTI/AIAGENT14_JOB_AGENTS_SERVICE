"""
Job report API endpoints.
Exports PDF/XLSX and returns the file directly.
"""

from __future__ import annotations

from datetime import datetime, date
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database_layer.db_config import get_db
from app.schemas.reports import ExportFormat, ReportFilter
from app.services.exporters import (
    export_job_details_pdf,
    export_jobs_overview_pdf,
    export_jobs_summary_pdf,
    export_multi_sheet_xlsx,
)
from app.services.reports.jobs import build_job_details_report, build_job_daily_report, build_jobs_overview_report, build_jobs_summary_report, build_jobs_summary_report
from app.api.deps.auth import require_report_admin
from app.api.deps.reports import parse_date_filters
from app.api.deps.auth import validate_token

from app.database_layer.db_model import (
    User,
    CandidatePipelineStatus,
    PipelineStageStatus,
    PipelineStageStatusTag,
    CandidateJobs,
)
from sqlalchemy import func, and_
from datetime import timedelta

router = APIRouter(prefix="/reports/jobs", tags=["reports:jobs"], dependencies=[Depends(require_report_admin)])


@router.get("/overview")
def jobs_overview(
    export_format: ExportFormat = Query(ExportFormat.pdf, description="xlsx|pdf"),
    filters = Depends(parse_date_filters),
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
        job_summary_sheet = [
            {
                "Job Public ID": row.get("job_public_id") or row.get("job_id"),
                "Job Title": row.get("title"),
                "Company Name": row.get("company_name"),
                "Main SPOC": row.get("main_spoc_name") or row.get("main_spoc_id"),
                "Internal SPOC": row.get("internal_spoc_name") or row.get("internal_spoc_id"),
                "Pipeline Name": row.get("pipeline_name") or "-",
                "Location": row.get("location"),
                "Deadline": row.get("deadline"),
                "Job Type": row.get("job_type"),
                "Remote": bool(row.get("remote")),
                "Openings": row.get("openings", 0),
                "Closed": row.get("joined_count", 0),
                "Work Mode": row.get("work_mode"),
                "Status": row.get("status"),
                "Salary Type": row.get("salary_type"),
                "Currency": row.get("currency"),
                "Min Salary": row.get("min_salary"),
                "Max Salary": row.get("max_salary"),
                "Skills Required": row.get("skills_required"),
                "Min Exp": row.get("min_exp"),
                "Max Exp": row.get("max_exp"),
                "Min Age": row.get("min_age"),
                "Max Age": row.get("max_age"),
                "Education Qualification": row.get("education_qualification"),
                "Educational Specialization": row.get("educational_specialization"),
                "Gender Preference": row.get("gender_preference"),
                "Communication": bool(row.get("communication")),
                "Cooling Period": row.get("cooling_period"),
                "Bulk": bool(row.get("bulk")),
                "Remarks": row.get("remarks"),
                "Created At": row.get("created_at"),
                "Updated At": row.get("updated_at"),
                "Deleted At": row.get("deleted_at"),
                "Created By": row.get("created_by_name") or row.get("created_by"),
                "Updated By": row.get("updated_by_name") or row.get("updated_by"),
                "Deleted By": row.get("deleted_by"),
                "Total Candidates": row.get("candidate_count", 0),
                "Total Users": row.get("total_users", 0),
                "Days Remaining": row.get("days_remaining"),
            }
            for row in payload["table"]
        ]

        jobs_at_risk_sheet = [
            {
                "Job ID": row.get("job_public_id") or row.get("job_id"),
                "Job Title": row.get("title"),
                "Company Name": row.get("company_name"),
                "Openings": row.get("openings", 0),
                "Closed": row.get("joined_count", 0),
                "Deadline": row.get("deadline"),
                "Days Remaining": row.get("days_remaining"),
                "Status": row.get("status"),
            }
            for row in payload["positions_at_risk"]
        ]

        sheets = {
            "Summary": [{"metric": k, "value": v} for k, v in payload["summary_tiles"]],
            "Job Summary": job_summary_sheet,
            "Jobs at risk": jobs_at_risk_sheet,
            "Jobs per company": payload["charts"].get("jobs_per_company", []),
            "New jobs timeline": payload["charts"].get("new_jobs_daily", []),
            "Candidates per job": payload["charts"].get("candidates_per_job", []),
            "Clawback per job": payload["charts"].get("clawback_per_job", []),
            "Accepted per job": payload["charts"].get("accepted_per_job", []),
        }
        content = export_multi_sheet_xlsx(sheets)
        filename = f"{base_name}.xlsx"
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return StreamingResponse(
        io.BytesIO(content),
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{job_id}/details")
def job_details(
    job_id: int,
    export_format: ExportFormat = Query(ExportFormat.pdf, description="xlsx|pdf"),
    filters = Depends(parse_date_filters),
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
        # Stage flow without color codes and with joined/rejected counts
        stage_flow_sheet = [{k: v for k, v in row.items() if k != "color_code"} for row in payload["stage_flow"]]

        # HR activities detailed
        hr_activities_sheet = [
            {
                "HR Name": row.get("hr_name"),
                "Activity": row.get("activity_type"),
                "Candidate ID": row.get("candidate_id"),
                "Candidate Name": row.get("candidate_name"),
                "Remarks": row.get("remarks"),
                "When (IST)": row.get("created_at"),
            }
            for row in payload["extras"].get("hr_activity_details", [])
        ]

        # Candidates with HR name and latest remark
        candidates_sheet = [
            {
                "Candidate ID": row.get("candidate_id"),
                "Candidate Name": row.get("candidate_name"),
                "Phone": row.get("candidate_phone_number"),
                "Stage": row.get("stage_name"),
                "Status": row.get("status"),
                "HR Name": row.get("hr_name"),
                "Latest Remark": row.get("latest_remark"),
            }
            for row in payload["candidate_rows"]
        ]

        # Recruiter Ranking sheet with updated field names
        recruiter_ranking_sheet = [
            {
                "Recruiter Name": row.get("recruiter_name"),
                "Candidates": row.get("candidates", 0),
                "Joined": row.get("joined", 0),
                "Rejected": row.get("rejected", 0),
                "Active": "Yes" if row.get("active", False) else "No",
            }
            for row in payload.get("best_hr", [])
        ]

        sheets = {
            "Summary": [{"metric": k, "value": v} for k, v in payload["summary_tiles"]],
            "Stage flow": stage_flow_sheet,
            "Stage times": payload["stage_times"],
            "HR activities": hr_activities_sheet,
            "Candidates": candidates_sheet,
            "Pipeline velocity": payload["extras"].get("pipeline_velocity", []),
            "Recruiter Ranking": recruiter_ranking_sheet,
        }
        content = export_multi_sheet_xlsx(sheets)
        filename = f"{base_name}.xlsx"
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return StreamingResponse(
        io.BytesIO(content),
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{job_id}/daily")
def job_daily_report(
    job_id: int,
    from_date: date = Query(..., description="Start date for the report (YYYY-MM-DD)"),
    to_date: date = Query(..., description="End date for the report (YYYY-MM-DD)"),
    export_format: ExportFormat = Query(ExportFormat.pdf, description="xlsx|pdf"),
    user: User = Depends(validate_token),
    db: Session = Depends(get_db),
):
    """
    Job Report - Returns a report exactly like job_details but filtered for a date range.
    Shows all activities and records from the start of from_date to the end of to_date.
    If from_date == to_date, it's a daily report.
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
        payload = build_job_daily_report(db, job_id, from_date, to_date)
    except ValueError:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Create filters for the date range
    filters = ReportFilter(date_from=from_date, date_to=to_date)
    
    summary_tiles = payload.get("summary_tiles", [])
    
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    job_metadata = payload.get("job_metadata", {})
    job_title = job_metadata.get("job_title", f"Job {job_id}")
    safe_title = job_title.replace(" ", "_")
    
    # Determine if it's a daily report
    is_daily = (from_date == to_date)
    if is_daily:
        date_str = from_date.strftime("%Y%m%d")
        base_name = f"{safe_title}_daily_{date_str}_{timestamp}"
        title = f"HTI {job_title} Report of Date {from_date.strftime('%d-%m-%Y')}"
    else:
        date_str = f"{from_date.strftime('%Y%m%d')}_{to_date.strftime('%Y%m%d')}"
        base_name = f"{safe_title}_report_{date_str}_{timestamp}"
        title = f"HTI {job_title} Report from {from_date.strftime('%d-%m-%Y')} to {to_date.strftime('%d-%m-%Y')}"

    if export_format == ExportFormat.pdf:
        content = export_job_details_pdf(
            title,
            summary_tiles,
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
        # Stage flow without color codes and with joined/rejected counts
        stage_flow_sheet = [{k: v for k, v in row.items() if k != "color_code"} for row in payload["stage_flow"]]

        # HR activities detailed
        hr_activities_sheet = [
            {
                "HR Name": row.get("hr_name"),
                "Activity": row.get("activity_type"),
                "Candidate ID": row.get("candidate_id"),
                "Candidate Name": row.get("candidate_name"),
                "Remarks": row.get("remarks"),
                "When (IST)": row.get("created_at"),
            }
            for row in payload["extras"].get("hr_activity_details", [])
        ]

        # Candidates with HR name and latest remark
        candidates_sheet = [
            {
                "Candidate ID": row.get("candidate_id"),
                "Candidate Name": row.get("candidate_name"),
                "Phone": row.get("candidate_phone_number"),
                "Stage": row.get("stage_name"),
                "Status": row.get("status"),
                "HR Name": row.get("hr_name"),
                "Latest Remark": row.get("latest_remark"),
            }
            for row in payload["candidate_rows"]
        ]

        sheets = {
            "Summary": [{"metric": k, "value": v} for k, v in summary_tiles],
            "Stage flow": stage_flow_sheet,
            "Stage times": payload["stage_times"],
            "HR activities": hr_activities_sheet,
            "Candidates": candidates_sheet,
            "Pipeline velocity": payload["extras"].get("pipeline_velocity", []),
            "Best HR": payload.get("best_hr", []),
        }
        content = export_multi_sheet_xlsx(sheets)
        filename = f"{base_name}.xlsx"
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return StreamingResponse(
        io.BytesIO(content),
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.get("/summary")
def jobs_summary_report(
    from_date: date = Query(..., description="Start date for the report (YYYY-MM-DD)"),
    to_date: date = Query(..., description="End date for the report (YYYY-MM-DD)"),
    export_format: ExportFormat = Query(ExportFormat.pdf, description="xlsx|pdf"),
    user: User = Depends(validate_token),
    db: Session = Depends(get_db),
):
    """
    Jobs Summary Report - Returns a comprehensive summary of all jobs with tag-based statuses,
    company details, and daily breakdowns for the specified date range.
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
        payload = build_jobs_summary_report(db, from_date, to_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")
    
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    
    # Determine if it's a daily report
    is_daily = (from_date == to_date)
    if is_daily:
        date_str = from_date.strftime("%Y%m%d")
        base_name = f"jobs_summary_daily_{date_str}_{timestamp}"
        title = f"HTI Jobs Summary Report - {from_date.strftime('%d-%m-%Y')}"
    else:
        date_str = f"{from_date.strftime('%Y%m%d')}_{to_date.strftime('%Y%m%d')}"
        base_name = f"jobs_summary_{date_str}_{timestamp}"
        title = f"HTI Jobs Summary Report - {from_date.strftime('%d-%m-%Y')} to {to_date.strftime('%d-%m-%Y')}"

    if export_format == ExportFormat.pdf:
        content = export_jobs_summary_pdf(
            title,
            payload.get("summary_tiles", []),
            payload.get("jobs_summary", []),
            payload.get("company_summary", []),
            payload.get("hr_summary", []),
            payload.get("daily_breakdown", []),
            payload.get("charts", {}),
            generated_by=user.name if user else "",
            date_range=(from_date, to_date),
            jobs_and_recruiters=payload.get("jobs_and_recruiters", []),
        )
        filename = f"{base_name}.pdf"
        mime = "application/pdf"
    elif export_format == ExportFormat.xlsx:
        # Excel export
        sheets = {
            "Summary": [{"metric": k, "value": v} for k, v in payload.get("summary_tiles", [])],
            "Jobs Summary": payload.get("jobs_summary", []),
            "Company Summary": payload.get("company_summary", []),
            "HR Summary": payload.get("hr_summary", []),
            "Daily Breakdown": payload.get("daily_breakdown", []),
            "Tag by Job": payload.get("charts", {}).get("tag_by_job", []),
            "Daily Trends": payload.get("charts", {}).get("daily_tag_trends_by_company", []),
            "Company Performance": payload.get("charts", {}).get("company_performance", []),
            "Daily Joined vs Rejected": payload.get("charts", {}).get("daily_joined_rejected", []),
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
