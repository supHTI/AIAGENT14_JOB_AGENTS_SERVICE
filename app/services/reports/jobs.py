"""
Job-related report services with richer analytics payloads.
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
    CandidatePipelineStatus,
    Candidates,
    Company,
    JobOpenings,
    PipelineStage,
    Pipeline,
    PipelineStageStatus,
    PipelineStageStatusTag,
    CompanySpoc,
    User,
    UserJobsAssigned,
)
from app.repositories import get_job_funnel, get_jobs_overview
from app.schemas.reports import FunnelMetrics, JobOverviewItem, JobOverviewResponse, JobOverviewSummary, ReportFilter

# Threshold (in days) to flag jobs nearing their deadline
DEADLINE_RISK_DAYS = 5


def _date_clauses(model_col, filters: ReportFilter):
    clauses = []
    if filters.date_from:
        clauses.append(model_col >= filters.date_from)
    if filters.date_to:
        clauses.append(model_col <= filters.date_to + timedelta(days=1))
    return clauses


def build_overview(db, filters: ReportFilter) -> JobOverviewResponse:
    summary_raw, items_raw = get_jobs_overview(db, filters)
    items = [JobOverviewItem(**item) for item in items_raw]
    summary = JobOverviewSummary(**summary_raw)
    return JobOverviewResponse(summary=summary, items=items)


def build_funnel(db, job_id: int, filters: ReportFilter) -> FunnelMetrics:
    metrics = get_job_funnel(db, job_id, filters)
    return FunnelMetrics(job_id=job_id, job_public_id=str(job_id), **metrics)


def build_jobs_overview_report(db: Session, filters: ReportFilter) -> Dict[str, Mapping]:
    """
    Build an enriched jobs overview payload for export (no email side-effects).
    Only date filters are honored for this view.
    """
    jobs_q = db.query(JobOpenings)
    if filters.date_from or filters.date_to:
        jobs_q = jobs_q.filter(*_date_clauses(JobOpenings.created_at, filters))
    jobs = jobs_q.all()
    job_ids = [j.id for j in jobs]
    company_ids = [j.company_id for j in jobs]
    pipeline_ids = [j.pipeline_id for j in jobs if j.pipeline_id]
    main_spoc_ids = {j.main_spoc_id for j in jobs if j.main_spoc_id}
    internal_spoc_ids = {j.internal_spoc_id for j in jobs if j.internal_spoc_id}
    creator_ids = {j.created_by for j in jobs if j.created_by}
    updater_ids = {j.updated_by for j in jobs if j.updated_by}
    company_rows = (
        db.query(Company.id, Company.company_name)
        .filter(Company.id.in_(company_ids) if company_ids else True)
        .all()
    )
    company_map = {cid: cname for cid, cname in company_rows}

    pipeline_rows = []
    if pipeline_ids:
        pipeline_rows = (
            db.query(Pipeline.id, Pipeline.name)
            .filter(Pipeline.id.in_(pipeline_ids))
            .all()
        )
    pipeline_map = {pid: pname for pid, pname in pipeline_rows}

    spoc_rows = []
    spoc_ids = list(main_spoc_ids | internal_spoc_ids) if (main_spoc_ids or internal_spoc_ids) else []
    if spoc_ids:
        spoc_rows = db.query(CompanySpoc.id, CompanySpoc.spoc_name).filter(CompanySpoc.id.in_(spoc_ids)).all()
    spoc_map = {sid: sname for sid, sname in spoc_rows}

    user_rows = []
    # Internal SPOC is requested from users; fall back to CompanySpoc name if missing
    user_ids = list((creator_ids | updater_ids | internal_spoc_ids)) if (creator_ids or updater_ids or internal_spoc_ids) else []
    if user_ids:
        user_rows = db.query(User.id, User.name).filter(User.id.in_(user_ids)).all()
    user_map = {uid: uname for uid, uname in user_rows}
    now = datetime.utcnow()

    candidate_q = db.query(CandidateJobs.job_id, func.count(CandidateJobs.id))
    if job_ids:
        candidate_q = candidate_q.filter(CandidateJobs.job_id.in_(job_ids))
    candidate_counts = dict(candidate_q.group_by(CandidateJobs.job_id).all())

    joined_q = (
        db.query(CandidateJobs.job_id, func.count(CandidateJobStatus.id))
        .join(CandidateJobStatus, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(CandidateJobStatus.type == CandidateJobStatusType.joined)
    )
    if job_ids:
        joined_q = joined_q.filter(CandidateJobs.job_id.in_(job_ids))
    joined_counts = dict(joined_q.group_by(CandidateJobs.job_id).all())

    user_counts_q = (
        db.query(CandidateJobs.job_id, func.count(func.distinct(CandidateJobs.created_by)))
        .filter(CandidateJobs.created_by.isnot(None))
    )
    if job_ids:
        user_counts_q = user_counts_q.filter(CandidateJobs.job_id.in_(job_ids))
    user_counts = dict(user_counts_q.group_by(CandidateJobs.job_id).all())

    items: List[dict] = []
    for job in jobs:
        aging_days = (now - (job.created_at or now)).days
        status_str = str(job.status).strip()
        days_remaining = None
        if job.deadline:
            days_remaining = (job.deadline - date.today()).days
        items.append(
            {
                "job_id": job.id,
                "job_public_id": job.job_id,
                "title": job.title,
                "location": job.location,
                "company_id": job.company_id,
                "company_name": company_map.get(job.company_id),
                "main_spoc_id": job.main_spoc_id,
                "internal_spoc_id": job.internal_spoc_id,
                "main_spoc_name": spoc_map.get(job.main_spoc_id),
                "internal_spoc_name": user_map.get(job.internal_spoc_id) or spoc_map.get(job.internal_spoc_id),
                "openings": job.openings or 0,
                "aging_days": aging_days,
                "created_at": job.created_at,
                "updated_at": job.updated_at,
                "deleted_at": job.deleted_at,
                "created_by": job.created_by,
                "updated_by": job.updated_by,
                "created_by_name": user_map.get(job.created_by),
                "updated_by_name": user_map.get(job.updated_by),
                "deleted_by": job.deleted_by,
                "status": status_str,
                "candidate_count": candidate_counts.get(job.id, 0),
                "joined_count": joined_counts.get(job.id, 0),
                "pipeline_id": job.pipeline_id,
                "pipeline_name": pipeline_map.get(job.pipeline_id),
                "deadline": job.deadline,
                "days_remaining": days_remaining,
                "total_users": user_counts.get(job.id, 0),
                "job_type": job.job_type,
                "remote": job.remote,
                "work_mode": job.work_mode,
                "stage": job.stage,
                "salary_type": job.salary_type,
                "currency": job.currency,
                "min_salary": job.min_salary,
                "max_salary": job.max_salary,
                "skills_required": job.skills_required,
                "min_exp": job.min_exp,
                "max_exp": job.max_exp,
                "min_age": job.min_age,
                "max_age": job.max_age,
                "education_qualification": job.education_qualification,
                "educational_specialization": job.educational_specialization,
                "gender_preference": job.gender_preference,
                "communication": job.communication,
                "cooling_period": job.cooling_period,
                "bulk": job.bulk,
                "remarks": job.remarks,
            }
        )

    total_jobs = len(items)
    active_jobs = len([i for i in items if str(i["status"]).lower() in {"active", "open"}])
    inactive_jobs = len([i for i in items if str(i["status"]).lower() == "inactive"])
    closed_jobs = len([i for i in items if str(i["status"]).lower() in {"closed", "inactive", "archived"}])
    total_hired = sum(i["joined_count"] for i in items)
    # Only include ACTIVE job openings in total_openings
    total_openings = sum(i["openings"] for i in items if str(i["status"]).lower() in {"active", "open"})

    positions_at_risk = [
        i
        for i in items
        if i.get("days_remaining") is not None
        and i["days_remaining"] < DEADLINE_RISK_DAYS
        and str(i["status"]).lower() in {"active", "open"}
    ]

    job_per_company_rows = (
        db.query(JobOpenings.company_id, func.count(JobOpenings.id))
        .filter(JobOpenings.id.in_(job_ids) if job_ids else True)
        .group_by(JobOpenings.company_id)
        .all()
    )
    job_per_company = [
        {"company_id": cid, "name": company_map.get(cid, f"Company {cid}"), "jobs": count}
        for cid, count in job_per_company_rows
    ]

    timeline: Dict[date, int] = {}
    for job in jobs:
        day = (job.created_at or now).date()
        timeline[day] = timeline.get(day, 0) + 1
    new_jobs_daily = [{"label": d.isoformat(), "count": cnt} for d, cnt in sorted(timeline.items())]

    candidates_per_job = [{"job_id": i["job_id"], "title": i["title"], "count": i["candidate_count"]} for i in items]
    accepted_per_job = [{"job_id": i["job_id"], "title": i["title"], "accepted": i["joined_count"]} for i in items]

    candidate_joined_subquery = (
        db.query(CandidateJobStatus.candidate_job_id)
        .filter(
            CandidateJobStatus.type == CandidateJobStatusType.joined
        )
        .subquery()
    )

    candidate_rejected_dropped_subquery = (
        db.query(CandidateJobStatus.candidate_job_id)
        .filter(
            CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped])
        )
        .subquery()
    )

    # Main clawback query
    # Get Job ID and count of candidate_jobs that meet criteria:
    # 1. Have a 'joined' status in future
    # 2. Do NOT have 'rejected' or 'dropped' status
    clawback_q = (
        db.query(CandidateJobs.job_id, func.count(CandidateJobs.id))
        .join(candidate_joined_subquery, CandidateJobs.id == candidate_joined_subquery.c.candidate_job_id)
        .outerjoin(candidate_rejected_dropped_subquery, CandidateJobs.id == candidate_rejected_dropped_subquery.c.candidate_job_id)
        .filter(candidate_rejected_dropped_subquery.c.candidate_job_id == None)
        .group_by(CandidateJobs.job_id)
    )

    clawback_counts_raw = clawback_q.all()
    # map to dict
    clawback_map = {job_id: count for job_id, count in clawback_counts_raw}
    clawback_per_job = [{"job_id": i["job_id"], "title": i["title"], "cases": clawback_map.get(i["job_id"], 0)} for i in items]

    summary_tiles = [
        ("Total jobs", total_jobs),
        ("Active jobs", active_jobs),
        ("Closed jobs", closed_jobs),
        ("Total openings", total_openings),
        ("Candidates hired", total_hired),
    ]

    return {
        "summary_tiles": summary_tiles,
        "positions_at_risk": positions_at_risk,
        "charts": {
            "jobs_per_company": job_per_company,
            "new_jobs_daily": new_jobs_daily,
            "candidates_per_job": candidates_per_job,
            "accepted_per_job": accepted_per_job,
            "clawback_per_job": clawback_per_job,
        },
        "table": items,
    }


def build_job_details_report(db: Session, job_id: int, filters: ReportFilter) -> Dict[str, Mapping]:
    def to_ist(dt_val):
        if not dt_val:
            return None
        ist_delta = timedelta(hours=5, minutes=30)
        if isinstance(dt_val, datetime):
            return dt_val + ist_delta
        # treat date as midnight UTC then convert
        if isinstance(dt_val, date):
            return datetime.combine(dt_val, datetime.min.time()) + ist_delta
        return dt_val

    job = db.query(JobOpenings).filter(JobOpenings.id == job_id).first()
    if not job:
        raise ValueError("Job not found")

    # Get company name
    company = db.query(Company).filter(Company.id == job.company_id).first()
    company_name = company.company_name if company else f"Company {job.company_id}"

    # Get created_by user name
    created_by_user = None
    if job.created_by:
        created_by_user = db.query(User).filter(User.id == job.created_by).first()
    created_by_name = created_by_user.name if created_by_user else "N/A"

    candidate_jobs_q = db.query(CandidateJobs).filter(CandidateJobs.job_id == job_id)
    if filters.date_from or filters.date_to:
        candidate_jobs_q = candidate_jobs_q.filter(*_date_clauses(CandidateJobs.created_at, filters))
    candidate_jobs = candidate_jobs_q.all()
    candidate_job_ids = [cj.id for cj in candidate_jobs]
    candidate_ids = [cj.candidate_id for cj in candidate_jobs]
    assigned_to_ids = set()
    candidate_assign_map = {}
    user_map: Dict[int, str] = {}
    base_user_ids = set()
    if job.created_by:
        base_user_ids.add(job.created_by)
    if job.updated_by:
        base_user_ids.add(job.updated_by)
    if candidate_ids:
        candidate_assign_rows = (
            db.query(Candidates.candidate_id, Candidates.assigned_to, Candidates.candidate_name)
            .filter(Candidates.candidate_id.in_(candidate_ids))
            .all()
        )
        for cid, assigned_to, cand_name in candidate_assign_rows:
            candidate_assign_map[cid] = assigned_to
            if cand_name:
                candidate_assign_map[(cid, "name")] = cand_name
            if assigned_to:
                assigned_to_ids.add(assigned_to)
                base_user_ids.add(assigned_to)

    if base_user_ids:
        base_user_rows = db.query(User.id, User.name).filter(User.id.in_(base_user_ids)).all()
        for uid, uname in base_user_rows:
            user_map[uid] = uname

    # Enrich user_map with assigned_to users
    if assigned_to_ids:
        missing_user_ids = [uid for uid in assigned_to_ids if uid not in user_map]
        if missing_user_ids:
            extra_user_rows = db.query(User.id, User.name).filter(User.id.in_(missing_user_ids)).all()
            for uid, uname in extra_user_rows:
                user_map[uid] = uname

    active_candidates = len(candidate_jobs)
    distinct_hrs = (
        db.query(func.count(func.distinct(CandidateJobs.created_by)))
        .filter(CandidateJobs.job_id == job_id, CandidateJobs.created_by.isnot(None))
        .scalar()
    )

    pipeline_stage_count = (
        db.query(func.count(PipelineStage.id)).filter(PipelineStage.pipeline_id == job.pipeline_id).scalar() or 0
    )

    # Get joined count (Closed)
    joined_count = (
        db.query(func.count(CandidateJobStatus.id))
        .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id == job_id,
            CandidateJobStatus.type == CandidateJobStatusType.joined,
        )
        .scalar() or 0
    )

    # Convert cooling period from months to days (integer)
    cooling_period_days = None
    if job.cooling_period:
        # Assuming cooling_period is in months, convert to days (30 days per month)
        cooling_period_days = int(float(job.cooling_period))

    # Updated tiles as per requirements
    summary_tiles = [
        ("Openings", job.openings or 0),
        ("Closed", joined_count),
        ("Deadline", job.deadline.strftime("%Y-%m-%d") if job.deadline else "-"),
        ("Days Remaining", max((job.deadline - date.today()).days, 0) if job.deadline else "-"),
        ("Cooling Period", f"{cooling_period_days} days" if cooling_period_days else "-"),
    ]

    # Job metadata for header section
    job_metadata = {
        "job_title": job.title,
        "job_id": job.job_id,
        "company_name": company_name,
        "created_at": job.created_at,
        "created_by": created_by_name,
        "status": job.status,
    }

    # Get ALL pipeline stages for this pipeline (even with 0 candidates)
    all_pipeline_stages = []
    if job.pipeline_id:
        all_pipeline_stages = (
            db.query(
                PipelineStage.id,
                PipelineStage.name,
                PipelineStage.color_code,
                PipelineStage.order
            )
            .filter(PipelineStage.pipeline_id == job.pipeline_id)
            .order_by(PipelineStage.order)
            .all()
        )
    
    # Get candidate counts per stage (only for stages that have candidates)
    stage_counts_q = (
        db.query(
            PipelineStage.id,
            func.count(CandidatePipelineStatus.id).label('count')
        )
        .join(CandidatePipelineStatus, PipelineStage.id == CandidatePipelineStatus.pipeline_stage_id)
        .filter(CandidatePipelineStatus.latest == 1)
    )
    if candidate_job_ids:
        stage_counts_q = stage_counts_q.filter(CandidatePipelineStatus.candidate_job_id.in_(candidate_job_ids))
    if job.pipeline_id:
        stage_counts_q = stage_counts_q.filter(PipelineStage.pipeline_id == job.pipeline_id)
    stage_counts = dict(stage_counts_q.group_by(PipelineStage.id).all())
    
    # Calculate Joined and Rejected counts based on candidate_job_status
    # Use same logic as Total Joined Candidates Datewise query
    
    # Joined count: count all CandidateJobStatus records with type=joined for this job
    # (matching the logic used in joined_datewise query)
    joined_count_funnel = (
        db.query(func.count(CandidateJobStatus.id))
        .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id == job_id,
            CandidateJobStatus.type == CandidateJobStatusType.joined,
            CandidateJobStatus.joined_at.isnot(None)
        )
        .scalar() or 0
    )
    
    rejected_count_funnel = (
        db.query(func.count(CandidateJobStatus.id))
        .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id == job_id,
            CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped])
        )
        .scalar() or 0
    )
    # Build stage_flow_rows with ALL stages (including zeros)
    stage_flow_rows = []
    for stage_id, name, color_code, order in all_pipeline_stages:
        count = stage_counts.get(stage_id, 0)
        
        # Normalize color_code: ensure it has # prefix and is valid
        normalized_color = "#2563eb"  # Default blue
        if color_code:
            color_code_str = str(color_code).strip()
            if color_code_str:
                # Add # prefix if missing
                if not color_code_str.startswith("#"):
                    color_code_str = "#" + color_code_str
                # Validate it's a valid hex color (6 chars after #)
                if len(color_code_str) == 7 and all(c in "0123456789ABCDEFabcdef" for c in color_code_str[1:]):
                    normalized_color = color_code_str
        
        stage_flow_rows.append({
            "stage_id": stage_id,
            "stage_name": name,
            "color_code": normalized_color,
            "candidates": count
        })
    # Append joined/rejected aggregates for downstream exports
    stage_flow_rows.append({
        "stage_id": "joined",
        "stage_name": "Joined",
        "color_code": None,
        "candidates": joined_count_funnel,
    })
    stage_flow_rows.append({
        "stage_id": "rejected",
        "stage_name": "Rejected",
        "color_code": None,
        "candidates": rejected_count_funnel,
    })

    # Rejected count: count all CandidateJobStatus records with rejected or dropped for this job
    rejected_count_funnel = (
        db.query(func.count(CandidateJobStatus.id))
        .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id == job_id,
            CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped])
        )
        .scalar() or 0
    )

    # Time spent per stage (avg days) - include ALL stages from pipeline
    stage_times_rows = []
    stage_durations: Dict[int, List[float]] = {}  # stage_id -> list of durations in days
    
    if candidate_job_ids:
        histories = (
            db.query(CandidatePipelineStatus)
            .filter(CandidatePipelineStatus.candidate_job_id.in_(candidate_job_ids))
            .order_by(CandidatePipelineStatus.candidate_job_id, CandidatePipelineStatus.created_at)
            .all()
        )
        # compute per candidate durations
        last_seen: Dict[int, CandidatePipelineStatus] = {}
        for row in histories:
            prev = last_seen.get(row.candidate_job_id)
            if prev:
                # Convert to days
                delta_days = (row.created_at - prev.created_at).total_seconds() / (3600.0 * 24)
                stage_durations.setdefault(row.pipeline_stage_id, []).append(delta_days)
            last_seen[row.candidate_job_id] = row
    
    # Build stage_times_rows with ALL pipeline stages (including zeros)
    stage_map = {s.id: s for s in all_pipeline_stages} if all_pipeline_stages else {}
    for stage_id, name, color_code, order in all_pipeline_stages:
        values = stage_durations.get(stage_id, [])
        avg_days = round(sum(values) / len(values), 2) if values else 0
        stage_times_rows.append({
            "stage_id": stage_id,
            "stage_name": name,
            "avg_days": avg_days,
            "order": order
        })
    
    # Calculate average time for Accepted (Joined) and Rejected
    # Accepted: time from first pipeline status to joined_at
    # Rejected: time from first pipeline status to rejected_at
    accepted_times = []
    rejected_times = []
    
    if candidate_job_ids:
        # Get joined candidates with their timeline
        joined_cjs = (
            db.query(CandidateJobs.id, CandidateJobStatus.joined_at)
            .join(CandidateJobStatus, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(
                CandidateJobs.job_id == job_id,
                CandidateJobStatus.type == CandidateJobStatusType.joined,
                CandidateJobStatus.joined_at.isnot(None)
            )
            .all()
        )
        
        for cj_id, joined_at in joined_cjs:
            # Get first pipeline status for this candidate_job
            first_status = (
                db.query(CandidatePipelineStatus)
                .filter(CandidatePipelineStatus.candidate_job_id == cj_id)
                .order_by(CandidatePipelineStatus.created_at.asc())
                .first()
            )
            if first_status and joined_at:
                delta_days = (joined_at - first_status.created_at).total_seconds() / (3600.0 * 24)
                accepted_times.append(delta_days)
        
        # Get rejected/dropped candidates with their timeline
        rejected_cjs = (
            db.query(CandidateJobs.id, CandidateJobStatus.rejected_at)
            .join(CandidateJobStatus, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(
                CandidateJobs.job_id == job_id,
                CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]),
                CandidateJobStatus.rejected_at.isnot(None)
            )
            .all()
        )
        
        for cj_id, rejected_at in rejected_cjs:
            # Get first pipeline status for this candidate_job
            first_status = (
                db.query(CandidatePipelineStatus)
                .filter(CandidatePipelineStatus.candidate_job_id == cj_id)
                .order_by(CandidatePipelineStatus.created_at.asc())
                .first()
            )
            if first_status and rejected_at:
                delta_days = (rejected_at - first_status.created_at).total_seconds() / (3600.0 * 24)
                rejected_times.append(delta_days)
    
    avg_accepted_days = round(sum(accepted_times) / len(accepted_times), 2) if accepted_times else 0
    avg_rejected_days = round(sum(rejected_times) / len(rejected_times), 2) if rejected_times else 0
    
    # Sort stage_times by order
    stage_times_rows.sort(key=lambda x: x.get("order", 999))

    # Candidate details with stage
    candidate_rows: List[dict] = []
    if candidate_job_ids:
        latest_status = (
            db.query(CandidatePipelineStatus, Candidates)
            .join(CandidateJobs, CandidatePipelineStatus.candidate_job_id == CandidateJobs.id)
            .join(Candidates, Candidates.candidate_id == CandidateJobs.candidate_id)
            .filter(
                CandidatePipelineStatus.latest == 1,
                CandidatePipelineStatus.candidate_job_id.in_(candidate_job_ids),
            )
            .all()
        )
        for status_row, candidate in latest_status:
            stage_name = (
                db.query(PipelineStage.name).filter(PipelineStage.id == status_row.pipeline_stage_id).scalar()
                or status_row.pipeline_stage_id
            )
            candidate_rows.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "candidate_name": candidate.candidate_name,
                    "candidate_phone_number": candidate.candidate_phone_number,
                    "stage_name": stage_name,
                    "status": status_row.status,
                    "hr_name": user_map.get(candidate_assign_map.get(candidate.candidate_id)) if candidate_assign_map.get(candidate.candidate_id) else None,
                    "latest_remark": None,  # filled below if available
                }
            )

    # HR activities aggregated + detailed + latest remark per candidate
    hr_rows = []
    hr_activity_details = []
    latest_remark_by_candidate: Dict[str, str] = {}
    if candidate_ids:
        activity_rows = (
            db.query(CandidateActivity)
            .filter(CandidateActivity.candidate_id.in_(candidate_ids))
            .order_by(CandidateActivity.created_at.desc())
            .all()
        )
        user_map_activity = {u.id: u for u in db.query(User).filter(User.id.in_({r.user_id for r in activity_rows})).all()}
        candidate_map_full = {c.candidate_id: c for c in db.query(Candidates).filter(Candidates.candidate_id.in_(candidate_ids)).all()}

        agg_counts: Dict[tuple, int] = {}
        for row in activity_rows:
            key = (row.user_id, row.type)
            agg_counts[key] = agg_counts.get(key, 0) + 1

            cand = candidate_map_full.get(row.candidate_id)
            cand_name = getattr(cand, "candidate_name", None)
            hr_activity_details.append(
                {
                    "hr_name": getattr(user_map_activity.get(row.user_id), "name", None) or f"User {row.user_id}",
                    "activity_type": row.type.value if isinstance(row.type, CandidateActivityType) else str(row.type),
                    "candidate_id": row.candidate_id,
                    "candidate_name": cand_name,
                    "remarks": row.remark,
                    "created_at": to_ist(row.created_at).isoformat() if row.created_at else None,
                }
            )
            if row.remark and row.candidate_id not in latest_remark_by_candidate:
                latest_remark_by_candidate[row.candidate_id] = row.remark

        for (user_id, act_type), count in agg_counts.items():
            hr_rows.append(
                {
                    "user_id": user_id,
                    "user_name": getattr(user_map_activity.get(user_id), "name", None) or f"User {user_id}",
                    "activity_type": act_type.value if isinstance(act_type, CandidateActivityType) else str(act_type),
                    "count": count,
                }
            )

        # fill latest remark into candidate_rows
        for row in candidate_rows:
            cid = row.get("candidate_id")
            if cid in latest_remark_by_candidate:
                row["latest_remark"] = latest_remark_by_candidate[cid]

    # Funnel metrics (reuse existing)
    funnel = get_job_funnel(db, job_id, filters)

    # Clawback metrics based on candidate_job_status with stricter rules
    from collections import defaultdict

    status_rows = []
    if candidate_job_ids:
        status_rows = (
            db.query(CandidateJobStatus)
            .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(CandidateJobs.job_id == job_id)
            .all()
        )
    status_by_cj: Dict[int, List[CandidateJobStatus]] = defaultdict(list)
    for row in status_rows:
        status_by_cj[row.candidate_job_id].append(row)

    today = date.today()
    cp_days_int = None
    if job.cooling_period:
        try:
            cp_days_int = int(float(job.cooling_period))
        except Exception:
            cp_days_int = None

    clawback_cases = []
    clawback_completed_today: List[dict] = []
    clawback_drop_today: List[dict] = []

    for cj in candidate_jobs:
        st_list = status_by_cj.get(cj.id, [])
        joined_statuses = [s for s in st_list if s.type == CandidateJobStatusType.joined and s.joined_at]
        has_reject_drop = any(s.type in [CandidateJobStatusType.rejected, CandidateJobStatusType.dropped] for s in st_list)

        # Track drop/reject today
        for s in st_list:
            if s.type in [CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]:
                s_date = (s.rejected_at or s.created_at or datetime.utcnow()).date()
                if s_date == today:
                    clawback_drop_today.append(
                        {
                            "candidate_id": cj.candidate_id,
                            "candidate_name": candidate_assign_map.get((cj.candidate_id, "name")),
                            "status": s.type.value if isinstance(s.type, CandidateJobStatusType) else str(s.type),
                            "date": s_date,
                        }
                    )

        if not joined_statuses:
            continue

        # Clause: joined present, no other records, no reject/drop
        other_statuses = [s for s in st_list if s.type != CandidateJobStatusType.joined]
        if other_statuses:
            continue
        if has_reject_drop:
            continue

        joined_status = joined_statuses[0]
        completion_date = None
        if cp_days_int is not None and joined_status.joined_at:
            completion_date = (joined_status.joined_at + timedelta(days=cp_days_int)).date()

        recruiter_id = candidate_assign_map.get(cj.candidate_id)
        clawback_case = {
            "candidate_job_id": cj.id,
            "candidate_id": cj.candidate_id,
            "candidate_name": candidate_assign_map.get((cj.candidate_id, "name")),
            "recruiter_id": recruiter_id,
            "recruiter_name": user_map.get(recruiter_id, f"User {recruiter_id}") if recruiter_id else "N/A",
            "joined_on": joined_status.joined_at.date() if joined_status.joined_at else None,
            "completion_date": completion_date,
        }
        clawback_cases.append(clawback_case)
        if completion_date and completion_date == today:
            clawback_completed_today.append(clawback_case)

    total_clawback = len(clawback_cases)
    clawback_completed = len([c for c in clawback_cases if c.get("completion_date") and c["completion_date"] <= today])
    clawback_dropped_count = sum(
        1
        for st_list in status_by_cj.values()
        if any(s.type == CandidateJobStatusType.joined for s in st_list)
        and any(s.type in [CandidateJobStatusType.rejected, CandidateJobStatusType.dropped] for s in st_list)
    )
    clawback_pending = max(total_clawback - clawback_completed - clawback_dropped_count, 0)
    recovery_rate = round((clawback_completed / total_clawback) * 100, 2) if total_clawback else 0.0

    clawback_metrics = {
        "total_cases": total_clawback,
        "completed": clawback_completed,
        "dropped": clawback_dropped_count,
        "pending": clawback_pending,
        "recovery_rate": recovery_rate,
        "completed_today": clawback_completed_today,
        "drop_today": clawback_drop_today,
        "pending_vs_recovered": [
            {"label": "Recovered", "value": clawback_completed},
            {"label": "Pending", "value": clawback_pending},
            {"label": "Dropped", "value": clawback_dropped_count},
        ],
        "all_cases": clawback_cases,
    }

    # Recruiter Ranking table data - include ALL assigned recruiters
    # Get all assigned recruiters from user_jobs_assigned
    all_assigned_recruiters = (
        db.query(UserJobsAssigned.user_id)
        .filter(UserJobsAssigned.job_id == job_id)
        .distinct()
        .all()
    )
    all_assigned_recruiter_ids = {row[0] for row in all_assigned_recruiters}
    
    # Calculate activity counts for each recruiter (for ranking)
    activity_counts: Dict[int, int] = {}
    if all_assigned_recruiter_ids and candidate_job_ids:
        # Count activities in date range
        date_filter_start = None
        date_filter_end = None
        if filters.date_from:
            date_filter_start = datetime.combine(filters.date_from, datetime.min.time())
        if filters.date_to:
            date_filter_end = datetime.combine(filters.date_to, datetime.min.time()) + timedelta(days=1)
        
        # Count CandidatePipelineStatus activities
        pipeline_activity_query = (
            db.query(CandidatePipelineStatus.created_by, func.count(CandidatePipelineStatus.id))
            .filter(
                CandidatePipelineStatus.candidate_job_id.in_(candidate_job_ids),
                CandidatePipelineStatus.created_by.in_(all_assigned_recruiter_ids),
                CandidatePipelineStatus.created_by.isnot(None)
            )
        )
        if date_filter_start:
            pipeline_activity_query = pipeline_activity_query.filter(CandidatePipelineStatus.created_at >= date_filter_start)
        if date_filter_end:
            pipeline_activity_query = pipeline_activity_query.filter(CandidatePipelineStatus.created_at < date_filter_end)
        for user_id, count in pipeline_activity_query.group_by(CandidatePipelineStatus.created_by).all():
            activity_counts[user_id] = activity_counts.get(user_id, 0) + count
        
        # Count CandidateJobStatus activities
        status_activity_query = (
            db.query(CandidateJobStatus.created_by, func.count(CandidateJobStatus.id))
            .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(
                CandidateJobs.job_id == job_id,
                CandidateJobStatus.created_by.in_(all_assigned_recruiter_ids),
                CandidateJobStatus.created_by.isnot(None)
            )
        )
        if date_filter_start:
            status_activity_query = status_activity_query.filter(CandidateJobStatus.created_at >= date_filter_start)
        if date_filter_end:
            status_activity_query = status_activity_query.filter(CandidateJobStatus.created_at < date_filter_end)
        for user_id, count in status_activity_query.group_by(CandidateJobStatus.created_by).all():
            activity_counts[user_id] = activity_counts.get(user_id, 0) + count
        
        # Count CandidateActivity activities
        if candidate_ids:
            activity_activity_query = (
                db.query(CandidateActivity.user_id, func.count(CandidateActivity.id))
                .filter(
                    CandidateActivity.candidate_id.in_(candidate_ids),
                    CandidateActivity.user_id.in_(all_assigned_recruiter_ids),
                    CandidateActivity.user_id.isnot(None)
                )
            )
            if date_filter_start:
                activity_activity_query = activity_activity_query.filter(CandidateActivity.created_at >= date_filter_start)
            if date_filter_end:
                activity_activity_query = activity_activity_query.filter(CandidateActivity.created_at < date_filter_end)
            for user_id, count in activity_activity_query.group_by(CandidateActivity.user_id).all():
                activity_counts[user_id] = activity_counts.get(user_id, 0) + count
        
        # Count CandidateJobs created
        jobs_activity_query = (
            db.query(CandidateJobs.created_by, func.count(CandidateJobs.id))
            .filter(
                CandidateJobs.job_id == job_id,
                CandidateJobs.created_by.in_(all_assigned_recruiter_ids),
                CandidateJobs.created_by.isnot(None)
            )
        )
        if date_filter_start:
            jobs_activity_query = jobs_activity_query.filter(CandidateJobs.created_at >= date_filter_start)
        if date_filter_end:
            jobs_activity_query = jobs_activity_query.filter(CandidateJobs.created_at < date_filter_end)
        for user_id, count in jobs_activity_query.group_by(CandidateJobs.created_by).all():
            activity_counts[user_id] = activity_counts.get(user_id, 0) + count
    
    # Build assignment stats for all assigned recruiters
    assignment_stats: Dict[int, dict] = {}
    for recruiter_id in all_assigned_recruiter_ids:
        assignment_stats[recruiter_id] = {"candidates": 0, "joined": 0, "rejected": 0}
    
    # Populate stats from candidate_jobs
    for cj in candidate_jobs:
        recruiter_id = candidate_assign_map.get(cj.candidate_id)
        if recruiter_id and recruiter_id in all_assigned_recruiter_ids:
            stats = assignment_stats[recruiter_id]
            stats["candidates"] += 1
        st_list = status_by_cj.get(cj.id, [])
        if any(s.type == CandidateJobStatusType.joined for s in st_list):
            stats["joined"] += 1
        if any(s.type in [CandidateJobStatusType.rejected, CandidateJobStatusType.dropped] for s in st_list):
            stats["rejected"] += 1

    # Calculate active_user_ids before building recruiter ranking
    # This is needed to determine which recruiters are active
    active_user_ids = set()
    if all_assigned_recruiter_ids:
        # Determine date range for activity check
        # If filters have date_from/date_to, use those; otherwise check all time
        date_filter_start = None
        date_filter_end = None
        if filters.date_from:
            date_filter_start = datetime.combine(filters.date_from, datetime.min.time())
        if filters.date_to:
            date_filter_end = datetime.combine(filters.date_to, datetime.min.time()) + timedelta(days=1)
        
        # From CandidateJobs
        jobs_query = (
            db.query(CandidateJobs.created_by)
            .filter(
                CandidateJobs.job_id == job_id,
                CandidateJobs.created_by.in_(all_assigned_recruiter_ids),
                CandidateJobs.created_by.isnot(None)
            )
        )
        if date_filter_start:
            jobs_query = jobs_query.filter(CandidateJobs.created_at >= date_filter_start)
        if date_filter_end:
            jobs_query = jobs_query.filter(CandidateJobs.created_at < date_filter_end)
        active_from_jobs = jobs_query.distinct().all()
        active_user_ids.update(row[0] for row in active_from_jobs)
        
        # From CandidatePipelineStatus (for this job's candidate_jobs)
        if candidate_job_ids:
            pipeline_query = (
                db.query(CandidatePipelineStatus.created_by)
                .filter(
                    CandidatePipelineStatus.candidate_job_id.in_(candidate_job_ids),
                    CandidatePipelineStatus.created_by.in_(all_assigned_recruiter_ids),
                    CandidatePipelineStatus.created_by.isnot(None)
                )
            )
            if date_filter_start:
                pipeline_query = pipeline_query.filter(CandidatePipelineStatus.created_at >= date_filter_start)
            if date_filter_end:
                pipeline_query = pipeline_query.filter(CandidatePipelineStatus.created_at < date_filter_end)
            active_from_pipeline = pipeline_query.distinct().all()
            active_user_ids.update(row[0] for row in active_from_pipeline)
        
        # From CandidateJobStatus (for this job's candidate_jobs)
        if candidate_job_ids:
            status_query = (
                db.query(CandidateJobStatus.created_by)
                .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
                .filter(
                    CandidateJobs.job_id == job_id,
                    CandidateJobStatus.created_by.in_(all_assigned_recruiter_ids),
                    CandidateJobStatus.created_by.isnot(None)
                )
            )
            if date_filter_start:
                status_query = status_query.filter(CandidateJobStatus.created_at >= date_filter_start)
            if date_filter_end:
                status_query = status_query.filter(CandidateJobStatus.created_at < date_filter_end)
            active_from_status = status_query.distinct().all()
            active_user_ids.update(row[0] for row in active_from_status)
        
        # From CandidateActivity (for candidates in this job)
        if candidate_ids:
            activity_query = (
                db.query(CandidateActivity.user_id)
                .filter(
                    CandidateActivity.candidate_id.in_(candidate_ids),
                    CandidateActivity.user_id.in_(all_assigned_recruiter_ids),
                    CandidateActivity.user_id.isnot(None)
                )
            )
            if date_filter_start:
                activity_query = activity_query.filter(CandidateActivity.created_at >= date_filter_start)
            if date_filter_end:
                activity_query = activity_query.filter(CandidateActivity.created_at < date_filter_end)
            active_from_activity = activity_query.distinct().all()
            active_user_ids.update(row[0] for row in active_from_activity)

    # Calculate completed clawback count per recruiter
    today = date.today()
    completed_clawback_per_recruiter = {}
    if clawback_metrics and clawback_metrics.get("all_cases"):
        for case in clawback_metrics["all_cases"]:
            recruiter_id = case.get("recruiter_id")
            if recruiter_id and case.get("completion_date") and case["completion_date"] <= today:
                completed_clawback_per_recruiter[recruiter_id] = completed_clawback_per_recruiter.get(recruiter_id, 0) + 1
    
    # Build recruiter ranking with all assigned recruiters
    recruiter_assignments = []
    for rid in all_assigned_recruiter_ids:
        stats = assignment_stats.get(rid, {"candidates": 0, "joined": 0, "rejected": 0})
        user = db.query(User).filter(User.id == rid).first()
        recruiter_name = user.name if user else f"User {rid}"
        is_active = rid in active_user_ids
        completed_clawback = completed_clawback_per_recruiter.get(rid, 0)
        
        recruiter_assignments.append({
            "recruiter_id": rid,
            "recruiter_name": recruiter_name,
            "candidates": stats["candidates"],
            "joined": stats["joined"],
            "rejected": stats["rejected"],
            "active": is_active,
            "activity_count": activity_counts.get(rid, 0),
            "completed_clawback": completed_clawback,
        })
    
    # Rank by: 1) max(joined, completed_clawback), 2) highest activity, 3) highest candidates
    best_hr = sorted(
        recruiter_assignments,
        key=lambda x: (max(x.get("joined", 0), x.get("completed_clawback", 0)), x.get("activity_count", 0), x.get("candidates", 0)),
        reverse=True
    )

    extras = {
        "clawback_metrics": clawback_metrics,
        "recruiter_assignments": recruiter_assignments,
    }

    # Pipeline velocity (movement per day) - only latest statuses for this job's candidates
    velocity_q = (
        db.query(func.date(CandidatePipelineStatus.created_at), func.count(CandidatePipelineStatus.id))
        .join(CandidateJobs, CandidatePipelineStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id == job_id,
            CandidatePipelineStatus.latest == 1,
        )
    )
    velocity_rows = velocity_q.group_by(func.date(CandidatePipelineStatus.created_at)).all()
    velocity_map = {}
    for day, count in velocity_rows:
        ist_day = to_ist(day).date() if day else day
        velocity_map[ist_day] = count
    start_date = to_ist(job.created_at).date() if job.created_at else datetime.utcnow().date()
    end_date = max(velocity_map.keys()) if velocity_map else start_date
    velocity = []
    cur = start_date
    while cur <= end_date:
        velocity.append({"label": str(cur), "moves": velocity_map.get(cur, 0)})
        cur += timedelta(days=1)

    # Joined candidates datewise (joined)
    joined_datewise_q = (
        db.query(func.date(CandidateJobStatus.joined_at), func.count(CandidateJobStatus.id))
        .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id == job_id,
            CandidateJobStatus.type == CandidateJobStatusType.joined,
            CandidateJobStatus.joined_at.isnot(None)
        )
        .group_by(func.date(CandidateJobStatus.joined_at))
        .order_by(func.date(CandidateJobStatus.joined_at))
    )
    joined_datewise_rows = joined_datewise_q.all()
    joined_datewise = [{"label": str(to_ist(day).date()), "count": count} for day, count in joined_datewise_rows]

    # Rejected/Dropped datewise
    rejected_datewise_q = (
        db.query(func.date(CandidateJobStatus.rejected_at), func.count(CandidateJobStatus.id))
        .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id == job_id,
            CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]),
            CandidateJobStatus.rejected_at.isnot(None)
        )
        .group_by(func.date(CandidateJobStatus.rejected_at))
        .order_by(func.date(CandidateJobStatus.rejected_at))
    )
    rejected_datewise_rows = rejected_datewise_q.all()
    rejected_datewise = [{"label": str(to_ist(day).date()), "count": count} for day, count in rejected_datewise_rows]

    # Recruiter Metrics
    # 1. Total Recruiters: count from user_jobs_assigned table
    total_recruiters = (
        db.query(func.count(func.distinct(UserJobsAssigned.user_id)))
        .filter(UserJobsAssigned.job_id == job_id)
        .scalar() or 0
    )

    # 2. Active Recruiters: active_user_ids was already calculated above in the recruiter ranking section
    active_recruiters = len(active_user_ids)

    # 3. Recruiter Closed Maximum Jobs
    # Get all joined candidate_job_ids for this job (without reject/drop)
    joined_cjs_valid = (
        db.query(CandidateJobStatus.candidate_job_id, CandidateJobStatus.created_by)
        .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id == job_id,
            CandidateJobStatus.type == CandidateJobStatusType.joined,
            CandidateJobStatus.joined_at.isnot(None)
        )
        .all()
    )
    
    # Get rejected/dropped candidate_job_ids for this job
    rejected_dropped_cjs = (
        db.query(CandidateJobStatus.candidate_job_id)
        .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id == job_id,
            CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped])
        )
        .distinct()
        .all()
    )
    rejected_dropped_set = {row[0] for row in rejected_dropped_cjs}
    
    # Count valid joined by recruiter (excluding those with reject/drop)
    closed_by_recruiter_dict = {}
    for cj_id, created_by in joined_cjs_valid:
        if cj_id not in rejected_dropped_set:
            closed_by_recruiter_dict[created_by] = closed_by_recruiter_dict.get(created_by, 0) + 1
    
    closed_by_recruiter_filtered = list(closed_by_recruiter_dict.items())
    
    # Get top recruiter
    top_recruiter_id = None
    top_recruiter_name = "N/A"
    top_recruiter_closed = 0
    if closed_by_recruiter_filtered:
        top_recruiter_id, top_recruiter_closed = max(closed_by_recruiter_filtered, key=lambda x: x[1])
        if top_recruiter_id:
            top_recruiter_user = db.query(User).filter(User.id == top_recruiter_id).first()
            top_recruiter_name = top_recruiter_user.name if top_recruiter_user else f"User {top_recruiter_id}"

    # 4. Top 10 Recruiters Ranking (based on closed jobs)
    top_recruiters_ranking = []
    sorted_recruiters = sorted(closed_by_recruiter_filtered, key=lambda x: x[1], reverse=True)[:10]
    for user_id, closed_count in sorted_recruiters:
        user = db.query(User).filter(User.id == user_id).first()
        recruiter_name = user.name if user else f"User {user_id}"
        top_recruiters_ranking.append({
            "recruiter_id": user_id,
            "recruiter_name": recruiter_name,
            "closed_count": closed_count
        })

    # 5. Candidates Per Recruiter (include all assigned recruiters, even with 0 candidates)
    candidates_per_recruiter_q = (
        db.query(
            Candidates.assigned_to,
            func.count(CandidateJobs.id).label('candidate_count')
        )
        .join(CandidateJobs, Candidates.candidate_id == CandidateJobs.candidate_id)
        .filter(
            CandidateJobs.job_id == job_id,
            Candidates.assigned_to.isnot(None),
            Candidates.assigned_to.in_(all_assigned_recruiter_ids)
        )
        .group_by(Candidates.assigned_to)
    )
    candidates_per_recruiter_rows = candidates_per_recruiter_q.all()
    candidates_per_recruiter_dict = {row[0]: row[1] for row in candidates_per_recruiter_rows}
    
    candidates_per_recruiter = []
    for recruiter_id in all_assigned_recruiter_ids:
        user = db.query(User).filter(User.id == recruiter_id).first()
        recruiter_name = user.name if user else f"User {recruiter_id}"
        candidates_per_recruiter.append({
            "recruiter_name": recruiter_name,
            "candidate_count": candidates_per_recruiter_dict.get(recruiter_id, 0)
        })
    candidates_per_recruiter.sort(key=lambda x: x["candidate_count"], reverse=True)

    # 6. Rejected or Dropped by Recruiter (include all assigned recruiters, even with 0 rejected)
    rejected_dropped_by_recruiter_q = (
        db.query(
            CandidateJobStatus.created_by,
            func.count(CandidateJobStatus.id).label('rejected_count')
        )
        .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id == job_id,
            CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]),
            CandidateJobStatus.created_by.in_(all_assigned_recruiter_ids)
        )
        .group_by(CandidateJobStatus.created_by)
    )
    rejected_dropped_by_recruiter_rows = rejected_dropped_by_recruiter_q.all()
    rejected_dropped_by_recruiter_dict = {row[0]: row[1] for row in rejected_dropped_by_recruiter_rows}
    
    rejected_dropped_by_recruiter = []
    for recruiter_id in all_assigned_recruiter_ids:
        user = db.query(User).filter(User.id == recruiter_id).first()
        recruiter_name = user.name if user else f"User {recruiter_id}"
        rejected_dropped_by_recruiter.append({
            "recruiter_name": recruiter_name,
            "rejected_count": rejected_dropped_by_recruiter_dict.get(recruiter_id, 0)
        })
    rejected_dropped_by_recruiter.sort(key=lambda x: x["rejected_count"], reverse=True)

    recruiter_metrics = {
        "total_recruiters": total_recruiters,
        "active_recruiters": active_recruiters,
        "inactive_recruiters": max(total_recruiters - active_recruiters, 0),
        "top_recruiter": {
            "name": top_recruiter_name,
            "closed_count": top_recruiter_closed
        },
        "top_recruiters_ranking": top_recruiters_ranking[:5],
        "candidates_per_recruiter": candidates_per_recruiter,
        "rejected_dropped_by_recruiter": rejected_dropped_by_recruiter,
        "recruiter_assignments": recruiter_assignments if 'recruiter_assignments' in locals() else [],
        "total_clawback_cases": total_clawback,
    }

    return {
        "job_metadata": job_metadata,
        "summary_tiles": summary_tiles,
        "stage_flow": stage_flow_rows,
        "stage_times": stage_times_rows,
        "hr_activities": hr_rows,
        "candidate_rows": candidate_rows,
        "best_hr": best_hr,
        "funnel": funnel,
        "extras": {
            **extras,
            "pipeline_velocity": velocity,
            "joined_datewise": joined_datewise,
            "rejected_datewise": rejected_datewise,
            "recruiter_metrics": recruiter_metrics,
            "hr_activity_details": hr_activity_details,
        },
        "funnel_counts": {
            "joined": joined_count_funnel,
            "rejected": rejected_count_funnel,
        },
        "avg_times": {
            "accepted_days": avg_accepted_days,
            "rejected_days": avg_rejected_days,
        },
    }


def build_job_daily_report(db: Session, job_id: int, from_date: date, to_date: date) -> Dict[str, Mapping]:
    """
    Build job report - similar to build_job_details_report but filters pipeline status
    and activities by the date range. Gets ALL candidate jobs but only shows pipeline
    status records and activities that happened within the date range.
    If from_date == to_date, it's a daily report.
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

    # Calculate date range (from start of from_date to end of to_date)
    date_start = datetime.combine(from_date, datetime.min.time())
    date_end = datetime.combine(to_date, datetime.min.time()) + timedelta(days=1)
    
    # Determine if it's a daily report
    is_daily = (from_date == to_date)
    
    # Calculate date range in days for graph type determination
    date_range_days = (to_date - from_date).days + 1

    job = db.query(JobOpenings).filter(JobOpenings.id == job_id).first()
    if not job:
        raise ValueError("Job not found")

    # Get company name
    company = db.query(Company).filter(Company.id == job.company_id).first()
    company_name = company.company_name if company else f"Company {job.company_id}"

    # Get created_by user name
    created_by_user = None
    if job.created_by:
        created_by_user = db.query(User).filter(User.id == job.created_by).first()
    created_by_name = created_by_user.name if created_by_user else "N/A"

    # Get ALL candidate jobs (not filtered by date for daily report)
    candidate_jobs = db.query(CandidateJobs).filter(CandidateJobs.job_id == job_id).all()
    candidate_job_ids = [cj.id for cj in candidate_jobs]
    candidate_ids = [cj.candidate_id for cj in candidate_jobs]
    assigned_to_ids = set()
    candidate_assign_map = {}
    user_map: Dict[int, str] = {}
    base_user_ids = set()
    if job.created_by:
        base_user_ids.add(job.created_by)
    if job.updated_by:
        base_user_ids.add(job.updated_by)
    if candidate_ids:
        candidate_assign_rows = (
            db.query(Candidates.candidate_id, Candidates.assigned_to, Candidates.candidate_name)
            .filter(Candidates.candidate_id.in_(candidate_ids))
            .all()
        )
        for cid, assigned_to, cand_name in candidate_assign_rows:
            candidate_assign_map[cid] = assigned_to
            if cand_name:
                candidate_assign_map[(cid, "name")] = cand_name
            if assigned_to:
                assigned_to_ids.add(assigned_to)
                base_user_ids.add(assigned_to)

    if base_user_ids:
        base_user_rows = db.query(User.id, User.name).filter(User.id.in_(base_user_ids)).all()
        for uid, uname in base_user_rows:
            user_map[uid] = uname

    # Enrich user_map with assigned_to users
    if assigned_to_ids:
        missing_user_ids = [uid for uid in assigned_to_ids if uid not in user_map]
        if missing_user_ids:
            extra_user_rows = db.query(User.id, User.name).filter(User.id.in_(missing_user_ids)).all()
            for uid, uname in extra_user_rows:
                user_map[uid] = uname

    active_candidates = len(candidate_jobs)
    distinct_hrs = (
        db.query(func.count(func.distinct(CandidateJobs.created_by)))
        .filter(CandidateJobs.job_id == job_id, CandidateJobs.created_by.isnot(None))
        .scalar()
    )

    pipeline_stage_count = (
        db.query(func.count(PipelineStage.id)).filter(PipelineStage.pipeline_id == job.pipeline_id).scalar() or 0
    )

    # Get joined count (Closed)
    joined_count = (
        db.query(func.count(CandidateJobStatus.id))
        .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id == job_id,
            CandidateJobStatus.type == CandidateJobStatusType.joined,
        )
        .scalar() or 0
    )

    # Convert cooling period from months to days (integer)
    cooling_period_days = None
    if job.cooling_period:
        cooling_period_days = int(float(job.cooling_period))

    # Get tag-based counts for the specific day from CandidateActivity
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
                CandidateJobs.job_id == job_id,
                CandidateActivity.candidate_id.in_(candidate_ids),
                CandidateActivity.type == CandidateActivityType.status,
                CandidateActivity.created_at >= date_start,
                CandidateActivity.created_at < date_end,
                cast(PipelineStageStatus.tag, String) == tag.value
            )
            .scalar()
        )
        return count or 0

    sourced_count = get_count_by_tag(PipelineStageStatusTag.SOURCING)
    screened_count = get_count_by_tag(PipelineStageStatusTag.SCREENING)
    lined_up_count = get_count_by_tag(PipelineStageStatusTag.LINE_UPS)
    turned_up_count = get_count_by_tag(PipelineStageStatusTag.TURN_UPS)
    offer_accepted_count = get_count_by_tag(PipelineStageStatusTag.OFFER_ACCEPTED)

    # Updated tiles with tag-based counts
    summary_tiles = [
        ("Openings", job.openings or 0),
        ("Closed", joined_count),
        ("Deadline", job.deadline.strftime("%Y-%m-%d") if job.deadline else "-"),
        ("Days Remaining", max((job.deadline - date.today()).days, 0) if job.deadline else "-"),
        ("Cooling Period", f"{cooling_period_days} days" if cooling_period_days else "-"),
        ("Sourced", sourced_count),
        ("Screened", screened_count),
        ("Lined Up", lined_up_count),
        ("Turned Up", turned_up_count),
        ("Offer Accepted", offer_accepted_count),
    ]

    # Job metadata for header section
    job_metadata = {
        "job_title": job.title,
        "job_id": job.job_id,
        "company_name": company_name,
        "created_at": job.created_at,
        "created_by": created_by_name,
        "status": job.status,
    }

    # Get ALL pipeline stages for this pipeline (even with 0 candidates)
    all_pipeline_stages = []
    if job.pipeline_id:
        all_pipeline_stages = (
            db.query(
                PipelineStage.id,
                PipelineStage.name,
                PipelineStage.color_code,
                PipelineStage.order
            )
            .filter(PipelineStage.pipeline_id == job.pipeline_id)
            .order_by(PipelineStage.order)
            .all()
        )
    
    # Get candidate counts per stage - use latest status only (not filtered by date)
    stage_counts_q = (
        db.query(
            PipelineStage.id,
            func.count(CandidatePipelineStatus.id).label('count')
        )
        .join(CandidatePipelineStatus, PipelineStage.id == CandidatePipelineStatus.pipeline_stage_id)
        .filter(CandidatePipelineStatus.latest == 1)
    )
    if candidate_job_ids:
        stage_counts_q = stage_counts_q.filter(CandidatePipelineStatus.candidate_job_id.in_(candidate_job_ids))
    if job.pipeline_id:
        stage_counts_q = stage_counts_q.filter(PipelineStage.pipeline_id == job.pipeline_id)
    stage_counts = dict(stage_counts_q.group_by(PipelineStage.id).all())
    
    # Calculate Joined and Rejected counts - FILTER BY DATE for daily report
    joined_count_funnel = (
        db.query(func.count(CandidateJobStatus.id))
        .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id == job_id,
            CandidateJobStatus.type == CandidateJobStatusType.joined,
            CandidateJobStatus.joined_at.isnot(None),
            CandidateJobStatus.joined_at >= date_start,
            CandidateJobStatus.joined_at < date_end
        )
        .scalar() or 0
    )
    
    rejected_count_funnel = (
        db.query(func.count(CandidateJobStatus.id))
        .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id == job_id,
            CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]),
            CandidateJobStatus.rejected_at.isnot(None),
            CandidateJobStatus.rejected_at >= date_start,
            CandidateJobStatus.rejected_at < date_end
        )
        .scalar() or 0
    )
    
    # Build stage_flow_rows with ALL stages (including zeros)
    stage_flow_rows = []
    for stage_id, name, color_code, order in all_pipeline_stages:
        count = stage_counts.get(stage_id, 0)
        
        # Normalize color_code
        normalized_color = "#2563eb"
        if color_code:
            color_code_str = str(color_code).strip()
            if color_code_str:
                if not color_code_str.startswith("#"):
                    color_code_str = "#" + color_code_str
                if len(color_code_str) == 7 and all(c in "0123456789ABCDEFabcdef" for c in color_code_str[1:]):
                    normalized_color = color_code_str
        
        stage_flow_rows.append({
            "stage_id": stage_id,
            "stage_name": name,
            "color_code": normalized_color,
            "candidates": count
        })
    
    stage_flow_rows.append({
        "stage_id": "joined",
        "stage_name": "Joined",
        "color_code": None,
        "candidates": joined_count_funnel,
    })
    stage_flow_rows.append({
        "stage_id": "rejected",
        "stage_name": "Rejected",
        "color_code": None,
        "candidates": rejected_count_funnel,
    })

    # Time spent per stage - FILTER BY DATE for daily report (in HOURS for daily report)
    stage_times_rows = []
    stage_durations: Dict[int, List[float]] = {}
    
    if candidate_job_ids:
        # Only get histories created on the specific day
        histories = (
            db.query(CandidatePipelineStatus)
            .filter(
                CandidatePipelineStatus.candidate_job_id.in_(candidate_job_ids),
                CandidatePipelineStatus.created_at >= date_start,
                CandidatePipelineStatus.created_at < date_end
            )
            .order_by(CandidatePipelineStatus.candidate_job_id, CandidatePipelineStatus.created_at)
            .all()
        )
        last_seen: Dict[int, CandidatePipelineStatus] = {}
        for row in histories:
            prev = last_seen.get(row.candidate_job_id)
            if prev:
                # Calculate in hours for daily report
                delta_hours = (row.created_at - prev.created_at).total_seconds() / 3600.0
                stage_durations.setdefault(row.pipeline_stage_id, []).append(delta_hours)
            last_seen[row.candidate_job_id] = row
    
    # Build stage_times_rows with ALL pipeline stages (including zeros)
    # For daily report, use avg_hours instead of avg_days
    for stage_id, name, color_code, order in all_pipeline_stages:
        values = stage_durations.get(stage_id, [])
        avg_hours = round(sum(values) / len(values), 2) if values else 0
        stage_times_rows.append({
            "stage_id": stage_id,
            "stage_name": name,
            "avg_days": avg_hours,  # Store hours in avg_days field for daily report (will be displayed as hours)
            "avg_hours": avg_hours,  # Add explicit hours field
            "order": order
        })
    
    # Calculate average time for Accepted (Joined) and Rejected - FILTER BY DATE
    accepted_times = []
    rejected_times = []
    
    if candidate_job_ids:
        # Get joined candidates on the specific day
        joined_cjs = (
            db.query(CandidateJobs.id, CandidateJobStatus.joined_at)
            .join(CandidateJobStatus, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(
                CandidateJobs.job_id == job_id,
                CandidateJobStatus.type == CandidateJobStatusType.joined,
                CandidateJobStatus.joined_at.isnot(None),
                CandidateJobStatus.joined_at >= date_start,
                CandidateJobStatus.joined_at < date_end
            )
            .all()
        )
        
        for cj_id, joined_at in joined_cjs:
            first_status = (
                db.query(CandidatePipelineStatus)
                .filter(CandidatePipelineStatus.candidate_job_id == cj_id)
                .order_by(CandidatePipelineStatus.created_at.asc())
                .first()
            )
            if first_status and joined_at:
                # Calculate in hours for daily report
                delta_hours = (joined_at - first_status.created_at).total_seconds() / 3600.0
                accepted_times.append(delta_hours)
        
        # Get rejected/dropped candidates on the specific day
        rejected_cjs = (
            db.query(CandidateJobs.id, CandidateJobStatus.rejected_at)
            .join(CandidateJobStatus, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(
                CandidateJobs.job_id == job_id,
                CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]),
                CandidateJobStatus.rejected_at.isnot(None),
                CandidateJobStatus.rejected_at >= date_start,
                CandidateJobStatus.rejected_at < date_end
            )
            .all()
        )
        
        for cj_id, rejected_at in rejected_cjs:
            first_status = (
                db.query(CandidatePipelineStatus)
                .filter(CandidatePipelineStatus.candidate_job_id == cj_id)
                .order_by(CandidatePipelineStatus.created_at.asc())
                .first()
            )
            if first_status and rejected_at:
                # Calculate in hours for daily report
                delta_hours = (rejected_at - first_status.created_at).total_seconds() / 3600.0
                rejected_times.append(delta_hours)
    
    # For daily report, store as hours (but keep field name as days for compatibility)
    avg_accepted_days = round(sum(accepted_times) / len(accepted_times), 2) if accepted_times else 0
    avg_rejected_days = round(sum(rejected_times) / len(rejected_times), 2) if rejected_times else 0
    
    # Sort stage_times by order
    stage_times_rows.sort(key=lambda x: x.get("order", 999))

    # Candidate details with stage - FILTER BY DATE (only show candidates with pipeline status on that day)
    candidate_rows: List[dict] = []
    if candidate_job_ids:
        # Get latest status for candidates that had pipeline status on the specific day
        # Use a subquery to get the latest status per candidate_job_id on that day
        subquery = (
            db.query(
                CandidatePipelineStatus.candidate_job_id,
                func.max(CandidatePipelineStatus.created_at).label('max_created_at')
            )
            .filter(
                CandidatePipelineStatus.candidate_job_id.in_(candidate_job_ids),
                CandidatePipelineStatus.created_at >= date_start,
                CandidatePipelineStatus.created_at < date_end
            )
            .group_by(CandidatePipelineStatus.candidate_job_id)
            .subquery()
        )
        
        latest_status = (
            db.query(CandidatePipelineStatus, Candidates)
            .join(CandidateJobs, CandidatePipelineStatus.candidate_job_id == CandidateJobs.id)
            .join(Candidates, Candidates.candidate_id == CandidateJobs.candidate_id)
            .join(
                subquery,
                and_(
                    CandidatePipelineStatus.candidate_job_id == subquery.c.candidate_job_id,
                    CandidatePipelineStatus.created_at == subquery.c.max_created_at
                )
            )
            .all()
        )
        
        for status_row, candidate in latest_status:
            stage_name = (
                db.query(PipelineStage.name).filter(PipelineStage.id == status_row.pipeline_stage_id).scalar()
                or status_row.pipeline_stage_id
            )
            candidate_rows.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "candidate_name": candidate.candidate_name,
                    "candidate_phone_number": candidate.candidate_phone_number,
                    "stage_name": stage_name,
                    "status": status_row.status,
                    "hr_name": user_map.get(candidate_assign_map.get(candidate.candidate_id)) if candidate_assign_map.get(candidate.candidate_id) else None,
                    "latest_remark": None,
                }
            )

    # HR activities aggregated + detailed + latest remark per candidate - FILTER BY DATE
    hr_rows = []
    hr_activity_details = []
    latest_remark_by_candidate: Dict[str, str] = {}
    if candidate_ids:
        # Only get activities on the specific day
        activity_rows = (
            db.query(CandidateActivity)
            .filter(
                CandidateActivity.candidate_id.in_(candidate_ids),
                CandidateActivity.created_at >= date_start,
                CandidateActivity.created_at < date_end
            )
            .order_by(CandidateActivity.created_at.desc())
            .all()
        )
        user_map_activity = {u.id: u for u in db.query(User).filter(User.id.in_({r.user_id for r in activity_rows})).all()}
        candidate_map_full = {c.candidate_id: c for c in db.query(Candidates).filter(Candidates.candidate_id.in_(candidate_ids)).all()}

        agg_counts: Dict[tuple, int] = {}
        for row in activity_rows:
            key = (row.user_id, row.type)
            agg_counts[key] = agg_counts.get(key, 0) + 1

            cand = candidate_map_full.get(row.candidate_id)
            cand_name = getattr(cand, "candidate_name", None)
            hr_activity_details.append(
                {
                    "hr_name": getattr(user_map_activity.get(row.user_id), "name", None) or f"User {row.user_id}",
                    "activity_type": row.type.value if isinstance(row.type, CandidateActivityType) else str(row.type),
                    "candidate_id": row.candidate_id,
                    "candidate_name": cand_name,
                    "remarks": row.remark,
                    "created_at": to_ist(row.created_at).isoformat() if row.created_at else None,
                }
            )
            if row.remark and row.candidate_id not in latest_remark_by_candidate:
                latest_remark_by_candidate[row.candidate_id] = row.remark

        for (user_id, act_type), count in agg_counts.items():
            hr_rows.append(
                {
                    "user_id": user_id,
                    "user_name": getattr(user_map_activity.get(user_id), "name", None) or f"User {user_id}",
                    "activity_type": act_type.value if isinstance(act_type, CandidateActivityType) else str(act_type),
                    "count": count,
                }
            )

        # fill latest remark into candidate_rows
        for row in candidate_rows:
            cid = row.get("candidate_id")
            if cid in latest_remark_by_candidate:
                row["latest_remark"] = latest_remark_by_candidate[cid]

    # Funnel metrics - create a filter for the date range
    daily_filters = ReportFilter(date_from=from_date, date_to=to_date)
    funnel = get_job_funnel(db, job_id, daily_filters)

    # Clawback metrics - filter by date
    from collections import defaultdict

    status_rows = []
    if candidate_job_ids:
        status_rows = (
            db.query(CandidateJobStatus)
            .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(
                CandidateJobs.job_id == job_id,
                CandidateJobStatus.created_at >= date_start,
                CandidateJobStatus.created_at < date_end
            )
            .all()
        )
    status_by_cj: Dict[int, List[CandidateJobStatus]] = defaultdict(list)
    for row in status_rows:
        status_by_cj[row.candidate_job_id].append(row)

    today = date.today()
    cp_days_int = None
    if job.cooling_period:
        try:
            cp_days_int = int(float(job.cooling_period))
        except Exception:
            cp_days_int = None

    clawback_cases = []
    clawback_completed_today: List[dict] = []
    clawback_drop_today: List[dict] = []

    for cj in candidate_jobs:
        st_list = status_by_cj.get(cj.id, [])
        joined_statuses = [s for s in st_list if s.type == CandidateJobStatusType.joined and s.joined_at]
        has_reject_drop = any(s.type in [CandidateJobStatusType.rejected, CandidateJobStatusType.dropped] for s in st_list)

        for s in st_list:
            if s.type in [CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]:
                s_date = (s.rejected_at or s.created_at or datetime.utcnow()).date()
                if from_date <= s_date <= to_date:
                    clawback_drop_today.append(
                        {
                            "candidate_id": cj.candidate_id,
                            "candidate_name": candidate_assign_map.get((cj.candidate_id, "name")),
                            "status": s.type.value if isinstance(s.type, CandidateJobStatusType) else str(s.type),
                            "date": s_date,
                        }
                    )

        if not joined_statuses:
            continue

        other_statuses = [s for s in st_list if s.type != CandidateJobStatusType.joined]
        if other_statuses:
            continue
        if has_reject_drop:
            continue

        joined_status = joined_statuses[0]
        completion_date = None
        if cp_days_int is not None and joined_status.joined_at:
            completion_date = (joined_status.joined_at + timedelta(days=cp_days_int)).date()

        recruiter_id = candidate_assign_map.get(cj.candidate_id)
        clawback_case = {
            "candidate_job_id": cj.id,
            "candidate_id": cj.candidate_id,
            "candidate_name": candidate_assign_map.get((cj.candidate_id, "name")),
            "recruiter_id": recruiter_id,
            "recruiter_name": user_map.get(recruiter_id, f"User {recruiter_id}") if recruiter_id else "N/A",
            "joined_on": joined_status.joined_at.date() if joined_status.joined_at else None,
            "completion_date": completion_date,
        }
        clawback_cases.append(clawback_case)
        if completion_date and from_date <= completion_date <= to_date:
            clawback_completed_today.append(clawback_case)

    total_clawback = len(clawback_cases)
    clawback_completed = len([c for c in clawback_cases if c.get("completion_date") and c["completion_date"] <= to_date])
    clawback_dropped_count = sum(
        1
        for st_list in status_by_cj.values()
        if any(s.type == CandidateJobStatusType.joined for s in st_list)
        and any(s.type in [CandidateJobStatusType.rejected, CandidateJobStatusType.dropped] for s in st_list)
    )
    clawback_pending = max(total_clawback - clawback_completed - clawback_dropped_count, 0)
    recovery_rate = round((clawback_completed / total_clawback) * 100, 2) if total_clawback else 0.0

    clawback_metrics = {
        "total_cases": total_clawback,
        "completed": clawback_completed,
        "dropped": clawback_dropped_count,
        "pending": clawback_pending,
        "recovery_rate": recovery_rate,
        "completed_today": clawback_completed_today,
        "drop_today": clawback_drop_today,
        "pending_vs_recovered": [
            {"label": "Recovered", "value": clawback_completed},
            {"label": "Pending", "value": clawback_pending},
            {"label": "Dropped", "value": clawback_dropped_count},
        ],
        "all_cases": clawback_cases,
    }

    # Recruiter Ranking table data - include ALL assigned recruiters
    # Get all assigned recruiters from user_jobs_assigned
    all_assigned_recruiters_daily = (
        db.query(UserJobsAssigned.user_id)
        .filter(UserJobsAssigned.job_id == job_id)
        .distinct()
        .all()
    )
    all_assigned_recruiter_ids_daily = {row[0] for row in all_assigned_recruiters_daily}
    
    # Calculate activity counts for each recruiter on the specific day (for ranking)
    activity_counts_daily: Dict[int, int] = {}
    if all_assigned_recruiter_ids_daily and candidate_job_ids:
        # Count CandidatePipelineStatus activities on that day
        pipeline_activity_daily = (
            db.query(CandidatePipelineStatus.created_by, func.count(CandidatePipelineStatus.id))
            .filter(
                CandidatePipelineStatus.candidate_job_id.in_(candidate_job_ids),
                CandidatePipelineStatus.created_by.in_(all_assigned_recruiter_ids_daily),
                CandidatePipelineStatus.created_by.isnot(None),
                CandidatePipelineStatus.created_at >= date_start,
                CandidatePipelineStatus.created_at < date_end
            )
            .group_by(CandidatePipelineStatus.created_by)
            .all()
        )
        for user_id, count in pipeline_activity_daily:
            activity_counts_daily[user_id] = activity_counts_daily.get(user_id, 0) + count
        
        # Count CandidateJobStatus activities on that day
        status_activity_daily = (
            db.query(CandidateJobStatus.created_by, func.count(CandidateJobStatus.id))
            .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(
                CandidateJobs.job_id == job_id,
                CandidateJobStatus.created_by.in_(all_assigned_recruiter_ids_daily),
                CandidateJobStatus.created_by.isnot(None),
                CandidateJobStatus.created_at >= date_start,
                CandidateJobStatus.created_at < date_end
            )
            .group_by(CandidateJobStatus.created_by)
            .all()
        )
        for user_id, count in status_activity_daily:
            activity_counts_daily[user_id] = activity_counts_daily.get(user_id, 0) + count
        
        # Count CandidateActivity activities on that day
        if candidate_ids:
            activity_activity_daily = (
                db.query(CandidateActivity.user_id, func.count(CandidateActivity.id))
                .filter(
                    CandidateActivity.candidate_id.in_(candidate_ids),
                    CandidateActivity.user_id.in_(all_assigned_recruiter_ids_daily),
                    CandidateActivity.user_id.isnot(None),
                    CandidateActivity.created_at >= date_start,
                    CandidateActivity.created_at < date_end
                )
                .group_by(CandidateActivity.user_id)
                .all()
            )
            for user_id, count in activity_activity_daily:
                activity_counts_daily[user_id] = activity_counts_daily.get(user_id, 0) + count
        
        # Count CandidateJobs created on that day
        jobs_activity_daily = (
            db.query(CandidateJobs.created_by, func.count(CandidateJobs.id))
            .filter(
                CandidateJobs.job_id == job_id,
                CandidateJobs.created_by.in_(all_assigned_recruiter_ids_daily),
                CandidateJobs.created_by.isnot(None),
                CandidateJobs.created_at >= date_start,
                CandidateJobs.created_at < date_end
            )
            .group_by(CandidateJobs.created_by)
            .all()
        )
        for user_id, count in jobs_activity_daily:
            activity_counts_daily[user_id] = activity_counts_daily.get(user_id, 0) + count
    
    # Build assignment stats for all assigned recruiters
    assignment_stats: Dict[int, dict] = {}
    for recruiter_id in all_assigned_recruiter_ids_daily:
        assignment_stats[recruiter_id] = {"candidates": 0, "joined": 0, "rejected": 0}
    
    # Populate stats from candidate_jobs (filtered by date for daily report)
    for cj in candidate_jobs:
        recruiter_id = candidate_assign_map.get(cj.candidate_id)
        if recruiter_id and recruiter_id in all_assigned_recruiter_ids_daily:
            stats = assignment_stats[recruiter_id]
            stats["candidates"] += 1
            st_list = status_by_cj.get(cj.id, [])
            if any(s.type == CandidateJobStatusType.joined for s in st_list):
                stats["joined"] += 1
            if any(s.type in [CandidateJobStatusType.rejected, CandidateJobStatusType.dropped] for s in st_list):
                stats["rejected"] += 1

    # Calculate active_user_ids before building recruiter ranking (for the specific day)
    active_user_ids = set()
    if all_assigned_recruiter_ids_daily:
        # From CandidatePipelineStatus - FILTER BY DATE
        if candidate_job_ids:
            active_from_pipeline = (
                db.query(CandidatePipelineStatus.created_by)
                .filter(
                    CandidatePipelineStatus.candidate_job_id.in_(candidate_job_ids),
                    CandidatePipelineStatus.created_by.in_(all_assigned_recruiter_ids_daily),
                    CandidatePipelineStatus.created_by.isnot(None),
                    CandidatePipelineStatus.created_at >= date_start,
                    CandidatePipelineStatus.created_at < date_end
                )
                .distinct()
                .all()
            )
            active_user_ids.update(row[0] for row in active_from_pipeline)
        
        # From CandidateJobStatus - FILTER BY DATE
        if candidate_job_ids:
            active_from_status = (
                db.query(CandidateJobStatus.created_by)
                .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
                .filter(
                    CandidateJobs.job_id == job_id,
                    CandidateJobStatus.created_by.in_(all_assigned_recruiter_ids_daily),
                    CandidateJobStatus.created_by.isnot(None),
                    CandidateJobStatus.created_at >= date_start,
                    CandidateJobStatus.created_at < date_end
                )
                .distinct()
                .all()
            )
            active_user_ids.update(row[0] for row in active_from_status)
        
        # From CandidateActivity - FILTER BY DATE
        if candidate_ids:
            active_from_activity = (
                db.query(CandidateActivity.user_id)
                .filter(
                    CandidateActivity.candidate_id.in_(candidate_ids),
                    CandidateActivity.user_id.in_(all_assigned_recruiter_ids_daily),
                    CandidateActivity.user_id.isnot(None),
                    CandidateActivity.created_at >= date_start,
                    CandidateActivity.created_at < date_end
                )
                .distinct()
                .all()
            )
            active_user_ids.update(row[0] for row in active_from_activity)
        
        # From CandidateJobs - FILTER BY DATE (if recruiter created a candidate on that day)
        active_from_jobs = (
            db.query(CandidateJobs.created_by)
            .filter(
                CandidateJobs.job_id == job_id,
                CandidateJobs.created_by.in_(all_assigned_recruiter_ids_daily),
                CandidateJobs.created_by.isnot(None),
                CandidateJobs.created_at >= date_start,
                CandidateJobs.created_at < date_end
            )
            .distinct()
            .all()
        )
        active_user_ids.update(row[0] for row in active_from_jobs)

    # Helper function to get count by tag for a specific recruiter on the specific day
    # Filter by user_id from candidate_activity (who created the activity)
    def get_count_by_tag_per_recruiter_daily(tag: PipelineStageStatusTag, recruiter_id: int) -> int:
        if not candidate_ids:
            return 0
        
        # Filter by user_id who created the activity (like tiles logic)
        # Use trimmed matching for remark/option to handle any whitespace issues
        count_query = (
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
            CandidateJobs.job_id == job_id,
                CandidateActivity.candidate_id.in_(candidate_ids),
                CandidateActivity.type == CandidateActivityType.status,
                CandidateActivity.user_id == recruiter_id,  # Filter by user_id who created the activity
                CandidateActivity.created_at >= date_start,
                CandidateActivity.created_at < date_end,
                cast(PipelineStageStatus.tag, String) == tag.value
            )
        )
        
        count = count_query.scalar()
        return count or 0
    
    # Helper function to get candidate details by tag for a specific recruiter on the specific day
    # Filter by user_id from candidate_activity (who created the activity)
    def get_candidates_by_tag_per_recruiter_daily(tag: PipelineStageStatusTag, recruiter_id: int) -> List[Dict]:
        if not candidate_ids:
            return []
        
        # Get candidate activities with this tag on the specific day, filtered by user_id who created the activity
        # Use case-insensitive and trimmed matching for remark/option to handle any whitespace or case issues
        activities = (
            db.query(
                CandidateActivity.candidate_id,
                func.max(CandidateActivity.created_at).label('created_at'),
                CandidateActivity.user_id
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
                CandidateJobs.job_id == job_id,
                CandidateActivity.candidate_id.in_(candidate_ids),
                CandidateActivity.type == CandidateActivityType.status,
                CandidateActivity.user_id == recruiter_id,  # Filter by user_id who created the activity
                CandidateActivity.created_at >= date_start,
                CandidateActivity.created_at < date_end,
                cast(PipelineStageStatus.tag, String) == tag.value
            )
            .group_by(CandidateActivity.candidate_id, CandidateActivity.user_id)
        .all()
    )
        
        candidate_details = []
        for cand_id, created_at, hr_user_id in activities:
            candidate_name = candidate_assign_map.get((cand_id, "name"), f"Candidate {cand_id}")
            hr_name = user_map.get(hr_user_id, f"User {hr_user_id}") if hr_user_id else "N/A"
            candidate_details.append({
                "candidate_id": cand_id,
                "candidate_name": candidate_name,
                "hr_name": hr_name,
                "created_at": to_ist(created_at).strftime("%d-%m-%Y %H:%M:%S") if created_at else "N/A"
            })
        return candidate_details
    
    # Calculate total candidates per recruiter (all time, not just for the day)
    # This is the total candidates assigned to each recruiter for this job
    total_candidates_per_recruiter = {}
    for cj in candidate_jobs:
        recruiter_id = candidate_assign_map.get(cj.candidate_id)
        if recruiter_id and recruiter_id in all_assigned_recruiter_ids_daily:
            total_candidates_per_recruiter[recruiter_id] = total_candidates_per_recruiter.get(recruiter_id, 0) + 1
    
    # Build recruiter ranking with all assigned recruiters
    recruiter_assignments = []
    tag_based_candidates_daily = {
        "sourced": [],
        "screened": [],
        "lined_up": [],
        "turned_up": [],
        "offer_accepted": []
    }
    
    for rid in all_assigned_recruiter_ids_daily:
        stats = assignment_stats.get(rid, {"candidates": 0, "joined": 0, "rejected": 0})
        user = db.query(User).filter(User.id == rid).first()
        recruiter_name = user.name if user else f"User {rid}"
        is_active = rid in active_user_ids
        
        # Total candidates for this recruiter (all time for this job)
        total_candidates = total_candidates_per_recruiter.get(rid, 0)
        
        # Calculate tag-based counts for this recruiter on the specific day
        sourced_count = get_count_by_tag_per_recruiter_daily(PipelineStageStatusTag.SOURCING, rid)
        screened_count = get_count_by_tag_per_recruiter_daily(PipelineStageStatusTag.SCREENING, rid)
        lined_up_count = get_count_by_tag_per_recruiter_daily(PipelineStageStatusTag.LINE_UPS, rid)
        turned_up_count = get_count_by_tag_per_recruiter_daily(PipelineStageStatusTag.TURN_UPS, rid)
        offer_accepted_count = get_count_by_tag_per_recruiter_daily(PipelineStageStatusTag.OFFER_ACCEPTED, rid)
        
        # Get candidate details for each tag
        sourced_candidates = get_candidates_by_tag_per_recruiter_daily(PipelineStageStatusTag.SOURCING, rid)
        screened_candidates = get_candidates_by_tag_per_recruiter_daily(PipelineStageStatusTag.SCREENING, rid)
        lined_up_candidates = get_candidates_by_tag_per_recruiter_daily(PipelineStageStatusTag.LINE_UPS, rid)
        turned_up_candidates = get_candidates_by_tag_per_recruiter_daily(PipelineStageStatusTag.TURN_UPS, rid)
        offer_accepted_candidates = get_candidates_by_tag_per_recruiter_daily(PipelineStageStatusTag.OFFER_ACCEPTED, rid)
        
        # Add to tag-based candidates lists
        tag_based_candidates_daily["sourced"].extend(sourced_candidates)
        tag_based_candidates_daily["screened"].extend(screened_candidates)
        tag_based_candidates_daily["lined_up"].extend(lined_up_candidates)
        tag_based_candidates_daily["turned_up"].extend(turned_up_candidates)
        tag_based_candidates_daily["offer_accepted"].extend(offer_accepted_candidates)
        
        # Calculate completed clawback count for this recruiter (for the date range)
        completed_clawback = 0
        if clawback_metrics and clawback_metrics.get("all_cases"):
            for case in clawback_metrics["all_cases"]:
                if case.get("recruiter_id") == rid and case.get("completion_date") and case["completion_date"] <= to_date:
                    completed_clawback += 1
        
        recruiter_assignments.append({
            "recruiter_id": rid,
            "recruiter_name": recruiter_name,
            "candidates": total_candidates,  # Total candidates for this recruiter in the job
            "joined": stats["joined"],
            "rejected": stats["rejected"],
            "active": is_active,
            "activity_count": activity_counts_daily.get(rid, 0),
            "sourced": sourced_count,
            "screened": screened_count,
            "lined_up": lined_up_count,
            "turned_up": turned_up_count,
            "offer_accepted": offer_accepted_count,
            "completed_clawback": completed_clawback,
        })
    
    # Rank by: 1) max(joined, completed_clawback), 2) highest activity, 3) highest candidates
    best_hr = sorted(
        recruiter_assignments,
        key=lambda x: (max(x.get("joined", 0), x.get("completed_clawback", 0)), x.get("activity_count", 0), x.get("candidates", 0)),
        reverse=True
    )

    # Determine graph type based on date range
    if date_range_days == 1:
        graph_type = "hourly"
    elif date_range_days <= 7:
        graph_type = "daily"
    elif date_range_days <= 31:
        graph_type = "daily"
    else:
        graph_type = "weekly"
    
    extras = {
        "clawback_metrics": clawback_metrics,
        "recruiter_assignments": recruiter_assignments,
        "tag_based_candidates_daily": tag_based_candidates_daily,  # Always include, works for date ranges too
        "graph_type": graph_type,
        "date_range_days": date_range_days,
        "is_daily": is_daily,
    }

    # Pipeline velocity - FILTER BY DATE (dynamically determine grouping: hourly/daily/weekly/monthly)
    # Fetch all records and group appropriately based on date range
    # Always ensure max 15 labels on X-axis by grouping intelligently
    velocity_q = (
        db.query(CandidatePipelineStatus.created_at)
        .join(CandidateJobs, CandidatePipelineStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id == job_id,
            CandidatePipelineStatus.created_at >= date_start,
            CandidatePipelineStatus.created_at < date_end
        )
        .all()
    )
    velocity_map = {}
    
    # Determine grouping based on date range, ensuring max 15 labels
    if date_range_days == 1:
        # Daily report: group by hour, but limit to max 15 labels
        for row in velocity_q:
            created_at = row.created_at if hasattr(row, 'created_at') else row[0]
            ist_datetime = to_ist(created_at)
            if ist_datetime:
                hour_key = f"{ist_datetime.strftime('%H:00')}"
                velocity_map[hour_key] = velocity_map.get(hour_key, 0) + 1
        # Generate hourly labels for the day (00:00 to 23:00)
        # Group by 2 hours if needed to keep under 15 labels
        velocity = []
        hour_interval = 2 if len(velocity_map) > 15 else 1
        for hour in range(0, 24, hour_interval):
            hour_label = f"{hour:02d}:00"
            # Sum up moves for this hour and next hour if grouping
            moves = 0
            for h in range(hour, min(hour + hour_interval, 24)):
                h_label = f"{h:02d}:00"
                moves += velocity_map.get(h_label, 0)
            velocity.append({"label": hour_label, "moves": moves})
    elif date_range_days <= 7:
        # Weekly report: group by day, format as DD-MM (no year)
        for row in velocity_q:
            created_at = row.created_at if hasattr(row, 'created_at') else row[0]
            ist_datetime = to_ist(created_at)
            if ist_datetime:
                day_key = ist_datetime.strftime('%d-%m')
                velocity_map[day_key] = velocity_map.get(day_key, 0) + 1
        # Generate daily labels, group if more than 15 days
        velocity = []
        current = from_date
        day_interval = 1
        total_days = date_range_days
        if total_days > 15:
            day_interval = (total_days + 14) // 15  # Round up to ensure <= 15 labels
        day_count = 0
        while current <= to_date:
            if day_count % day_interval == 0:
                day_label = current.strftime('%d-%m')
                # Sum moves for this day and following days in interval
                moves = 0
                temp_date = current
                for _ in range(day_interval):
                    if temp_date <= to_date:
                        temp_label = temp_date.strftime('%d-%m')
                        moves += velocity_map.get(temp_label, 0)
                        temp_date += timedelta(days=1)
                velocity.append({"label": day_label, "moves": moves})
            current += timedelta(days=1)
            day_count += 1
        # Ensure we don't exceed 15 labels
        if len(velocity) > 15:
            # Further group if needed
            grouped_velocity = []
            group_size = (len(velocity) + 14) // 15
            for i in range(0, len(velocity), group_size):
                group = velocity[i:i+group_size]
                label = group[0]["label"] if group else ""
                moves = sum(g["moves"] for g in group)
                grouped_velocity.append({"label": label, "moves": moves})
            velocity = grouped_velocity
    elif date_range_days <= 31:
        # Monthly report: group by day, format as DD-MM (no year)
        # Group days to ensure max 15 labels
        for row in velocity_q:
            created_at = row.created_at if hasattr(row, 'created_at') else row[0]
            ist_datetime = to_ist(created_at)
            if ist_datetime:
                day_key = ist_datetime.strftime('%d-%m')
                velocity_map[day_key] = velocity_map.get(day_key, 0) + 1
        # Generate daily labels, group if more than 15 days
        velocity = []
        current = from_date
        day_interval = 1
        total_days = date_range_days
        if total_days > 15:
            day_interval = (total_days + 14) // 15  # Round up to ensure <= 15 labels
        day_count = 0
        while current <= to_date:
            if day_count % day_interval == 0:
                day_label = current.strftime('%d-%m')
                # Sum moves for this day and following days in interval
                moves = 0
                temp_date = current
                for _ in range(day_interval):
                    if temp_date <= to_date:
                        temp_label = temp_date.strftime('%d-%m')
                        moves += velocity_map.get(temp_label, 0)
                        temp_date += timedelta(days=1)
                velocity.append({"label": day_label, "moves": moves})
            current += timedelta(days=1)
            day_count += 1
        # Ensure we don't exceed 15 labels
        if len(velocity) > 15:
            # Further group if needed
            grouped_velocity = []
            group_size = (len(velocity) + 14) // 15
            for i in range(0, len(velocity), group_size):
                group = velocity[i:i+group_size]
                label = group[0]["label"] if group else ""
                moves = sum(g["moves"] for g in group)
                grouped_velocity.append({"label": label, "moves": moves})
            velocity = grouped_velocity
    else:
        # Longer range: group by week, format as DD-MM (no year)
        for row in velocity_q:
            created_at = row.created_at if hasattr(row, 'created_at') else row[0]
            ist_datetime = to_ist(created_at)
            if ist_datetime:
                # Get week start (Monday)
                week_start = ist_datetime.date() - timedelta(days=ist_datetime.weekday())
                week_key = week_start.strftime('%d-%m')
                velocity_map[week_key] = velocity_map.get(week_key, 0) + 1
        # Generate weekly labels, group if more than 15 weeks
        velocity = []
        current = from_date
        # Start from Monday of the week containing from_date
        week_start = current - timedelta(days=current.weekday())
        week_count = 0
        week_interval = 1
        total_weeks = ((to_date - week_start).days // 7) + 1
        if total_weeks > 15:
            week_interval = (total_weeks + 14) // 15  # Round up to ensure <= 15 labels
        while week_start <= to_date:
            if week_count % week_interval == 0:
                week_label = week_start.strftime('%d-%m')
                # Sum moves for this week and following weeks in interval
                moves = 0
                temp_week = week_start
                for _ in range(week_interval):
                    if temp_week <= to_date:
                        temp_label = temp_week.strftime('%d-%m')
                        moves += velocity_map.get(temp_label, 0)
                        temp_week += timedelta(days=7)
                velocity.append({"label": week_label, "moves": moves})
            week_start += timedelta(days=7)
            week_count += 1
        # Ensure we don't exceed 15 labels
        if len(velocity) > 15:
            # Further group if needed
            grouped_velocity = []
            group_size = (len(velocity) + 14) // 15
            for i in range(0, len(velocity), group_size):
                group = velocity[i:i+group_size]
                label = group[0]["label"] if group else ""
                moves = sum(g["moves"] for g in group)
                grouped_velocity.append({"label": label, "moves": moves})
            velocity = grouped_velocity

    # Joined candidates datewise - FILTER BY DATE
    joined_datewise_q = (
        db.query(func.date(CandidateJobStatus.joined_at), func.count(CandidateJobStatus.id))
        .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id == job_id,
            CandidateJobStatus.type == CandidateJobStatusType.joined,
            CandidateJobStatus.joined_at.isnot(None),
            CandidateJobStatus.joined_at >= date_start,
            CandidateJobStatus.joined_at < date_end
        )
        .group_by(func.date(CandidateJobStatus.joined_at))
        .order_by(func.date(CandidateJobStatus.joined_at))
    )
    joined_datewise_rows = joined_datewise_q.all()
    joined_datewise = [{"label": str(to_ist(day).date()), "count": count} for day, count in joined_datewise_rows]

    # Rejected/Dropped datewise - FILTER BY DATE
    rejected_datewise_q = (
        db.query(func.date(CandidateJobStatus.rejected_at), func.count(CandidateJobStatus.id))
        .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id == job_id,
            CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]),
            CandidateJobStatus.rejected_at.isnot(None),
            CandidateJobStatus.rejected_at >= date_start,
            CandidateJobStatus.rejected_at < date_end
        )
        .group_by(func.date(CandidateJobStatus.rejected_at))
        .order_by(func.date(CandidateJobStatus.rejected_at))
    )
    rejected_datewise_rows = rejected_datewise_q.all()
    rejected_datewise = [{"label": str(to_ist(day).date()), "count": count} for day, count in rejected_datewise_rows]

    # Recruiter Metrics - simplified for daily report
    # Total Recruiters: count from user_jobs_assigned table
    total_recruiters = (
        db.query(func.count(func.distinct(UserJobsAssigned.user_id)))
        .filter(UserJobsAssigned.job_id == job_id)
        .scalar() or 0
    )
    
    # Active Recruiters: active_user_ids was already calculated above in the recruiter ranking section
    active_recruiters = len(active_user_ids)

    # Candidates Per Recruiter (include all assigned recruiters, even with 0 candidates)
    candidates_per_recruiter_q = (
        db.query(
            Candidates.assigned_to,
            func.count(CandidateJobs.id).label('candidate_count')
        )
        .join(CandidateJobs, Candidates.candidate_id == CandidateJobs.candidate_id)
        .filter(
            CandidateJobs.job_id == job_id,
            Candidates.assigned_to.isnot(None),
            Candidates.assigned_to.in_(all_assigned_recruiter_ids_daily)
        )
        .group_by(Candidates.assigned_to)
    )
    candidates_per_recruiter_rows = candidates_per_recruiter_q.all()
    candidates_per_recruiter_dict = {row[0]: row[1] for row in candidates_per_recruiter_rows}
    
    candidates_per_recruiter = []
    for recruiter_id in all_assigned_recruiter_ids_daily:
        user = db.query(User).filter(User.id == recruiter_id).first()
        recruiter_name = user.name if user else f"User {recruiter_id}"
        candidates_per_recruiter.append({
            "recruiter_name": recruiter_name,
            "candidate_count": candidates_per_recruiter_dict.get(recruiter_id, 0)
        })
    candidates_per_recruiter.sort(key=lambda x: x["candidate_count"], reverse=True)

    # Rejected or Dropped by Recruiter (include all assigned recruiters, even with 0 rejected)
    rejected_dropped_by_recruiter_q = (
        db.query(
            CandidateJobStatus.created_by,
            func.count(CandidateJobStatus.id).label('rejected_count')
        )
        .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id == job_id,
            CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]),
            CandidateJobStatus.created_by.in_(all_assigned_recruiter_ids_daily)
        )
        .group_by(CandidateJobStatus.created_by)
    )
    rejected_dropped_by_recruiter_rows = rejected_dropped_by_recruiter_q.all()
    rejected_dropped_by_recruiter_dict = {row[0]: row[1] for row in rejected_dropped_by_recruiter_rows}
    
    rejected_dropped_by_recruiter = []
    for recruiter_id in all_assigned_recruiter_ids_daily:
        user = db.query(User).filter(User.id == recruiter_id).first()
        recruiter_name = user.name if user else f"User {recruiter_id}"
        rejected_dropped_by_recruiter.append({
            "recruiter_name": recruiter_name,
            "rejected_count": rejected_dropped_by_recruiter_dict.get(recruiter_id, 0)
        })
    rejected_dropped_by_recruiter.sort(key=lambda x: x["rejected_count"], reverse=True)

    # Simplified recruiter metrics for daily report
    recruiter_metrics = {
        "total_recruiters": total_recruiters,
        "active_recruiters": active_recruiters,
        "inactive_recruiters": max(total_recruiters - active_recruiters, 0),
        "top_recruiter": {
            "name": "N/A",
            "closed_count": 0
        },
        "top_recruiters_ranking": [],
        "candidates_per_recruiter": candidates_per_recruiter,
        "rejected_dropped_by_recruiter": rejected_dropped_by_recruiter,
        "recruiter_assignments": recruiter_assignments,
        "total_clawback_cases": total_clawback,
    }

    return {
        "job_metadata": job_metadata,
        "summary_tiles": summary_tiles,
        "stage_flow": stage_flow_rows,
        "stage_times": stage_times_rows,
        "hr_activities": hr_rows,
        "candidate_rows": candidate_rows,
        "best_hr": best_hr,
        "funnel": funnel,
        "extras": {
            **extras,
            "pipeline_velocity": velocity,
            "joined_datewise": joined_datewise,
            "rejected_datewise": rejected_datewise,
            "recruiter_metrics": recruiter_metrics,
            "hr_activity_details": hr_activity_details,
        },
        "funnel_counts": {
            "joined": joined_count_funnel,
            "rejected": rejected_count_funnel,
        },
        "avg_times": {
            "accepted_days": avg_accepted_days,
            "rejected_days": avg_rejected_days,
        },
    }



def build_jobs_summary_report(db: Session, from_date: date, to_date: date) -> Dict[str, Mapping]:
    """
    Build a summary report for all jobs with tag-based statuses, company details, and daily breakdowns.
    Shows aggregated data across all jobs for the specified date range.
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

    # Get all jobs (not just active) to calculate status breakdowns
    all_jobs = db.query(JobOpenings).all()
    # Filter active jobs for the main report
    jobs = [j for j in all_jobs if j.status == "ACTIVE"]
    job_ids = [j.id for j in jobs]
    
    # Calculate job status counts (excluding PENDING)
    total_jobs_all = len([j for j in all_jobs if j.status and j.status.upper() != "PENDING"])
    total_active_jobs = len([j for j in all_jobs if j.status and j.status.upper() == "ACTIVE"])
    total_inactive_jobs = len([j for j in all_jobs if j.status and j.status.upper() == "INACTIVE"])
    total_closed_jobs = len([j for j in all_jobs if j.status and j.status.upper() == "CLOSED"])
    
    if not job_ids:
        return {
            "summary_tiles": [],
            "jobs_summary": [],
            "company_summary": [],
            "daily_breakdown": [],
            "charts": {},
            "date_range": {
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
                "is_daily": is_daily,
                "date_range_days": date_range_days
            }
        }

    # Get company details
    company_ids = list(set([j.company_id for j in jobs if j.company_id]))
    companies = {}
    if company_ids:
        company_rows = db.query(Company.id, Company.company_name, Company.location).filter(Company.id.in_(company_ids)).all()
        companies = {cid: {"name": cname, "location": cloc} for cid, cname, cloc in company_rows}

    # Get all candidate jobs for these jobs
    candidate_jobs = db.query(CandidateJobs).filter(CandidateJobs.job_id.in_(job_ids)).all()
    candidate_job_ids = [cj.id for cj in candidate_jobs]
    candidate_ids = [cj.candidate_id for cj in candidate_jobs]
    
    # Map candidate_id to job_id
    candidate_to_job = {cj.candidate_id: cj.job_id for cj in candidate_jobs}

    # Helper function to get tag count for a specific job
    def get_tag_count_for_job(job_id: int, tag: PipelineStageStatusTag) -> int:
        job_candidate_ids = [cid for cid, jid in candidate_to_job.items() if jid == job_id]
        if not job_candidate_ids:
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
                CandidateJobs.job_id == job_id,
                CandidateActivity.candidate_id.in_(job_candidate_ids),
                CandidateActivity.type == CandidateActivityType.status,
                CandidateActivity.created_at >= date_start,
                CandidateActivity.created_at < date_end,
                cast(PipelineStageStatus.tag, String) == tag.value
            )
            .scalar()
        )
        return count or 0

    # Get joined and rejected counts per job (for the date range)
    joined_counts = {}
    rejected_counts = {}
    if candidate_job_ids:
        joined_data = (
            db.query(CandidateJobs.job_id, func.count(CandidateJobStatus.id))
            .join(CandidateJobStatus, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(
                CandidateJobs.job_id.in_(job_ids),
                CandidateJobStatus.type == CandidateJobStatusType.joined,
                CandidateJobStatus.joined_at.isnot(None),
                CandidateJobStatus.joined_at >= date_start,
                CandidateJobStatus.joined_at < date_end
            )
            .group_by(CandidateJobs.job_id)
            .all()
        )
        joined_counts = {jid: count for jid, count in joined_data}
        
        rejected_data = (
            db.query(CandidateJobs.job_id, func.count(CandidateJobStatus.id))
            .join(CandidateJobStatus, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(
                CandidateJobs.job_id.in_(job_ids),
                CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]),
                CandidateJobStatus.rejected_at.isnot(None),
                CandidateJobStatus.rejected_at >= date_start,
                CandidateJobStatus.rejected_at < date_end
            )
            .group_by(CandidateJobs.job_id)
            .all()
        )
        rejected_counts = {jid: count for jid, count in rejected_data}

    # Build jobs summary (only active jobs)
    jobs_summary = []
    for job in jobs:
        company_info = companies.get(job.company_id, {"name": f"Company {job.company_id}", "location": ""})
        
        # Get tag counts for this job
        sourced = get_tag_count_for_job(job.id, PipelineStageStatusTag.SOURCING)
        screened = get_tag_count_for_job(job.id, PipelineStageStatusTag.SCREENING)
        lined_up = get_tag_count_for_job(job.id, PipelineStageStatusTag.LINE_UPS)
        turned_up = get_tag_count_for_job(job.id, PipelineStageStatusTag.TURN_UPS)
        offer_accepted = get_tag_count_for_job(job.id, PipelineStageStatusTag.OFFER_ACCEPTED)
        
        # Calculate total activity for this job (sum of all tag counts + joined + rejected)
        total_activity = sourced + screened + lined_up + turned_up + offer_accepted + joined_counts.get(job.id, 0) + rejected_counts.get(job.id, 0)
        
        jobs_summary.append({
            "job_id": job.id,
            "job_public_id": job.job_id,
            "job_title": job.title,
            "company_id": job.company_id,
            "company_name": company_info["name"],
            "company_location": company_info.get("location", ""),
            "openings": job.openings or 0,
            "deadline": job.deadline.strftime("%Y-%m-%d") if job.deadline else None,
            "days_remaining": max((job.deadline - date.today()).days, 0) if job.deadline else None,
            "status": job.status,
            "sourced": sourced,
            "screened": screened,
            "lined_up": lined_up,
            "turned_up": turned_up,
            "offer_accepted": offer_accepted,
            "joined": joined_counts.get(job.id, 0),
            "rejected": rejected_counts.get(job.id, 0),
            "total_activity": total_activity,  # For sorting
            "created_at": job.created_at.isoformat() if job.created_at else None,
        })
    
    # Sort jobs by most activity (total_activity descending)
    jobs_summary.sort(key=lambda x: x["total_activity"], reverse=True)

    # Build company summary (aggregate by company)
    company_summary_dict = {}
    for job_summary in jobs_summary:
        company_id = job_summary["company_id"]
        if company_id not in company_summary_dict:
            company_summary_dict[company_id] = {
                "company_id": company_id,
                "company_name": job_summary["company_name"],
                "company_location": job_summary["company_location"],
                "total_jobs": 0,
                "total_openings": 0,
                "total_sourced": 0,
                "total_screened": 0,
                "total_lined_up": 0,
                "total_turned_up": 0,
                "total_offer_accepted": 0,
                "total_joined": 0,
                "total_rejected": 0,
            }
        
        comp = company_summary_dict[company_id]
        comp["total_jobs"] += 1
        comp["total_openings"] += job_summary["openings"]
        comp["total_sourced"] += job_summary["sourced"]
        comp["total_screened"] += job_summary["screened"]
        comp["total_lined_up"] += job_summary["lined_up"]
        comp["total_turned_up"] += job_summary["turned_up"]
        comp["total_offer_accepted"] += job_summary["offer_accepted"]
        comp["total_joined"] += job_summary["joined"]
        comp["total_rejected"] += job_summary["rejected"]
    
    company_summary = list(company_summary_dict.values())
    # Sort by total activity (sum of all metrics)
    for comp in company_summary:
        comp["total_activity"] = (
            comp["total_sourced"] + comp["total_screened"] + comp["total_lined_up"] +
            comp["total_turned_up"] + comp["total_offer_accepted"] + comp["total_joined"] + comp["total_rejected"]
        )
    company_summary.sort(key=lambda x: x["total_activity"], reverse=True)

    # Build breakdown (hourly for 1 day, daily for <=30 days, weekly for >30 days, monthly for >365 days)
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
        # Hourly breakdown for single day
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
        # Daily/weekly/monthly breakdown
        current = from_date
        while current <= to_date:
            if group_type == "daily":
                key = current.isoformat()
            elif group_type == "weekly":
                # Get week start (Monday)
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
    
    # Get tag breakdowns based on group type
    for tag, tag_key in [
        (PipelineStageStatusTag.SOURCING, "sourced"),
        (PipelineStageStatusTag.SCREENING, "screened"),
        (PipelineStageStatusTag.LINE_UPS, "lined_up"),
        (PipelineStageStatusTag.TURN_UPS, "turned_up"),
        (PipelineStageStatusTag.OFFER_ACCEPTED, "offer_accepted"),
    ]:
        if group_type == "hourly":
            # Group by hour
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
                    CandidateJobs.job_id.in_(job_ids),
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
            # Group by date
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
                    CandidateJobs.job_id.in_(job_ids),
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
            # Group by week (Monday as week start) - MySQL compatible
            # DATE_SUB(date, INTERVAL WEEKDAY(date) DAY) gets Monday of the week
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
                    CandidateJobs.job_id.in_(job_ids),
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
            # Group by month - MySQL compatible
            # DATE_SUB(date, INTERVAL DAY(date)-1 DAY) gets first day of month
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
                    CandidateJobs.job_id.in_(job_ids),
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
    
    # Get joined/rejected breakdowns based on group type
    if group_type == "hourly":
        # Group by hour
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
                CandidateJobStatus.joined_at < date_end
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
                CandidateJobStatus.rejected_at < date_end
            )
            .group_by(func.extract('hour', CandidateJobStatus.rejected_at))
            .all()
        )
        for hour, count in rejected_data:
            hour_key = f"{int(hour):02d}:00"
            if hour_key in daily_breakdown_dict:
                daily_breakdown_dict[hour_key]["rejected"] = count
    elif group_type == "daily":
        # Group by date
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
                CandidateJobStatus.joined_at < date_end
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
                CandidateJobStatus.rejected_at < date_end
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
        # Group by week - MySQL compatible
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
                CandidateJobStatus.joined_at < date_end
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
                CandidateJobStatus.rejected_at < date_end
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
        # Group by month - MySQL compatible
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
                CandidateJobStatus.joined_at < date_end
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
                CandidateJobStatus.rejected_at < date_end
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
    # Total Jobs excludes PENDING (already calculated above)
    # Total Openings only from active jobs
    total_openings = sum(j["openings"] for j in jobs_summary)  # Only active jobs
    total_sourced = sum(j["sourced"] for j in jobs_summary)
    total_screened = sum(j["screened"] for j in jobs_summary)
    total_lined_up = sum(j["lined_up"] for j in jobs_summary)
    total_turned_up = sum(j["turned_up"] for j in jobs_summary)
    total_offer_accepted = sum(j["offer_accepted"] for j in jobs_summary)
    total_joined = sum(j["joined"] for j in jobs_summary)
    total_rejected = sum(j["rejected"] for j in jobs_summary)
    
    summary_tiles = [
        ("Total Jobs", total_jobs_all),  # Excludes PENDING
        ("Total Active Jobs", total_active_jobs),
        ("Total Inactive Jobs", total_inactive_jobs),
        ("Total Closed Jobs", total_closed_jobs),
        ("Total Openings", total_openings),  # Only active jobs
        ("Total Sourced", total_sourced),
        ("Total Screened", total_screened),
        ("Total Lined Up", total_lined_up),
        ("Total Turned Up", total_turned_up),
        ("Total Offer Accepted", total_offer_accepted),
        ("Total Joined", total_joined),
        ("Total Rejected", total_rejected),
    ]

    # Build charts
    # Chart 1: Tag status by job
    tag_by_job = [
        {
            "job_title": j["job_title"],
            "sourced": j["sourced"],
            "screened": j["screened"],
            "lined_up": j["lined_up"],
            "turned_up": j["turned_up"],
            "offer_accepted": j["offer_accepted"],
        }
        for j in jobs_summary[:20]  # Top 20 jobs
    ]
    
    # Chart 2: Daily tag trends with company breakdown
    # Build daily tag trends by company
    daily_tag_trends_by_company = []
    
    # Get company breakdown for each date in daily_breakdown
    for d in daily_breakdown:
        date_key = d["date"]
        
        # For each company, get tag counts for this date
        for company_id, company_info in companies.items():
            company_name = company_info["name"]
            
            # Get jobs for this company
            company_job_ids = [j.id for j in jobs if j.company_id == company_id]
            if not company_job_ids:
                continue
            
            # Get candidate_ids for this company's jobs
            company_candidate_ids = [cid for cid, jid in candidate_to_job.items() if jid in company_job_ids]
            if not company_candidate_ids:
                continue
            
            # Get tag counts for this company on this date
            company_sourced = 0
            company_screened = 0
            company_lined_up = 0
            company_turned_up = 0
            company_offer_accepted = 0
            
            # Determine date range for this specific date
            if group_type == "hourly":
                # For hourly, date_key is like "00:00", "01:00", etc.
                # We need to get the hour and filter by that hour on from_date
                try:
                    hour = int(date_key.split(":")[0])
                    date_start_hour = datetime.combine(from_date, datetime.min.time()) + timedelta(hours=hour)
                    date_end_hour = date_start_hour + timedelta(hours=1)
                except:
                    continue
            elif group_type == "daily":
                try:
                    date_obj = datetime.fromisoformat(date_key).date() if isinstance(date_key, str) else date_key
                    date_start_hour = datetime.combine(date_obj, datetime.min.time())
                    date_end_hour = date_start_hour + timedelta(days=1)
                except:
                    continue
            elif group_type == "weekly":
                try:
                    week_start_date = datetime.fromisoformat(date_key).date() if isinstance(date_key, str) else date_key
                    date_start_hour = datetime.combine(week_start_date, datetime.min.time())
                    date_end_hour = date_start_hour + timedelta(days=7)
                except:
                    continue
            else:  # monthly
                try:
                    month_start_date = datetime.fromisoformat(date_key).date() if isinstance(date_key, str) else date_key
                    if isinstance(month_start_date, str):
                        month_start_date = datetime.fromisoformat(month_start_date).date()
                    # Get first day of month
                    month_start = month_start_date.replace(day=1)
                    date_start_hour = datetime.combine(month_start, datetime.min.time())
                    # Get first day of next month
                    if month_start.month == 12:
                        next_month = month_start.replace(year=month_start.year + 1, month=1)
                    else:
                        next_month = month_start.replace(month=month_start.month + 1)
                    date_end_hour = datetime.combine(next_month, datetime.min.time())
                except:
                    continue
            
            # Get tag counts for this company and date range
            for tag, tag_key in [
                (PipelineStageStatusTag.SOURCING, "sourced"),
                (PipelineStageStatusTag.SCREENING, "screened"),
                (PipelineStageStatusTag.LINE_UPS, "lined_up"),
                (PipelineStageStatusTag.TURN_UPS, "turned_up"),
                (PipelineStageStatusTag.OFFER_ACCEPTED, "offer_accepted"),
            ]:
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
                        CandidateJobs.job_id.in_(company_job_ids),
                        CandidateActivity.candidate_id.in_(company_candidate_ids),
                        CandidateActivity.type == CandidateActivityType.status,
                        CandidateActivity.created_at >= date_start_hour,
                        CandidateActivity.created_at < date_end_hour,
                        cast(PipelineStageStatus.tag, String) == tag.value
                    )
                    .scalar() or 0
                )
                
                if tag_key == "sourced":
                    company_sourced = count
                elif tag_key == "screened":
                    company_screened = count
                elif tag_key == "lined_up":
                    company_lined_up = count
                elif tag_key == "turned_up":
                    company_turned_up = count
                elif tag_key == "offer_accepted":
                    company_offer_accepted = count
            
            # Only add if there's at least one non-zero value
            if company_sourced > 0 or company_screened > 0 or company_lined_up > 0 or company_turned_up > 0 or company_offer_accepted > 0:
                daily_tag_trends_by_company.append({
                    "date": date_key,
                    "company_name": company_name,
                    "sourced": company_sourced,
                    "screened": company_screened,
                    "lined_up": company_lined_up,
                    "turned_up": company_turned_up,
                    "offer_accepted": company_offer_accepted,
                })
    
    # Also keep the original aggregated version for charts (without company breakdown)
    daily_tag_trends = [
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
    
    # Chart 3: Company performance
    company_performance = [
        {
            "company_name": c["company_name"],
            "total_joined": c["total_joined"],
            "total_sourced": c["total_sourced"],
            "total_screened": c["total_screened"],
        }
        for c in company_summary[:15]  # Top 15 companies
    ]
    
    # Chart 4: Daily joined vs rejected
    daily_joined_rejected = [
        {
            "date": d["date"],
            "joined": d["joined"],
            "rejected": d["rejected"],
        }
        for d in daily_breakdown
    ]
    
    # Build HR Summary - Get all HRs who have activity in the date range
    # Get all unique user_ids from activities in the date range
    hr_activity_data = (
        db.query(
            CandidateActivity.user_id,
            func.count(func.distinct(CandidateActivity.candidate_id)).label('candidate_count'),
            func.count(CandidateActivity.id).label('activity_count')
        )
        .join(CandidateJobs, CandidateActivity.candidate_id == CandidateJobs.candidate_id)
        .filter(
            CandidateJobs.job_id.in_(job_ids),
            CandidateActivity.user_id.isnot(None),
            CandidateActivity.created_at >= date_start,
            CandidateActivity.created_at < date_end
        )
        .group_by(CandidateActivity.user_id)
        .all()
    )
    
    # Get joined/rejected counts per HR
    hr_joined_data = (
        db.query(
            CandidateJobStatus.created_by,
            func.count(CandidateJobStatus.id).label('joined_count')
        )
        .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id.in_(job_ids),
            CandidateJobStatus.type == CandidateJobStatusType.joined,
            CandidateJobStatus.joined_at.isnot(None),
            CandidateJobStatus.joined_at >= date_start,
            CandidateJobStatus.joined_at < date_end,
            CandidateJobStatus.created_by.isnot(None)
        )
        .group_by(CandidateJobStatus.created_by)
        .all()
    )
    hr_joined_map = {hr_id: count for hr_id, count in hr_joined_data}
    
    hr_rejected_data = (
        db.query(
            CandidateJobStatus.created_by,
            func.count(CandidateJobStatus.id).label('rejected_count')
        )
        .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id.in_(job_ids),
            CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]),
            CandidateJobStatus.rejected_at.isnot(None),
            CandidateJobStatus.rejected_at >= date_start,
            CandidateJobStatus.rejected_at < date_end,
            CandidateJobStatus.created_by.isnot(None)
        )
        .group_by(CandidateJobStatus.created_by)
        .all()
    )
    hr_rejected_map = {hr_id: count for hr_id, count in hr_rejected_data}
    
    # Build HR summary list
    hr_summary = []
    hr_user_ids = set()
    for user_id, candidate_count, activity_count in hr_activity_data:
        hr_user_ids.add(user_id)
        user = db.query(User).filter(User.id == user_id).first()
        hr_name = user.name if user else f"User {user_id}"
        
        total_activity = activity_count + hr_joined_map.get(user_id, 0) + hr_rejected_map.get(user_id, 0)
        
        hr_summary.append({
            "hr_id": user_id,
            "hr_name": hr_name,
            "candidate_count": candidate_count,
            "activity_count": activity_count,
            "joined": hr_joined_map.get(user_id, 0),
            "rejected": hr_rejected_map.get(user_id, 0),
            "total_activity": total_activity,
        })
    
    # Also include HRs from joined/rejected who might not have activities
    for hr_id in set(list(hr_joined_map.keys()) + list(hr_rejected_map.keys())):
        if hr_id not in hr_user_ids:
            user = db.query(User).filter(User.id == hr_id).first()
            hr_name = user.name if user else f"User {hr_id}"
            total_activity = hr_joined_map.get(hr_id, 0) + hr_rejected_map.get(hr_id, 0)
            hr_summary.append({
                "hr_id": hr_id,
                "hr_name": hr_name,
                "candidate_count": 0,
                "activity_count": 0,
                "joined": hr_joined_map.get(hr_id, 0),
                "rejected": hr_rejected_map.get(hr_id, 0),
                "total_activity": total_activity,
            })
    
    # Sort HRs by total activity (descending)
    hr_summary.sort(key=lambda x: x["total_activity"], reverse=True)

    return {
        "summary_tiles": summary_tiles,
        "jobs_summary": jobs_summary,
        "company_summary": company_summary,
        "hr_summary": hr_summary,
        "daily_breakdown": daily_breakdown,
        "charts": {
            "tag_by_job": tag_by_job,
            "daily_tag_trends": daily_tag_trends,
            "daily_tag_trends_by_company": daily_tag_trends_by_company,  # For Excel export with company breakdown
            "company_performance": company_performance,
            "daily_joined_rejected": daily_joined_rejected,
        },
        "date_range": {
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "is_daily": is_daily,
            "date_range_days": date_range_days,
            "group_type": group_type  # hourly, daily, weekly, monthly
        }
    }
