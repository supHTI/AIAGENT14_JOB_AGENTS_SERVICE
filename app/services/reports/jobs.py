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
    User,
)
from app.repositories import get_job_funnel, get_jobs_overview
from app.schemas.reports import FunnelMetrics, JobOverviewItem, JobOverviewResponse, JobOverviewSummary, ReportFilter

RISK_DAYS = 45


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
    Build an enriched jobs overview payload for export/email.
    Only date filters are honored for this view.
    """
    jobs_q = db.query(JobOpenings)
    if filters.date_from or filters.date_to:
        jobs_q = jobs_q.filter(*_date_clauses(JobOpenings.created_at, filters))
    jobs = jobs_q.all()
    job_ids = [j.id for j in jobs]
    company_ids = [j.company_id for j in jobs]
    company_rows = (
        db.query(Company.id, Company.company_name)
        .filter(Company.id.in_(company_ids) if company_ids else True)
        .all()
    )
    company_map = {cid: cname for cid, cname in company_rows}
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

    items: List[dict] = []
    for job in jobs:
        aging_days = (now - (job.created_at or now)).days
        status_str = str(job.status)
        items.append(
            {
                "job_id": job.id,
                "job_public_id": job.job_id,
                "title": job.title,
                "company_id": job.company_id,
                "company_name": company_map.get(job.company_id),
                "openings": job.openings or 0,
                "aging_days": aging_days,
                "created_at": job.created_at,
                "status": status_str,
                "candidate_count": candidate_counts.get(job.id, 0),
                "joined_count": joined_counts.get(job.id, 0),
            }
        )

    total_jobs = len(items)
    active_jobs = len([i for i in items if str(i["status"]).lower() in {"active", "open"}])
    closed_jobs = len([i for i in items if str(i["status"]).lower() in {"closed", "inactive", "archived"}])
    total_hired = sum(i["joined_count"] for i in items)
    total_openings = sum(i["openings"] for i in items)

    positions_at_risk = [i for i in items if i["aging_days"] > RISK_DAYS and str(i["status"]).lower() != "closed"]

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

    # Clawback eligible: joined without rejection/dropped
    joined_candidate_jobs = db.query(CandidateJobStatus.candidate_job_id).filter(
        CandidateJobStatus.type == CandidateJobStatusType.joined
    )
    rejected_or_dropped = db.query(CandidateJobStatus.candidate_job_id).filter(
        CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped])
    )
    eligible_cj_ids = [cid for (cid,) in joined_candidate_jobs.all() if (cid,) not in rejected_or_dropped.all()]
    clawback_q = db.query(CandidateJobs.job_id, func.count(CandidateJobs.id))
    if eligible_cj_ids:
        clawback_q = clawback_q.filter(CandidateJobs.id.in_(eligible_cj_ids))
    clawback_counts = clawback_q.group_by(CandidateJobs.job_id).all()
    clawback_per_job = [{"job_id": job_id, "cases": count} for job_id, count in clawback_counts]

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
    job = db.query(JobOpenings).filter(JobOpenings.id == job_id).first()
    if not job:
        raise ValueError("Job not found")

    candidate_jobs_q = db.query(CandidateJobs).filter(CandidateJobs.job_id == job_id)
    if filters.date_from or filters.date_to:
        candidate_jobs_q = candidate_jobs_q.filter(*_date_clauses(CandidateJobs.created_at, filters))
    candidate_jobs = candidate_jobs_q.all()
    candidate_job_ids = [cj.id for cj in candidate_jobs]
    candidate_ids = [cj.candidate_id for cj in candidate_jobs]

    active_candidates = len(candidate_jobs)
    distinct_hrs = (
        db.query(func.count(func.distinct(CandidateJobs.created_by)))
        .filter(CandidateJobs.job_id == job_id, CandidateJobs.created_by.isnot(None))
        .scalar()
    )

    pipeline_stage_count = (
        db.query(func.count(PipelineStage.id)).filter(PipelineStage.pipeline_id == job.pipeline_id).scalar() or 0
    )

    summary_tiles = [
        ("Job ID", job.job_id),
        ("Title", job.title),
        ("Company", getattr(job, "company_name", "") or job.company_id),
        ("Total openings", job.openings or 0),
        ("Cooling period", getattr(job, "cooling_period", None) or "-"),
        ("Deadline", job.deadline),
        ("Remaining days", max((job.deadline - date.today()).days, 0) if job.deadline else "-"),
        ("Status", job.status),
        ("Pipeline stages", pipeline_stage_count),
        ("Active candidates", active_candidates),
        ("HRs assigned", distinct_hrs or 0),
    ]

    # Stage flow: latest status per candidate job
    stage_flow_q = (
        db.query(PipelineStage.name, func.count(CandidatePipelineStatus.id))
        .join(CandidatePipelineStatus, PipelineStage.id == CandidatePipelineStatus.pipeline_stage_id)
        .filter(CandidatePipelineStatus.latest == 1)
    )
    if candidate_job_ids:
        stage_flow_q = stage_flow_q.filter(CandidatePipelineStatus.candidate_job_id.in_(candidate_job_ids))
    stage_flow = stage_flow_q.group_by(PipelineStage.name).all()
    stage_flow_rows = [{"stage_name": name, "candidates": count} for name, count in stage_flow]

    # Time spent per stage (avg hours)
    stage_times_rows = []
    if candidate_job_ids:
        histories = (
            db.query(CandidatePipelineStatus)
            .filter(CandidatePipelineStatus.candidate_job_id.in_(candidate_job_ids))
            .order_by(CandidatePipelineStatus.candidate_job_id, CandidatePipelineStatus.created_at)
            .all()
        )
        # compute per candidate durations
        durations: Dict[int, List[float]] = {}
        last_seen: Dict[int, CandidatePipelineStatus] = {}
        for row in histories:
            prev = last_seen.get(row.candidate_job_id)
            if prev:
                delta = (row.created_at - prev.created_at).total_seconds() / 3600.0
                durations.setdefault(row.pipeline_stage_id, []).append(delta)
            last_seen[row.candidate_job_id] = row
        for stage_id, values in durations.items():
            avg_hours = round(sum(values) / len(values), 2) if values else 0
            stage_name = (
                db.query(PipelineStage.name).filter(PipelineStage.id == stage_id).scalar()
            ) or f"Stage {stage_id}"
            stage_times_rows.append({"stage_id": stage_id, "stage_name": stage_name, "avg_hours": avg_hours})

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
                }
            )

    # HR activities
    hr_rows = []
    if candidate_ids:
        activity_rows = (
            db.query(CandidateActivity.user_id, CandidateActivity.type, func.count(CandidateActivity.id))
            .filter(CandidateActivity.candidate_id.in_(candidate_ids))
            .group_by(CandidateActivity.user_id, CandidateActivity.type)
            .all()
        )
        user_map = {u.id: u for u in db.query(User).filter(User.id.in_([r[0] for r in activity_rows])).all()}
        for user_id, act_type, count in activity_rows:
            hr_rows.append(
                {
                    "user_id": user_id,
                    "user_name": getattr(user_map.get(user_id), "name", None) or f"User {user_id}",
                    "activity_type": act_type.value if isinstance(act_type, CandidateActivityType) else str(act_type),
                    "count": count,
                }
            )

    best_hr = sorted(hr_rows, key=lambda x: x["count"], reverse=True)[:3]

    # Funnel metrics (reuse existing)
    funnel = get_job_funnel(db, job_id, filters)

    # Clawback + dropouts
    joined_ids_q = db.query(CandidateJobStatus.candidate_job_id).filter(
        CandidateJobStatus.type == CandidateJobStatusType.joined,
    )
    if candidate_job_ids:
        joined_ids_q = joined_ids_q.filter(CandidateJobStatus.candidate_job_id.in_(candidate_job_ids))
    joined_ids = joined_ids_q.all()

    rejected_or_dropped_q = db.query(CandidateJobStatus.candidate_job_id).filter(
        CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped])
    )
    rejected_or_dropped = rejected_or_dropped_q.all()
    eligible_clawback = [cid for (cid,) in joined_ids if (cid,) not in rejected_or_dropped]
    total_clawback = len(eligible_clawback)

    drop_q = db.query(CandidateJobStatus.type, func.count(CandidateJobStatus.id)).filter(
        CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]),
    )
    if candidate_job_ids:
        drop_q = drop_q.filter(CandidateJobStatus.candidate_job_id.in_(candidate_job_ids))
    drop_rows = drop_q.group_by(CandidateJobStatus.type).all()
    reject_drop_summary = {str(t.value): count for t, count in drop_rows}

    extras = {
        "clawback_eligible": total_clawback,
        "rejected": reject_drop_summary.get("rejected", 0),
        "dropped": reject_drop_summary.get("dropped", 0),
    }

    # Pipeline velocity (movement per day)
    velocity_q = db.query(func.date(CandidatePipelineStatus.created_at), func.count(CandidatePipelineStatus.id))
    if candidate_job_ids:
        velocity_q = velocity_q.filter(CandidatePipelineStatus.candidate_job_id.in_(candidate_job_ids))
    velocity_rows = velocity_q.group_by(func.date(CandidatePipelineStatus.created_at)).all()
    velocity = [{"label": str(day), "moves": count} for day, count in velocity_rows]

    return {
        "summary_tiles": summary_tiles,
        "stage_flow": stage_flow_rows,
        "stage_times": stage_times_rows,
        "hr_activities": hr_rows,
        "candidate_rows": candidate_rows,
        "best_hr": best_hr,
        "funnel": funnel,
        "extras": {**extras, "pipeline_velocity": velocity},
    }

