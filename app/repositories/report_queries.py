"""
Reusable query helpers for report endpoints.
These functions keep raw SQLAlchemy logic in one place so services stay thin.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Iterable, List, Tuple

from sqlalchemy import and_, func, select, case
from sqlalchemy.orm import Session

from app.database_layer.db_model import (
    CandidateActivity,
    CandidateActivityType,
    CandidateJobStatus,
    CandidateJobStatusType,
    CandidateJobs,
    CandidatePipelineStatus,
    JobOpenings,
    PipelineStage,
    Session as LoginSession,
    User,
)
from app.schemas.reports import ReportFilter


def _date_range_clause(model_date_col, filters: ReportFilter):
    clauses = []
    if filters.date_from:
        clauses.append(model_date_col >= filters.date_from)
    if filters.date_to:
        clauses.append(model_date_col <= filters.date_to + timedelta(days=1))
    return clauses


def apply_job_filters(query, filters: ReportFilter):
    if filters.job_ids:
        query = query.filter(JobOpenings.id.in_(filters.job_ids))
    if filters.job_public_ids:
        query = query.filter(JobOpenings.job_id.in_(filters.job_public_ids))
    if filters.company_ids:
        query = query.filter(JobOpenings.company_id.in_(filters.company_ids))
    if filters.pipeline_ids:
        query = query.filter(JobOpenings.pipeline_id.in_(filters.pipeline_ids))
    if filters.status:
        query = query.filter(JobOpenings.status == filters.status)
    if filters.location:
        query = query.filter(JobOpenings.location == filters.location)
    if filters.remote is not None:
        query = query.filter(JobOpenings.remote == int(filters.remote))
    if filters.work_mode:
        query = query.filter(JobOpenings.work_mode == filters.work_mode)
    if filters.date_from or filters.date_to:
        query = query.filter(*_date_range_clause(JobOpenings.created_at, filters))
    return query


def get_jobs_overview(db: Session, filters: ReportFilter):
    jobs_q = apply_job_filters(db.query(JobOpenings), filters)
    jobs = jobs_q.all()
    now = datetime.utcnow()

    items = []
    total_open_positions = 0
    for job in jobs:
        aging_days = (now - (job.created_at or now)).days
        total_open_positions += job.openings or 0
        items.append(
            {
                "job_id": job.id,
                "job_public_id": job.job_id,
                "title": job.title,
                "openings": job.openings or 0,
                "aging_days": aging_days,
                "created_at": job.created_at,
                "status": job.status,
            }
        )

    avg_aging = sum([i["aging_days"] for i in items]) / len(items) if items else 0
    new_jobs = (
        jobs_q.filter(
            and_(
                JobOpenings.created_at >= now - timedelta(days=30),
                JobOpenings.created_at <= now,
            )
        ).count()
    )

    summary = {
        "total_open_positions": total_open_positions,
        "total_jobs": len(items),
        "avg_aging_days": round(avg_aging, 2),
        "new_jobs": new_jobs,
    }
    return summary, items


def get_job_funnel(db: Session, job_id: int, filters: ReportFilter):
    base_cj = db.query(CandidateJobs).filter(CandidateJobs.job_id == job_id)
    if filters.date_from or filters.date_to:
        base_cj = base_cj.filter(*_date_range_clause(CandidateJobs.created_at, filters))
    candidate_job_ids = [cj.id for cj in base_cj.all()]
    if not candidate_job_ids:
        return {"sourced": 0, "screened": 0, "offers": 0, "joins": 0}

    sourced = (
        db.query(func.count(CandidateActivity.id))
        .filter(
            CandidateActivity.candidate_id.in_(
                db.query(CandidateJobs.candidate_id).filter(CandidateJobs.id.in_(candidate_job_ids))
            ),
            CandidateActivity.type.in_(
                [CandidateActivityType.pipeline, CandidateActivityType.general]
            ),
        )
        .scalar()
    )
    screened = (
        db.query(func.count(CandidateActivity.id))
        .filter(
            CandidateActivity.candidate_id.in_(
                db.query(CandidateJobs.candidate_id).filter(CandidateJobs.id.in_(candidate_job_ids))
            ),
            CandidateActivity.type == CandidateActivityType.pipeline,
        )
        .scalar()
    )
    offers = (
        db.query(func.count(CandidateJobStatus.id))
        .filter(
            CandidateJobStatus.candidate_job_id.in_(candidate_job_ids),
            CandidateJobStatus.type == CandidateJobStatusType.joined,
        )
        .scalar()
    )
    joins = offers  # no explicit accepted status; treat joined as offer+join
    ratio = round((joins / offers) if offers else 0, 2)
    return {"sourced": sourced, "screened": screened, "offers": offers, "joins": joins, "join_ratio": ratio}


def get_recruiter_performance(db: Session, filters: ReportFilter):
    base_activity = db.query(
        CandidateActivity.user_id,
        func.count(CandidateActivity.id).label("activity_count"),
        func.sum(case((CandidateActivity.type == CandidateActivityType.general, 1), else_=0)).label("sourced"),
        func.sum(case((CandidateActivity.type == CandidateActivityType.pipeline, 1), else_=0)).label("pipeline"),
    )
    if filters.recruiter_ids:
        base_activity = base_activity.filter(CandidateActivity.user_id.in_(filters.recruiter_ids))
    if filters.date_from or filters.date_to:
        base_activity = base_activity.filter(*_date_range_clause(CandidateActivity.created_at, filters))
    base_activity = base_activity.group_by(CandidateActivity.user_id)
    activity_rows = base_activity.all()

    user_ids = [row.user_id for row in activity_rows]
    login_rows = (
        db.query(
            LoginSession.user_id,
            func.count(LoginSession.id).label("login_count"),
            func.max(LoginSession.login_at).label("last_login_at"),
        )
        .filter(LoginSession.user_id.in_(user_ids))
        .group_by(LoginSession.user_id)
        .all()
    )
    login_map = {r.user_id: r for r in login_rows}
    user_rows = db.query(User).filter(User.id.in_(user_ids)).all()
    user_map = {u.id: u for u in user_rows}

    items = []
    for row in activity_rows:
        offers = 0
        joins = 0
        ratio = 0
        login_count = getattr(login_map.get(row.user_id), "login_count", 0) or 0
        last_login_at = getattr(login_map.get(row.user_id), "last_login_at", None)
        items.append(
            {
                "user_id": row.user_id,
                "name": getattr(user_map.get(row.user_id), "name", None),
                "sourced": row.sourced or 0,
                "screened": row.pipeline or 0,
                "moves": row.activity_count or 0,
                "offers": offers,
                "joins": joins,
                "join_ratio": ratio,
                "login_count": login_count,
                "last_login_at": last_login_at,
            }
        )
    return items


def _compute_stage_durations(rows: Iterable[CandidatePipelineStatus]) -> List[Tuple[int, float]]:
    durations = []
    for row in rows:
        durations.append((row.pipeline_stage_id, row.created_at))
    durations.sort(key=lambda x: x[1])
    deltas = []
    for idx in range(1, len(durations)):
        prev = durations[idx - 1]
        curr = durations[idx]
        hours = (curr[1] - prev[1]).total_seconds() / 3600.0
        deltas.append((curr[0], hours))
    return deltas


def get_pipeline_velocity(db: Session, filters: ReportFilter):
    query = db.query(CandidatePipelineStatus).filter(CandidatePipelineStatus.latest == 1)
    if filters.pipeline_stage_ids:
        query = query.filter(CandidatePipelineStatus.pipeline_stage_id.in_(filters.pipeline_stage_ids))
    if filters.date_from or filters.date_to:
        query = query.filter(*_date_range_clause(CandidatePipelineStatus.created_at, filters))
    rows = query.all()

    stage_buckets: dict[int, List[float]] = {}
    for cps in rows:
        # Fetch all statuses for the candidate_job to compute deltas
        history = (
            db.query(CandidatePipelineStatus)
            .filter(CandidatePipelineStatus.candidate_job_id == cps.candidate_job_id)
            .order_by(CandidatePipelineStatus.created_at)
            .all()
        )
        for stage_id, hours in _compute_stage_durations(history):
            stage_buckets.setdefault(stage_id, []).append(hours)

    results = []
    if not stage_buckets:
        return results
    stages = db.query(PipelineStage).filter(PipelineStage.id.in_(stage_buckets.keys())).all()
    stage_map = {s.id: s for s in stages}
    for stage_id, values in stage_buckets.items():
        values_sorted = sorted(values)
        p50 = median(values_sorted)
        p90 = values_sorted[int(0.9 * len(values_sorted))] if values_sorted else 0
        avg = sum(values_sorted) / len(values_sorted)
        results.append(
            {
                "pipeline_stage_id": stage_id,
                "stage_name": getattr(stage_map.get(stage_id), "name", None),
                "avg_hours": round(avg, 2),
                "p50_hours": round(p50, 2),
                "p90_hours": round(p90, 2),
                "job_id": None,
            }
        )
    return results


def get_pipeline_dropout(db: Session, filters: ReportFilter):
    query = db.query(CandidatePipelineStatus)
    if filters.pipeline_stage_ids:
        query = query.filter(CandidatePipelineStatus.pipeline_stage_id.in_(filters.pipeline_stage_ids))
    rows = query.all()
    stage_stats: dict[int, dict] = {}
    for row in rows:
        bucket = stage_stats.setdefault(row.pipeline_stage_id, {"entrants": 0, "exits": 0})
        bucket["entrants"] += 1
        if row.status and row.status.lower() in {"rejected", "dropped"}:
            bucket["exits"] += 1
    # Add drops from candidate_job_status as exits
    cjs = (
        db.query(CandidateJobStatus)
        .filter(CandidateJobStatus.type.in_([CandidateJobStatusType.rejected, CandidateJobStatusType.dropped]))
        .all()
    )
    for status_row in cjs:
        # no stage mapping; attribute to latest stage if available
        latest = (
            db.query(CandidatePipelineStatus)
            .filter(CandidatePipelineStatus.candidate_job_id == status_row.candidate_job_id)
            .order_by(CandidatePipelineStatus.created_at.desc())
            .first()
        )
        stage_id = latest.pipeline_stage_id if latest else None
        if stage_id:
            bucket = stage_stats.setdefault(stage_id, {"entrants": 0, "exits": 0})
            bucket["exits"] += 1
    results = []
    stage_ids = list(stage_stats.keys())
    stages = db.query(PipelineStage).filter(PipelineStage.id.in_(stage_ids)).all()
    stage_map = {s.id: s for s in stages}
    for stage_id, stat in stage_stats.items():
        entrants = stat["entrants"]
        exits = stat["exits"]
        dropout_pct = round((exits / entrants) * 100, 2) if entrants else 0
        results.append(
            {
                "pipeline_stage_id": stage_id,
                "stage_name": getattr(stage_map.get(stage_id), "name", None),
                "entrants": entrants,
                "exits": exits,
                "dropout_pct": dropout_pct,
            }
        )
    return results

