"""
Job-related report services with richer analytics payloads.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, List, Mapping

from sqlalchemy import func
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
    CompanySpoc,
    User,
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

    # Recruiter assignment table data
    assignment_stats: Dict[int, dict] = {}
    for cj in candidate_jobs:
        recruiter_id = candidate_assign_map.get(cj.candidate_id)
        if not recruiter_id:
            continue
        stats = assignment_stats.setdefault(recruiter_id, {"assigned": 0, "joined": 0, "rejected": 0})
        stats["assigned"] += 1
        st_list = status_by_cj.get(cj.id, [])
        if any(s.type == CandidateJobStatusType.joined for s in st_list):
            stats["joined"] += 1
        if any(s.type in [CandidateJobStatusType.rejected, CandidateJobStatusType.dropped] for s in st_list):
            stats["rejected"] += 1

    recruiter_assignments = [
        {
            "recruiter_id": rid,
            "recruiter_name": user_map.get(rid, f"User {rid}"),
            **stats,
        }
        for rid, stats in assignment_stats.items()
    ]

    # Best HR ranking: use recruiter assignments (assigned/closed) sorted descending by assigned then joined
    best_hr = sorted(recruiter_assignments, key=lambda x: (x.get("assigned", 0), x.get("joined", 0)), reverse=True)

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
    # 1. Total Recruiters (users who have created any candidate_job for this job)
    total_recruiters_q = (
        db.query(func.count(func.distinct(CandidateJobs.created_by)))
        .filter(
            CandidateJobs.job_id == job_id,
            CandidateJobs.created_by.isnot(None)
        )
    )
    total_recruiters = total_recruiters_q.scalar() or 0

    # 2. Active Recruiters (users with recent activity in last 30 days)
    # Check: CandidateJobs, CandidatePipelineStatus, CandidateJobStatus, CandidateActivity
    now = datetime.utcnow()
    recent_date = now - timedelta(days=30)
    
    active_user_ids = set()
    
    # From CandidateJobs
    active_from_jobs = (
        db.query(CandidateJobs.created_by)
        .filter(
            CandidateJobs.job_id == job_id,
            CandidateJobs.created_by.isnot(None),
            CandidateJobs.created_at >= recent_date
        )
        .distinct()
        .all()
    )
    active_user_ids.update(row[0] for row in active_from_jobs)
    
    # From CandidatePipelineStatus (for this job's candidate_jobs)
    if candidate_job_ids:
        active_from_pipeline = (
            db.query(CandidatePipelineStatus.created_by)
            .filter(
                CandidatePipelineStatus.candidate_job_id.in_(candidate_job_ids),
                CandidatePipelineStatus.created_by.isnot(None),
                CandidatePipelineStatus.created_at >= recent_date
            )
            .distinct()
            .all()
        )
        active_user_ids.update(row[0] for row in active_from_pipeline)
    
    # From CandidateJobStatus (for this job's candidate_jobs)
    if candidate_job_ids:
        active_from_status = (
            db.query(CandidateJobStatus.created_by)
            .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(
                CandidateJobs.job_id == job_id,
                CandidateJobStatus.created_by.isnot(None),
                CandidateJobStatus.created_at >= recent_date
            )
            .distinct()
            .all()
        )
        active_user_ids.update(row[0] for row in active_from_status)
    
    # From CandidateActivity (for candidates in this job)
    if candidate_ids:
        active_from_activity = (
            db.query(CandidateActivity.user_id)
            .filter(
                CandidateActivity.candidate_id.in_(candidate_ids),
                CandidateActivity.user_id.isnot(None),
                CandidateActivity.created_at >= recent_date
            )
            .distinct()
            .all()
        )
        active_user_ids.update(row[0] for row in active_from_activity)
    
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

    # 5. Candidates Per Recruiter (candidates assigned to recruiter for this job)
    candidates_per_recruiter_q = (
        db.query(
            Candidates.assigned_to,
            func.count(CandidateJobs.id).label('candidate_count')
        )
        .join(CandidateJobs, Candidates.candidate_id == CandidateJobs.candidate_id)
        .filter(
            CandidateJobs.job_id == job_id,
            Candidates.assigned_to.isnot(None)
        )
        .group_by(Candidates.assigned_to)
    )
    candidates_per_recruiter_rows = candidates_per_recruiter_q.all()
    candidates_per_recruiter = []
    for user_id, count in candidates_per_recruiter_rows:
        user = db.query(User).filter(User.id == user_id).first()
        recruiter_name = user.name if user else f"User {user_id}"
        candidates_per_recruiter.append({
            "recruiter_name": recruiter_name,
            "candidate_count": count
        })
    candidates_per_recruiter.sort(key=lambda x: x["candidate_count"], reverse=True)

    # 6. Rejected or Dropped by Recruiter
    rejected_dropped_by_recruiter_q = (
        db.query(
            CandidateJobStatus.created_by,
            func.count(CandidateJobStatus.id).label('rejected_count')
        )
        .join(CandidateJobs, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
        .filter(
            CandidateJobs.job_id == job_id,
            CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped])
        )
        .group_by(CandidateJobStatus.created_by)
    )
    rejected_dropped_by_recruiter_rows = rejected_dropped_by_recruiter_q.all()
    rejected_dropped_by_recruiter = []
    for user_id, count in rejected_dropped_by_recruiter_rows:
        user = db.query(User).filter(User.id == user_id).first()
        recruiter_name = user.name if user else f"User {user_id}"
        rejected_dropped_by_recruiter.append({
            "recruiter_name": recruiter_name,
            "rejected_count": count
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

