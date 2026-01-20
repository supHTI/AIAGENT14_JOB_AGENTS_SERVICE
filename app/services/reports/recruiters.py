"""
Recruiter/HR performance report services.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, List, Mapping

from sqlalchemy import func, and_, cast, String, literal_column
from sqlalchemy.orm import Session

from app.database_layer.db_model import (
    CandidateActivity,
    CandidateActivityType,
    CandidateJobStatus,
    CandidateJobStatusType,
    CandidateJobs,
    Candidates,
    JobOpenings,
    PipelineStageStatus,
    PipelineStageStatusTag,
    User,
    UserJobsAssigned,
    Session as LoginSession,
)
from app.repositories import get_recruiter_performance
from app.schemas.reports import RecruiterPerformanceItem, RecruiterPerformanceResponse, ReportFilter


def build_performance(db, filters: ReportFilter) -> RecruiterPerformanceResponse:
    items_raw = get_recruiter_performance(db, filters)
    items: List[RecruiterPerformanceItem] = [RecruiterPerformanceItem(**item) for item in items_raw]
    return RecruiterPerformanceResponse(items=items)


def build_recruiters_summary_report(db: Session, from_date: date, to_date: date) -> Dict[str, Mapping]:
    """
    Build a summary report for all recruiters with tag-based statuses, job assignments, and daily breakdowns.
    Shows aggregated data across all recruiters for the specified date range.
    """
    def to_ist(dt_val):
        if not dt_val:
            return None
        ist_delta = timedelta(hours=5, minutes=30)
        if isinstance(dt_val, datetime):
            return dt_val + ist_delta
        if isinstance(dt_val, date):
            return datetime.combine(dt_val, datetime.min.time()) + ist_delta
        return dt_val

    # Calculate date range
    date_start = datetime.combine(from_date, datetime.min.time())
    date_end = datetime.combine(to_date, datetime.min.time()) + timedelta(days=1)
    
    # Determine if it's a daily report
    is_daily = (from_date == to_date)
    date_range_days = (to_date - from_date).days + 1

    # Get all recruiters (users who have been assigned to jobs or have activities)
    all_recruiter_ids = set()
    
    # From UserJobsAssigned
    assigned_recruiters = db.query(UserJobsAssigned.user_id).distinct().all()
    all_recruiter_ids.update(row[0] for row in assigned_recruiters)
    
    # From CandidateActivity
    activity_recruiters = (
        db.query(CandidateActivity.user_id)
        .filter(
            CandidateActivity.user_id.isnot(None),
            CandidateActivity.created_at >= date_start,
            CandidateActivity.created_at < date_end
        )
        .distinct()
        .all()
    )
    all_recruiter_ids.update(row[0] for row in activity_recruiters)
    
    # From CandidateJobStatus
    status_recruiters = (
        db.query(CandidateJobStatus.created_by)
        .filter(
            CandidateJobStatus.created_by.isnot(None),
            CandidateJobStatus.created_at >= date_start,
            CandidateJobStatus.created_at < date_end
        )
        .distinct()
        .all()
    )
    all_recruiter_ids.update(row[0] for row in status_recruiters)
    
    if not all_recruiter_ids:
        return {
            "summary_tiles": [],
            "recruiters_summary": [],
            "daily_breakdown": [],
            "charts": {},
            "date_range": {
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
                "is_daily": is_daily,
                "date_range_days": date_range_days
            }
        }
    
    # Get user details
    users = db.query(User).filter(User.id.in_(list(all_recruiter_ids))).all()
    user_map = {u.id: u for u in users}
    
    # Helper function to get tag count for a specific recruiter
    def get_tag_count_for_recruiter(recruiter_id: int, tag: PipelineStageStatusTag) -> int:
        count = (
            db.query(func.count(func.distinct(CandidateActivity.candidate_id)))
            .join(CandidateJobs, CandidateActivity.candidate_id == CandidateJobs.candidate_id)
            .join(
                PipelineStageStatus,
                and_(
                    CandidateActivity.remark.isnot(None),
                    PipelineStageStatus.option.isnot(None),
                    func.LOWER(func.trim(CandidateActivity.remark)) == func.LOWER(func.trim(PipelineStageStatus.option))
                )
            )
            .filter(
                CandidateActivity.user_id == recruiter_id,
                CandidateActivity.type == CandidateActivityType.status,
                CandidateActivity.created_at >= date_start,
                CandidateActivity.created_at < date_end,
                cast(PipelineStageStatus.tag, String) == tag.value
            )
            .scalar()
        )
        return count or 0
    
    # Get joined and rejected counts per recruiter
    joined_counts = {}
    rejected_counts = {}
    
    joined_data = (
        db.query(
            CandidateJobStatus.created_by,
            func.count(CandidateJobStatus.id).label('count')
        )
        .filter(
            CandidateJobStatus.type == CandidateJobStatusType.joined,
            CandidateJobStatus.joined_at.isnot(None),
            CandidateJobStatus.joined_at >= date_start,
            CandidateJobStatus.joined_at < date_end,
            CandidateJobStatus.created_by.in_(list(all_recruiter_ids))
        )
        .group_by(CandidateJobStatus.created_by)
        .all()
    )
    joined_counts = {rid: count for rid, count in joined_data}
    
    rejected_data = (
        db.query(
            CandidateJobStatus.created_by,
            func.count(CandidateJobStatus.id).label('count')
        )
        .filter(
            CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]),
            CandidateJobStatus.rejected_at.isnot(None),
            CandidateJobStatus.rejected_at >= date_start,
            CandidateJobStatus.rejected_at < date_end,
            CandidateJobStatus.created_by.in_(list(all_recruiter_ids))
        )
        .group_by(CandidateJobStatus.created_by)
        .all()
    )
    rejected_counts = {rid: count for rid, count in rejected_data}
    
    # Get activity counts per recruiter
    activity_counts = {}
    activity_data = (
        db.query(
            CandidateActivity.user_id,
            func.count(CandidateActivity.id).label('count')
        )
        .filter(
            CandidateActivity.user_id.in_(list(all_recruiter_ids)),
            CandidateActivity.user_id.isnot(None),
            CandidateActivity.created_at >= date_start,
            CandidateActivity.created_at < date_end
        )
        .group_by(CandidateActivity.user_id)
        .all()
    )
    activity_counts = {rid: count for rid, count in activity_data}
    
    # Get candidate counts per recruiter
    candidate_counts = {}
    candidate_data = (
        db.query(
            Candidates.assigned_to,
            func.count(func.distinct(Candidates.candidate_id)).label('count')
        )
        .join(CandidateJobs, Candidates.candidate_id == CandidateJobs.candidate_id)
        .filter(
            Candidates.assigned_to.in_(list(all_recruiter_ids)),
            Candidates.assigned_to.isnot(None),
            CandidateJobs.created_at >= date_start,
            CandidateJobs.created_at < date_end
        )
        .group_by(Candidates.assigned_to)
        .all()
    )
    candidate_counts = {rid: count for rid, count in candidate_data}
    
    # Get login counts per recruiter
    login_counts = {}
    login_data = (
        db.query(
            LoginSession.user_id,
            func.count(LoginSession.id).label('count')
        )
        .filter(
            LoginSession.user_id.in_(list(all_recruiter_ids)),
            LoginSession.login_at >= date_start,
            LoginSession.login_at < date_end
        )
        .group_by(LoginSession.user_id)
        .all()
    )
    login_counts = {rid: count for rid, count in login_data}
    
    # Build recruiters summary
    recruiters_summary = []
    for recruiter_id in all_recruiter_ids:
        user = user_map.get(recruiter_id)
        if not user:
            continue
        
        # Get tag counts for this recruiter
        sourced = get_tag_count_for_recruiter(recruiter_id, PipelineStageStatusTag.SOURCING)
        screened = get_tag_count_for_recruiter(recruiter_id, PipelineStageStatusTag.SCREENING)
        lined_up = get_tag_count_for_recruiter(recruiter_id, PipelineStageStatusTag.LINE_UPS)
        turned_up = get_tag_count_for_recruiter(recruiter_id, PipelineStageStatusTag.TURN_UPS)
        offer_accepted = get_tag_count_for_recruiter(recruiter_id, PipelineStageStatusTag.OFFER_ACCEPTED)
        
        # Calculate total activity
        total_activity = (
            sourced + screened + lined_up + turned_up + offer_accepted +
            joined_counts.get(recruiter_id, 0) + rejected_counts.get(recruiter_id, 0) +
            activity_counts.get(recruiter_id, 0)
        )
        
        recruiters_summary.append({
            "recruiter_id": recruiter_id,
            "recruiter_name": user.name,
            "candidates": candidate_counts.get(recruiter_id, 0),
            "sourced": sourced,
            "screened": screened,
            "lined_up": lined_up,
            "turned_up": turned_up,
            "offer_accepted": offer_accepted,
            "joined": joined_counts.get(recruiter_id, 0),
            "rejected": rejected_counts.get(recruiter_id, 0),
            "activities": activity_counts.get(recruiter_id, 0),
            "logins": login_counts.get(recruiter_id, 0),
            "total_activity": total_activity,
        })
    
    # Sort by most activity
    recruiters_summary.sort(key=lambda x: x["total_activity"], reverse=True)
    
    # Build daily breakdown (similar to jobs summary)
    # Determine grouping type
    if date_range_days == 1:
        group_type = "hourly"
    elif date_range_days <= 30:
        group_type = "daily"
    elif date_range_days <= 365:
        group_type = "weekly"
    else:
        group_type = "monthly"
    
    daily_breakdown_dict = {}
    
    if group_type == "hourly":
        for hour in range(24):
            hour_key = f"{hour:02d}:00"
            daily_breakdown_dict[hour_key] = {
                "date": hour_key,
                "sourced": 0,
                "screened": 0,
                "lined_up": 0,
                "turned_up": 0,
                "offer_accepted": 0,
                "joined": 0,
                "rejected": 0,
            }
    else:
        current = from_date
        while current <= to_date:
            if group_type == "daily":
                key = current.isoformat()
            elif group_type == "weekly":
                days_since_monday = current.weekday()
                week_start = current - timedelta(days=days_since_monday)
                key = week_start.isoformat()
            else:  # monthly
                key = current.replace(day=1).isoformat()
            
            if key not in daily_breakdown_dict:
                daily_breakdown_dict[key] = {
                    "date": key,
                    "sourced": 0,
                    "screened": 0,
                    "lined_up": 0,
                    "turned_up": 0,
                    "offer_accepted": 0,
                    "joined": 0,
                    "rejected": 0,
                }
            current += timedelta(days=1)
    
    # Get tag breakdowns (similar to jobs summary, but aggregated across all recruiters)
    for tag, tag_key in [
        (PipelineStageStatusTag.SOURCING, "sourced"),
        (PipelineStageStatusTag.SCREENING, "screened"),
        (PipelineStageStatusTag.LINE_UPS, "lined_up"),
        (PipelineStageStatusTag.TURN_UPS, "turned_up"),
        (PipelineStageStatusTag.OFFER_ACCEPTED, "offer_accepted"),
    ]:
        if group_type == "hourly":
            tag_data = (
                db.query(
                    func.extract('hour', CandidateActivity.created_at).label('activity_hour'),
                    func.count(func.distinct(CandidateActivity.candidate_id)).label('count')
                )
                .join(CandidateJobs, CandidateActivity.candidate_id == CandidateJobs.candidate_id)
                .join(
                    PipelineStageStatus,
                    and_(
                        CandidateActivity.remark.isnot(None),
                        PipelineStageStatus.option.isnot(None),
                        func.LOWER(func.trim(CandidateActivity.remark)) == func.LOWER(func.trim(PipelineStageStatus.option))
                    )
                )
                .filter(
                    CandidateActivity.user_id.in_(list(all_recruiter_ids)),
                    CandidateActivity.type == CandidateActivityType.status,
                    CandidateActivity.created_at >= date_start,
                    CandidateActivity.created_at < date_end,
                    cast(PipelineStageStatus.tag, String) == tag.value
                )
                .group_by(func.extract('hour', CandidateActivity.created_at))
                .all()
            )
            for hour, count in tag_data:
                hour_key = f"{int(hour):02d}:00"
                if hour_key in daily_breakdown_dict:
                    daily_breakdown_dict[hour_key][tag_key] = count
        elif group_type == "daily":
            tag_data = (
                db.query(
                    func.date(CandidateActivity.created_at).label('activity_date'),
                    func.count(func.distinct(CandidateActivity.candidate_id)).label('count')
                )
                .join(CandidateJobs, CandidateActivity.candidate_id == CandidateJobs.candidate_id)
                .join(
                    PipelineStageStatus,
                    and_(
                        CandidateActivity.remark.isnot(None),
                        PipelineStageStatus.option.isnot(None),
                        func.LOWER(func.trim(CandidateActivity.remark)) == func.LOWER(func.trim(PipelineStageStatus.option))
                    )
                )
                .filter(
                    CandidateActivity.user_id.in_(list(all_recruiter_ids)),
                    CandidateActivity.type == CandidateActivityType.status,
                    CandidateActivity.created_at >= date_start,
                    CandidateActivity.created_at < date_end,
                    cast(PipelineStageStatus.tag, String) == tag.value
                )
                .group_by(func.date(CandidateActivity.created_at))
                .all()
            )
            for day, count in tag_data:
                day_date = day.date() if isinstance(day, datetime) else day
                day_key = day_date.isoformat()
                if day_key in daily_breakdown_dict:
                    daily_breakdown_dict[day_key][tag_key] = count
        elif group_type == "weekly":
            week_start_expr = literal_column("DATE_SUB(DATE(candidate_activity.created_at), INTERVAL WEEKDAY(candidate_activity.created_at) DAY)")
            tag_data = (
                db.query(
                    func.date(week_start_expr).label('activity_week'),
                    func.count(func.distinct(CandidateActivity.candidate_id)).label('count')
                )
                .join(CandidateJobs, CandidateActivity.candidate_id == CandidateJobs.candidate_id)
                .join(
                    PipelineStageStatus,
                    and_(
                        CandidateActivity.remark.isnot(None),
                        PipelineStageStatus.option.isnot(None),
                        func.LOWER(func.trim(CandidateActivity.remark)) == func.LOWER(func.trim(PipelineStageStatus.option))
                    )
                )
                .filter(
                    CandidateActivity.user_id.in_(list(all_recruiter_ids)),
                    CandidateActivity.type == CandidateActivityType.status,
                    CandidateActivity.created_at >= date_start,
                    CandidateActivity.created_at < date_end,
                    cast(PipelineStageStatus.tag, String) == tag.value
                )
                .group_by(func.date(week_start_expr))
                .all()
            )
            for week, count in tag_data:
                week_date = week.date() if isinstance(week, datetime) else week
                week_key = week_date.isoformat()
                if week_key in daily_breakdown_dict:
                    daily_breakdown_dict[week_key][tag_key] = count
        else:  # monthly
            month_start_expr = literal_column("DATE_SUB(DATE(candidate_activity.created_at), INTERVAL DAY(candidate_activity.created_at)-1 DAY)")
            tag_data = (
                db.query(
                    func.date(month_start_expr).label('activity_month'),
                    func.count(func.distinct(CandidateActivity.candidate_id)).label('count')
                )
                .join(CandidateJobs, CandidateActivity.candidate_id == CandidateJobs.candidate_id)
                .join(
                    PipelineStageStatus,
                    and_(
                        CandidateActivity.remark.isnot(None),
                        PipelineStageStatus.option.isnot(None),
                        func.LOWER(func.trim(CandidateActivity.remark)) == func.LOWER(func.trim(PipelineStageStatus.option))
                    )
                )
                .filter(
                    CandidateActivity.user_id.in_(list(all_recruiter_ids)),
                    CandidateActivity.type == CandidateActivityType.status,
                    CandidateActivity.created_at >= date_start,
                    CandidateActivity.created_at < date_end,
                    cast(PipelineStageStatus.tag, String) == tag.value
                )
                .group_by(func.date(month_start_expr))
                .all()
            )
            for month, count in tag_data:
                month_date = month.date() if isinstance(month, datetime) else month
                month_key = month_date.replace(day=1).isoformat()
                if month_key in daily_breakdown_dict:
                    daily_breakdown_dict[month_key][tag_key] = count
    
    # Get joined/rejected breakdowns
    if group_type == "hourly":
        joined_data = (
            db.query(
                func.extract('hour', CandidateJobStatus.joined_at).label('joined_hour'),
                func.count(CandidateJobStatus.id).label('count')
            )
            .filter(
                CandidateJobStatus.type == CandidateJobStatusType.joined,
                CandidateJobStatus.joined_at.isnot(None),
                CandidateJobStatus.joined_at >= date_start,
                CandidateJobStatus.joined_at < date_end,
                CandidateJobStatus.created_by.in_(list(all_recruiter_ids))
            )
            .group_by(func.extract('hour', CandidateJobStatus.joined_at))
            .all()
        )
        for hour, count in joined_data:
            hour_key = f"{int(hour):02d}:00"
            if hour_key in daily_breakdown_dict:
                daily_breakdown_dict[hour_key]["joined"] = count
        
        rejected_data = (
            db.query(
                func.extract('hour', CandidateJobStatus.rejected_at).label('rejected_hour'),
                func.count(CandidateJobStatus.id).label('count')
            )
            .filter(
                CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]),
                CandidateJobStatus.rejected_at.isnot(None),
                CandidateJobStatus.rejected_at >= date_start,
                CandidateJobStatus.rejected_at < date_end,
                CandidateJobStatus.created_by.in_(list(all_recruiter_ids))
            )
            .group_by(func.extract('hour', CandidateJobStatus.rejected_at))
            .all()
        )
        for hour, count in rejected_data:
            hour_key = f"{int(hour):02d}:00"
            if hour_key in daily_breakdown_dict:
                daily_breakdown_dict[hour_key]["rejected"] = count
    elif group_type == "daily":
        joined_data = (
            db.query(
                func.date(CandidateJobStatus.joined_at).label('joined_date'),
                func.count(CandidateJobStatus.id).label('count')
            )
            .filter(
                CandidateJobStatus.type == CandidateJobStatusType.joined,
                CandidateJobStatus.joined_at.isnot(None),
                CandidateJobStatus.joined_at >= date_start,
                CandidateJobStatus.joined_at < date_end,
                CandidateJobStatus.created_by.in_(list(all_recruiter_ids))
            )
            .group_by(func.date(CandidateJobStatus.joined_at))
            .all()
        )
        for day, count in joined_data:
            day_date = day.date() if isinstance(day, datetime) else day
            day_key = day_date.isoformat()
            if day_key in daily_breakdown_dict:
                daily_breakdown_dict[day_key]["joined"] = count
        
        rejected_data = (
            db.query(
                func.date(CandidateJobStatus.rejected_at).label('rejected_date'),
                func.count(CandidateJobStatus.id).label('count')
            )
            .filter(
                CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]),
                CandidateJobStatus.rejected_at.isnot(None),
                CandidateJobStatus.rejected_at >= date_start,
                CandidateJobStatus.rejected_at < date_end,
                CandidateJobStatus.created_by.in_(list(all_recruiter_ids))
            )
            .group_by(func.date(CandidateJobStatus.rejected_at))
            .all()
        )
        for day, count in rejected_data:
            day_date = day.date() if isinstance(day, datetime) else day
            day_key = day_date.isoformat()
            if day_key in daily_breakdown_dict:
                daily_breakdown_dict[day_key]["rejected"] = count
    elif group_type == "weekly":
        week_start_expr_joined = literal_column("DATE_SUB(DATE(candidate_job_status.joined_at), INTERVAL WEEKDAY(candidate_job_status.joined_at) DAY)")
        joined_data = (
            db.query(
                func.date(week_start_expr_joined).label('joined_week'),
                func.count(CandidateJobStatus.id).label('count')
            )
            .filter(
                CandidateJobStatus.type == CandidateJobStatusType.joined,
                CandidateJobStatus.joined_at.isnot(None),
                CandidateJobStatus.joined_at >= date_start,
                CandidateJobStatus.joined_at < date_end,
                CandidateJobStatus.created_by.in_(list(all_recruiter_ids))
            )
            .group_by(func.date(week_start_expr_joined))
            .all()
        )
        for week, count in joined_data:
            week_date = week.date() if isinstance(week, datetime) else week
            week_key = week_date.isoformat()
            if week_key in daily_breakdown_dict:
                daily_breakdown_dict[week_key]["joined"] = count
        
        week_start_expr_rejected = literal_column("DATE_SUB(DATE(candidate_job_status.rejected_at), INTERVAL WEEKDAY(candidate_job_status.rejected_at) DAY)")
        rejected_data = (
            db.query(
                func.date(week_start_expr_rejected).label('rejected_week'),
                func.count(CandidateJobStatus.id).label('count')
            )
            .filter(
                CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]),
                CandidateJobStatus.rejected_at.isnot(None),
                CandidateJobStatus.rejected_at >= date_start,
                CandidateJobStatus.rejected_at < date_end,
                CandidateJobStatus.created_by.in_(list(all_recruiter_ids))
            )
            .group_by(func.date(week_start_expr_rejected))
            .all()
        )
        for week, count in rejected_data:
            week_date = week.date() if isinstance(week, datetime) else week
            week_key = week_date.isoformat()
            if week_key in daily_breakdown_dict:
                daily_breakdown_dict[week_key]["rejected"] = count
    else:  # monthly
        month_start_expr_joined = literal_column("DATE_SUB(DATE(candidate_job_status.joined_at), INTERVAL DAY(candidate_job_status.joined_at)-1 DAY)")
        joined_data = (
            db.query(
                func.date(month_start_expr_joined).label('joined_month'),
                func.count(CandidateJobStatus.id).label('count')
            )
            .filter(
                CandidateJobStatus.type == CandidateJobStatusType.joined,
                CandidateJobStatus.joined_at.isnot(None),
                CandidateJobStatus.joined_at >= date_start,
                CandidateJobStatus.joined_at < date_end,
                CandidateJobStatus.created_by.in_(list(all_recruiter_ids))
            )
            .group_by(func.date(month_start_expr_joined))
            .all()
        )
        for month, count in joined_data:
            month_date = month.date() if isinstance(month, datetime) else month
            month_key = month_date.replace(day=1).isoformat()
            if month_key in daily_breakdown_dict:
                daily_breakdown_dict[month_key]["joined"] = count
        
        month_start_expr_rejected = literal_column("DATE_SUB(DATE(candidate_job_status.rejected_at), INTERVAL DAY(candidate_job_status.rejected_at)-1 DAY)")
        rejected_data = (
            db.query(
                func.date(month_start_expr_rejected).label('rejected_month'),
                func.count(CandidateJobStatus.id).label('count')
            )
            .filter(
                CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]),
                CandidateJobStatus.rejected_at.isnot(None),
                CandidateJobStatus.rejected_at >= date_start,
                CandidateJobStatus.rejected_at < date_end,
                CandidateJobStatus.created_by.in_(list(all_recruiter_ids))
            )
            .group_by(func.date(month_start_expr_rejected))
            .all()
        )
        for month, count in rejected_data:
            month_date = month.date() if isinstance(month, datetime) else month
            month_key = month_date.replace(day=1).isoformat()
            if month_key in daily_breakdown_dict:
                daily_breakdown_dict[month_key]["rejected"] = count
    
    daily_breakdown = sorted(daily_breakdown_dict.values(), key=lambda x: x["date"])
    
    # Calculate summary tiles
    total_recruiters = len(recruiters_summary)
    total_candidates = sum(r["candidates"] for r in recruiters_summary)
    total_sourced = sum(r["sourced"] for r in recruiters_summary)
    total_screened = sum(r["screened"] for r in recruiters_summary)
    total_lined_up = sum(r["lined_up"] for r in recruiters_summary)
    total_turned_up = sum(r["turned_up"] for r in recruiters_summary)
    total_offer_accepted = sum(r["offer_accepted"] for r in recruiters_summary)
    total_joined = sum(r["joined"] for r in recruiters_summary)
    total_rejected = sum(r["rejected"] for r in recruiters_summary)
    total_activities = sum(r["activities"] for r in recruiters_summary)
    total_logins = sum(r["logins"] for r in recruiters_summary)
    
    summary_tiles = [
        ("Total Recruiters", total_recruiters),
        ("Total Candidates", total_candidates),
        ("Total Sourced", total_sourced),
        ("Total Screened", total_screened),
        ("Total Lined Up", total_lined_up),
        ("Total Turned Up", total_turned_up),
        ("Total Offer Accepted", total_offer_accepted),
        ("Total Joined", total_joined),
        ("Total Rejected", total_rejected),
        ("Total Activities", total_activities),
        ("Total Logins", total_logins),
    ]
    
    # Build charts
    # Chart 1: Daily status trends
    daily_status_trends = [
        {
            "date": d["date"],
            "sourced": d["sourced"],
            "screened": d["screened"],
            "lined_up": d["lined_up"],
            "turned_up": d["turned_up"],
            "offer_accepted": d["offer_accepted"],
        }
        for d in daily_breakdown
    ]
    
    # Chart 2: Daily joined vs rejected
    daily_joined_rejected = [
        {
            "date": d["date"],
            "joined": d["joined"],
            "rejected": d["rejected"],
        }
        for d in daily_breakdown
    ]
    
    # Chart 3: Top recruiters performance
    top_recruiters_performance = [
        {
            "recruiter_name": r["recruiter_name"],
            "joined": r["joined"],
            "sourced": r["sourced"],
            "screened": r["screened"],
        }
        for r in recruiters_summary[:15]  # Top 15 recruiters
    ]
    
    # Chart 4: Recruiter Efficiency (Joined/Activities ratio)
    recruiter_efficiency = []
    for r in recruiters_summary[:15]:  # Top 15 recruiters
        activities = r.get("activities", 0)
        joined = r.get("joined", 0)
        efficiency = round((joined / activities * 100), 2) if activities > 0 else 0
        recruiter_efficiency.append({
            "recruiter_name": r["recruiter_name"],
            "efficiency": efficiency,
            "joined": joined,
            "activities": activities,
        })
    recruiter_efficiency.sort(key=lambda x: x["efficiency"], reverse=True)
    
    # Chart 5: Activity Distribution (Histogram data)
    activity_distribution = []
    activity_ranges = [
        (0, 10, "0-10"),
        (11, 25, "11-25"),
        (26, 50, "26-50"),
        (51, 100, "51-100"),
        (101, 200, "101-200"),
        (201, float('inf'), "200+"),
    ]
    for min_val, max_val, label in activity_ranges:
        count = len([r for r in recruiters_summary if min_val <= r.get("activities", 0) <= max_val])
        activity_distribution.append({
            "range": label,
            "count": count,
        })
    
    # Chart 6: Performance Comparison (Grouped bar chart data)
    performance_comparison = []
    for r in recruiters_summary[:10]:  # Top 10 for better readability
        performance_comparison.append({
            "recruiter_name": r["recruiter_name"],
            "sourced": r["sourced"],
            "screened": r["screened"],
            "lined_up": r["lined_up"],
            "turned_up": r["turned_up"],
            "offer_accepted": r["offer_accepted"],
            "joined": r["joined"],
        })
    
    # Chart 7: Conversion Rate (Joined/Candidates * 100)
    conversion_rates = []
    for r in recruiters_summary[:15]:  # Top 15 recruiters
        candidates = r.get("candidates", 0)
        joined = r.get("joined", 0)
        conversion_rate = round((joined / candidates * 100), 2) if candidates > 0 else 0
        conversion_rates.append({
            "recruiter_name": r["recruiter_name"],
            "conversion_rate": conversion_rate,
            "candidates": candidates,
            "joined": joined,
        })
    conversion_rates.sort(key=lambda x: x["conversion_rate"], reverse=True)
    
    return {
        "summary_tiles": summary_tiles,
        "recruiters_summary": recruiters_summary,
        "daily_breakdown": daily_breakdown,
        "charts": {
            "daily_status_trends": daily_status_trends,
            "daily_joined_rejected": daily_joined_rejected,
            "top_recruiters_performance": top_recruiters_performance,
            "recruiter_efficiency": recruiter_efficiency,
            "activity_distribution": activity_distribution,
            "performance_comparison": performance_comparison,
            "conversion_rates": conversion_rates,
        },
        "date_range": {
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "is_daily": is_daily,
            "date_range_days": date_range_days,
            "group_type": group_type
        }
    }


def build_recruiter_performance_report(db: Session, recruiter_id: int, from_date: date, to_date: date) -> Dict[str, Mapping]:
    """
    Build a detailed performance report for a specific recruiter.
    Similar to build_job_daily_report but focused on a single recruiter.
    """
    def to_ist(dt_val):
        if not dt_val:
            return None
        ist_delta = timedelta(hours=5, minutes=30)
        if isinstance(dt_val, datetime):
            return dt_val + ist_delta
        if isinstance(dt_val, date):
            return datetime.combine(dt_val, datetime.min.time()) + ist_delta
        return dt_val

    # Calculate date range
    date_start = datetime.combine(from_date, datetime.min.time())
    date_end = datetime.combine(to_date, datetime.min.time()) + timedelta(days=1)
    
    # Determine if it's a daily report
    is_daily = (from_date == to_date)
    date_range_days = (to_date - from_date).days + 1

    # Get recruiter details
    recruiter = db.query(User).filter(User.id == recruiter_id).first()
    if not recruiter:
        raise ValueError("Recruiter not found")
    
    recruiter_name = recruiter.name
    
    # Get all jobs assigned to this recruiter
    assigned_jobs = (
        db.query(UserJobsAssigned.job_id)
        .filter(UserJobsAssigned.user_id == recruiter_id)
        .distinct()
        .all()
    )
    job_ids = [row[0] for row in assigned_jobs]
    
    # Get all candidate jobs for these jobs
    candidate_jobs = db.query(CandidateJobs).filter(CandidateJobs.job_id.in_(job_ids)).all()
    candidate_job_ids = [cj.id for cj in candidate_jobs]
    candidate_ids = [cj.candidate_id for cj in candidate_jobs]
    
    # Get candidates assigned to this recruiter
    assigned_candidates = (
        db.query(Candidates.candidate_id)
        .filter(Candidates.assigned_to == recruiter_id)
        .all()
    )
    assigned_candidate_ids = {row[0] for row in assigned_candidates}
    
    # Helper function to get tag count for this recruiter
    def get_count_by_tag(tag: PipelineStageStatusTag) -> int:
        if not candidate_ids:
            return 0
        count = (
            db.query(func.count(func.distinct(CandidateActivity.candidate_id)))
            .join(CandidateJobs, CandidateActivity.candidate_id == CandidateJobs.candidate_id)
            .join(
                PipelineStageStatus,
                and_(
                    CandidateActivity.remark.isnot(None),
                    PipelineStageStatus.option.isnot(None),
                    func.LOWER(func.trim(CandidateActivity.remark)) == func.LOWER(func.trim(PipelineStageStatus.option))
                )
            )
            .filter(
                CandidateActivity.user_id == recruiter_id,
                CandidateActivity.candidate_id.in_(candidate_ids),
                CandidateActivity.type == CandidateActivityType.status,
                CandidateActivity.created_at >= date_start,
                CandidateActivity.created_at < date_end,
                cast(PipelineStageStatus.tag, String) == tag.value
            )
            .scalar()
        )
        return count or 0
    
    # Get tag counts
    sourced_count = get_count_by_tag(PipelineStageStatusTag.SOURCING)
    screened_count = get_count_by_tag(PipelineStageStatusTag.SCREENING)
    lined_up_count = get_count_by_tag(PipelineStageStatusTag.LINE_UPS)
    turned_up_count = get_count_by_tag(PipelineStageStatusTag.TURN_UPS)
    offer_accepted_count = get_count_by_tag(PipelineStageStatusTag.OFFER_ACCEPTED)
    
    # Get joined and rejected counts
    joined_count = (
        db.query(func.count(CandidateJobStatus.id))
        .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id.in_(job_ids),
            CandidateJobStatus.type == CandidateJobStatusType.joined,
            CandidateJobStatus.joined_at.isnot(None),
            CandidateJobStatus.joined_at >= date_start,
            CandidateJobStatus.joined_at < date_end,
            CandidateJobStatus.created_by == recruiter_id
        )
        .scalar() or 0
    )
    
    rejected_count = (
        db.query(func.count(CandidateJobStatus.id))
        .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id.in_(job_ids),
            CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]),
            CandidateJobStatus.rejected_at.isnot(None),
            CandidateJobStatus.rejected_at >= date_start,
            CandidateJobStatus.rejected_at < date_end,
            CandidateJobStatus.created_by == recruiter_id
        )
        .scalar() or 0
    )
    
    # Get activity count
    activity_count = (
        db.query(func.count(CandidateActivity.id))
        .filter(
            CandidateActivity.user_id == recruiter_id,
            CandidateActivity.created_at >= date_start,
            CandidateActivity.created_at < date_end
        )
        .scalar() or 0
    )
    
    # Get candidate count
    candidate_count = (
        db.query(func.count(func.distinct(Candidates.candidate_id)))
        .join(CandidateJobs, Candidates.candidate_id == CandidateJobs.candidate_id)
        .filter(
            Candidates.assigned_to == recruiter_id,
            CandidateJobs.job_id.in_(job_ids),
            CandidateJobs.created_at >= date_start,
            CandidateJobs.created_at < date_end
        )
        .scalar() or 0
    )
    
    # Get login count
    login_count = (
        db.query(func.count(LoginSession.id))
        .filter(
            LoginSession.user_id == recruiter_id,
            LoginSession.login_at >= date_start,
            LoginSession.login_at < date_end
        )
        .scalar() or 0
    )
    
    # Get total active jobs assigned to this recruiter
    total_jobs_assigned = 0
    if job_ids:
        active_jobs = (
            db.query(JobOpenings.id)
            .filter(
                JobOpenings.id.in_(job_ids),
                JobOpenings.status == "ACTIVE"
            )
            .count()
        )
        total_jobs_assigned = active_jobs
    
    # Summary tiles
    summary_tiles = [
        ("Total Jobs Assigned", total_jobs_assigned),
        ("Candidates", candidate_count),
        ("Sourced", sourced_count),
        ("Screened", screened_count),
        ("Lined Up", lined_up_count),
        ("Turned Up", turned_up_count),
        ("Offer Accepted", offer_accepted_count),
        ("Joined", joined_count),
        ("Rejected", rejected_count),
        ("Activities", activity_count),
        ("Logins", login_count),
    ]
    
    # Recruiter metadata
    recruiter_metadata = {
        "recruiter_id": recruiter_id,
        "recruiter_name": recruiter_name,
        "email": recruiter.email if hasattr(recruiter, 'email') else None,
    }
    
    # Get jobs assigned to this recruiter
    jobs_assigned = []
    if job_ids:
        jobs = db.query(JobOpenings).filter(JobOpenings.id.in_(job_ids)).all()
        for job in jobs:
            # Get counts for this job
            job_candidate_ids = [cid for cid in candidate_ids if cid in assigned_candidate_ids]
            job_candidate_jobs = [cj for cj in candidate_jobs if cj.job_id == job.id]
            job_candidate_job_ids = [cj.id for cj in job_candidate_jobs]
            
            job_joined = (
                db.query(func.count(CandidateJobStatus.id))
                .filter(
                    CandidateJobStatus.candidate_job_id.in_(job_candidate_job_ids),
                    CandidateJobStatus.type == CandidateJobStatusType.joined,
                    CandidateJobStatus.joined_at.isnot(None),
                    CandidateJobStatus.joined_at >= date_start,
                    CandidateJobStatus.joined_at < date_end,
                    CandidateJobStatus.created_by == recruiter_id
                )
                .scalar() or 0
            )
            
            jobs_assigned.append({
                "job_id": job.id,
                "job_public_id": job.job_id,
                "job_title": job.title,
                "candidates": len([cj for cj in job_candidate_jobs if cj.candidate_id in assigned_candidate_ids]),
                "joined": job_joined,
            })
    
    # Build daily breakdown (similar to jobs summary)
    if date_range_days == 1:
        group_type = "hourly"
    elif date_range_days <= 30:
        group_type = "daily"
    elif date_range_days <= 365:
        group_type = "weekly"
    else:
        group_type = "monthly"
    
    daily_breakdown_dict = {}
    
    if group_type == "hourly":
        for hour in range(24):
            hour_key = f"{hour:02d}:00"
            daily_breakdown_dict[hour_key] = {
                "date": hour_key,
                "sourced": 0,
                "screened": 0,
                "lined_up": 0,
                "turned_up": 0,
                "offer_accepted": 0,
                "joined": 0,
                "rejected": 0,
            }
    else:
        current = from_date
        while current <= to_date:
            if group_type == "daily":
                key = current.isoformat()
            elif group_type == "weekly":
                days_since_monday = current.weekday()
                week_start = current - timedelta(days=days_since_monday)
                key = week_start.isoformat()
            else:  # monthly
                key = current.replace(day=1).isoformat()
            
            if key not in daily_breakdown_dict:
                daily_breakdown_dict[key] = {
                    "date": key,
                    "sourced": 0,
                    "screened": 0,
                    "lined_up": 0,
                    "turned_up": 0,
                    "offer_accepted": 0,
                    "joined": 0,
                    "rejected": 0,
                }
            current += timedelta(days=1)
    
    # Get tag breakdowns (similar to jobs summary but filtered by recruiter_id)
    for tag, tag_key in [
        (PipelineStageStatusTag.SOURCING, "sourced"),
        (PipelineStageStatusTag.SCREENING, "screened"),
        (PipelineStageStatusTag.LINE_UPS, "lined_up"),
        (PipelineStageStatusTag.TURN_UPS, "turned_up"),
        (PipelineStageStatusTag.OFFER_ACCEPTED, "offer_accepted"),
    ]:
        if group_type == "hourly":
            tag_data = (
                db.query(
                    func.extract('hour', CandidateActivity.created_at).label('activity_hour'),
                    func.count(func.distinct(CandidateActivity.candidate_id)).label('count')
                )
                .join(CandidateJobs, CandidateActivity.candidate_id == CandidateJobs.candidate_id)
                .join(
                    PipelineStageStatus,
                    and_(
                        CandidateActivity.remark.isnot(None),
                        PipelineStageStatus.option.isnot(None),
                        func.LOWER(func.trim(CandidateActivity.remark)) == func.LOWER(func.trim(PipelineStageStatus.option))
                    )
                )
                .filter(
                    CandidateActivity.user_id == recruiter_id,
                    CandidateActivity.candidate_id.in_(candidate_ids),
                    CandidateActivity.type == CandidateActivityType.status,
                    CandidateActivity.created_at >= date_start,
                    CandidateActivity.created_at < date_end,
                    cast(PipelineStageStatus.tag, String) == tag.value
                )
                .group_by(func.extract('hour', CandidateActivity.created_at))
                .all()
            )
            for hour, count in tag_data:
                hour_key = f"{int(hour):02d}:00"
                if hour_key in daily_breakdown_dict:
                    daily_breakdown_dict[hour_key][tag_key] = count
        elif group_type == "daily":
            tag_data = (
                db.query(
                    func.date(CandidateActivity.created_at).label('activity_date'),
                    func.count(func.distinct(CandidateActivity.candidate_id)).label('count')
                )
                .join(CandidateJobs, CandidateActivity.candidate_id == CandidateJobs.candidate_id)
                .join(
                    PipelineStageStatus,
                    and_(
                        CandidateActivity.remark.isnot(None),
                        PipelineStageStatus.option.isnot(None),
                        func.LOWER(func.trim(CandidateActivity.remark)) == func.LOWER(func.trim(PipelineStageStatus.option))
                    )
                )
                .filter(
                    CandidateActivity.user_id == recruiter_id,
                    CandidateActivity.candidate_id.in_(candidate_ids),
                    CandidateActivity.type == CandidateActivityType.status,
                    CandidateActivity.created_at >= date_start,
                    CandidateActivity.created_at < date_end,
                    cast(PipelineStageStatus.tag, String) == tag.value
                )
                .group_by(func.date(CandidateActivity.created_at))
                .all()
            )
            for day, count in tag_data:
                day_date = day.date() if isinstance(day, datetime) else day
                day_key = day_date.isoformat()
                if day_key in daily_breakdown_dict:
                    daily_breakdown_dict[day_key][tag_key] = count
        elif group_type == "weekly":
            week_start_expr = literal_column("DATE_SUB(DATE(candidate_activity.created_at), INTERVAL WEEKDAY(candidate_activity.created_at) DAY)")
            tag_data = (
                db.query(
                    func.date(week_start_expr).label('activity_week'),
                    func.count(func.distinct(CandidateActivity.candidate_id)).label('count')
                )
                .join(CandidateJobs, CandidateActivity.candidate_id == CandidateJobs.candidate_id)
                .join(
                    PipelineStageStatus,
                    and_(
                        CandidateActivity.remark.isnot(None),
                        PipelineStageStatus.option.isnot(None),
                        func.LOWER(func.trim(CandidateActivity.remark)) == func.LOWER(func.trim(PipelineStageStatus.option))
                    )
                )
                .filter(
                    CandidateActivity.user_id == recruiter_id,
                    CandidateActivity.candidate_id.in_(candidate_ids),
                    CandidateActivity.type == CandidateActivityType.status,
                    CandidateActivity.created_at >= date_start,
                    CandidateActivity.created_at < date_end,
                    cast(PipelineStageStatus.tag, String) == tag.value
                )
                .group_by(func.date(week_start_expr))
                .all()
            )
            for week, count in tag_data:
                week_date = week.date() if isinstance(week, datetime) else week
                week_key = week_date.isoformat()
                if week_key in daily_breakdown_dict:
                    daily_breakdown_dict[week_key][tag_key] = count
        else:  # monthly
            month_start_expr = literal_column("DATE_SUB(DATE(candidate_activity.created_at), INTERVAL DAY(candidate_activity.created_at)-1 DAY)")
            tag_data = (
                db.query(
                    func.date(month_start_expr).label('activity_month'),
                    func.count(func.distinct(CandidateActivity.candidate_id)).label('count')
                )
                .join(CandidateJobs, CandidateActivity.candidate_id == CandidateJobs.candidate_id)
                .join(
                    PipelineStageStatus,
                    and_(
                        CandidateActivity.remark.isnot(None),
                        PipelineStageStatus.option.isnot(None),
                        func.LOWER(func.trim(CandidateActivity.remark)) == func.LOWER(func.trim(PipelineStageStatus.option))
                    )
                )
                .filter(
                    CandidateActivity.user_id == recruiter_id,
                    CandidateActivity.candidate_id.in_(candidate_ids),
                    CandidateActivity.type == CandidateActivityType.status,
                    CandidateActivity.created_at >= date_start,
                    CandidateActivity.created_at < date_end,
                    cast(PipelineStageStatus.tag, String) == tag.value
                )
                .group_by(func.date(month_start_expr))
                .all()
            )
            for month, count in tag_data:
                month_date = month.date() if isinstance(month, datetime) else month
                month_key = month_date.replace(day=1).isoformat()
                if month_key in daily_breakdown_dict:
                    daily_breakdown_dict[month_key][tag_key] = count
    
    # Get joined/rejected breakdowns
    if group_type == "hourly":
        joined_data = (
            db.query(
                func.extract('hour', CandidateJobStatus.joined_at).label('joined_hour'),
                func.count(CandidateJobStatus.id).label('count')
            )
            .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(
                CandidateJobs.job_id.in_(job_ids),
                CandidateJobStatus.type == CandidateJobStatusType.joined,
                CandidateJobStatus.joined_at.isnot(None),
                CandidateJobStatus.joined_at >= date_start,
                CandidateJobStatus.joined_at < date_end,
                CandidateJobStatus.created_by == recruiter_id
            )
            .group_by(func.extract('hour', CandidateJobStatus.joined_at))
            .all()
        )
        for hour, count in joined_data:
            hour_key = f"{int(hour):02d}:00"
            if hour_key in daily_breakdown_dict:
                daily_breakdown_dict[hour_key]["joined"] = count
        
        rejected_data = (
            db.query(
                func.extract('hour', CandidateJobStatus.rejected_at).label('rejected_hour'),
                func.count(CandidateJobStatus.id).label('count')
            )
            .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(
                CandidateJobs.job_id.in_(job_ids),
                CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]),
                CandidateJobStatus.rejected_at.isnot(None),
                CandidateJobStatus.rejected_at >= date_start,
                CandidateJobStatus.rejected_at < date_end,
                CandidateJobStatus.created_by == recruiter_id
            )
            .group_by(func.extract('hour', CandidateJobStatus.rejected_at))
            .all()
        )
        for hour, count in rejected_data:
            hour_key = f"{int(hour):02d}:00"
            if hour_key in daily_breakdown_dict:
                daily_breakdown_dict[hour_key]["rejected"] = count
    elif group_type == "daily":
        joined_data = (
            db.query(
                func.date(CandidateJobStatus.joined_at).label('joined_date'),
                func.count(CandidateJobStatus.id).label('count')
            )
            .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(
                CandidateJobs.job_id.in_(job_ids),
                CandidateJobStatus.type == CandidateJobStatusType.joined,
                CandidateJobStatus.joined_at.isnot(None),
                CandidateJobStatus.joined_at >= date_start,
                CandidateJobStatus.joined_at < date_end,
                CandidateJobStatus.created_by == recruiter_id
            )
            .group_by(func.date(CandidateJobStatus.joined_at))
            .all()
        )
        for day, count in joined_data:
            day_date = day.date() if isinstance(day, datetime) else day
            day_key = day_date.isoformat()
            if day_key in daily_breakdown_dict:
                daily_breakdown_dict[day_key]["joined"] = count
        
        rejected_data = (
            db.query(
                func.date(CandidateJobStatus.rejected_at).label('rejected_date'),
                func.count(CandidateJobStatus.id).label('count')
            )
            .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(
                CandidateJobs.job_id.in_(job_ids),
                CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]),
                CandidateJobStatus.rejected_at.isnot(None),
                CandidateJobStatus.rejected_at >= date_start,
                CandidateJobStatus.rejected_at < date_end,
                CandidateJobStatus.created_by == recruiter_id
            )
            .group_by(func.date(CandidateJobStatus.rejected_at))
            .all()
        )
        for day, count in rejected_data:
            day_date = day.date() if isinstance(day, datetime) else day
            day_key = day_date.isoformat()
            if day_key in daily_breakdown_dict:
                daily_breakdown_dict[day_key]["rejected"] = count
    elif group_type == "weekly":
        week_start_expr_joined = literal_column("DATE_SUB(DATE(candidate_job_status.joined_at), INTERVAL WEEKDAY(candidate_job_status.joined_at) DAY)")
        joined_data = (
            db.query(
                func.date(week_start_expr_joined).label('joined_week'),
                func.count(CandidateJobStatus.id).label('count')
            )
            .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(
                CandidateJobs.job_id.in_(job_ids),
                CandidateJobStatus.type == CandidateJobStatusType.joined,
                CandidateJobStatus.joined_at.isnot(None),
                CandidateJobStatus.joined_at >= date_start,
                CandidateJobStatus.joined_at < date_end,
                CandidateJobStatus.created_by == recruiter_id
            )
            .group_by(func.date(week_start_expr_joined))
            .all()
        )
        for week, count in joined_data:
            week_date = week.date() if isinstance(week, datetime) else week
            week_key = week_date.isoformat()
            if week_key in daily_breakdown_dict:
                daily_breakdown_dict[week_key]["joined"] = count
        
        week_start_expr_rejected = literal_column("DATE_SUB(DATE(candidate_job_status.rejected_at), INTERVAL WEEKDAY(candidate_job_status.rejected_at) DAY)")
        rejected_data = (
            db.query(
                func.date(week_start_expr_rejected).label('rejected_week'),
                func.count(CandidateJobStatus.id).label('count')
            )
            .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(
                CandidateJobs.job_id.in_(job_ids),
                CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]),
                CandidateJobStatus.rejected_at.isnot(None),
                CandidateJobStatus.rejected_at >= date_start,
                CandidateJobStatus.rejected_at < date_end,
                CandidateJobStatus.created_by == recruiter_id
            )
            .group_by(func.date(week_start_expr_rejected))
            .all()
        )
        for week, count in rejected_data:
            week_date = week.date() if isinstance(week, datetime) else week
            week_key = week_date.isoformat()
            if week_key in daily_breakdown_dict:
                daily_breakdown_dict[week_key]["rejected"] = count
    else:  # monthly
        month_start_expr_joined = literal_column("DATE_SUB(DATE(candidate_job_status.joined_at), INTERVAL DAY(candidate_job_status.joined_at)-1 DAY)")
        joined_data = (
            db.query(
                func.date(month_start_expr_joined).label('joined_month'),
                func.count(CandidateJobStatus.id).label('count')
            )
            .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(
                CandidateJobs.job_id.in_(job_ids),
                CandidateJobStatus.type == CandidateJobStatusType.joined,
                CandidateJobStatus.joined_at.isnot(None),
                CandidateJobStatus.joined_at >= date_start,
                CandidateJobStatus.joined_at < date_end,
                CandidateJobStatus.created_by == recruiter_id
            )
            .group_by(func.date(month_start_expr_joined))
            .all()
        )
        for month, count in joined_data:
            month_date = month.date() if isinstance(month, datetime) else month
            month_key = month_date.replace(day=1).isoformat()
            if month_key in daily_breakdown_dict:
                daily_breakdown_dict[month_key]["joined"] = count
        
        month_start_expr_rejected = literal_column("DATE_SUB(DATE(candidate_job_status.rejected_at), INTERVAL DAY(candidate_job_status.rejected_at)-1 DAY)")
        rejected_data = (
            db.query(
                func.date(month_start_expr_rejected).label('rejected_month'),
                func.count(CandidateJobStatus.id).label('count')
            )
            .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(
                CandidateJobs.job_id.in_(job_ids),
                CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]),
                CandidateJobStatus.rejected_at.isnot(None),
                CandidateJobStatus.rejected_at >= date_start,
                CandidateJobStatus.rejected_at < date_end,
                CandidateJobStatus.created_by == recruiter_id
            )
            .group_by(func.date(month_start_expr_rejected))
            .all()
        )
        for month, count in rejected_data:
            month_date = month.date() if isinstance(month, datetime) else month
            month_key = month_date.replace(day=1).isoformat()
            if month_key in daily_breakdown_dict:
                daily_breakdown_dict[month_key]["rejected"] = count
    
    daily_breakdown = sorted(daily_breakdown_dict.values(), key=lambda x: x["date"])
    
    # Get recruiter activity details (similar to hr_activity_details in job reports)
    # This needs to be defined before it's used in chart building
    recruiter_activity_details = []
    if candidate_ids:
        activity_rows = (
            db.query(CandidateActivity)
            .filter(
                CandidateActivity.user_id == recruiter_id,
                CandidateActivity.candidate_id.in_(candidate_ids),
                CandidateActivity.created_at >= date_start,
                CandidateActivity.created_at < date_end
            )
            .order_by(CandidateActivity.created_at.desc())
            .all()
        )
        
        candidate_map_full = {c.candidate_id: c for c in db.query(Candidates).filter(Candidates.candidate_id.in_(candidate_ids)).all()}
        
        for row in activity_rows:
            cand = candidate_map_full.get(row.candidate_id)
            cand_name = getattr(cand, "candidate_name", None) if cand else None
            
            recruiter_activity_details.append({
                "activity_type": row.type.value if isinstance(row.type, CandidateActivityType) else str(row.type),
                "candidate_id": row.candidate_id,
                "candidate_name": cand_name,
                "remarks": row.remark,
                "created_at": to_ist(row.created_at).isoformat() if row.created_at else None,
            })
    
    # Build charts
    daily_status_trends = [
        {
            "date": d["date"],
            "sourced": d["sourced"],
            "screened": d["screened"],
            "lined_up": d["lined_up"],
            "turned_up": d["turned_up"],
            "offer_accepted": d["offer_accepted"],
        }
        for d in daily_breakdown
    ]
    
    daily_joined_rejected = [
        {
            "date": d["date"],
            "joined": d["joined"],
            "rejected": d["rejected"],
        }
        for d in daily_breakdown
    ]
    
    # Jobs performance for this recruiter
    jobs_performance = [
        {
            "job_title": j["job_title"],
            "candidates": j["candidates"],
            "joined": j["joined"],
        }
        for j in jobs_assigned[:20]  # Top 20 jobs
    ]
    
    # Get login logs for this recruiter
    login_logs = []
    session_rows = (
        db.query(LoginSession)
        .filter(
            LoginSession.user_id == recruiter_id,
            LoginSession.login_at >= date_start,
            LoginSession.login_at < date_end
        )
        .order_by(LoginSession.login_at.desc())
        .all()
    )
    
    for session in session_rows:
        login_logs.append({
            "session_id": session.session_id,
            "login_at": to_ist(session.login_at).isoformat() if session.login_at else None,
            "is_active": session.is_active if hasattr(session, 'is_active') else None,
        })
    
    return {
        "recruiter_metadata": recruiter_metadata,
        "summary_tiles": summary_tiles,
        "jobs_assigned": jobs_assigned,
        "daily_breakdown": daily_breakdown,
        "recruiter_activity_details": recruiter_activity_details,
        "login_logs": login_logs,
        "charts": {
            "daily_status_trends": daily_status_trends,
            "daily_joined_rejected": daily_joined_rejected,
            "jobs_performance": jobs_performance,
        },
        "date_range": {
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "is_daily": is_daily,
            "date_range_days": date_range_days,
            "group_type": group_type
        }
    }

