# Reports API Architecture (FastAPI + SQLAlchemy)

## Goals
- Provide report-ready APIs over existing SQLAlchemy models in `app/database_layer/db_model.py`.
- Accept date ranges, IDs, and filter params (job, recruiter/HR, pipeline stage + status).
- Produce JSON plus downloadable CSV/XLSX/PDF; email the same.
- Keep implementation small: thin routers → service layer → query helpers.

## High-Level Design
- **Routers** under `app/api/reports`: one module per report domain (jobs, recruiters, pipeline, clawback, exports).
- **Schemas** in `app/schemas/reports.py`: request filters + response DTOs.
- **Services** in `app/services/reports/*`: pure functions that build SQLAlchemy queries using existing models.
- **Repositories/queries** in `app/repositories/report_queries.py`: reusable query fragments (filters, aggregations).
- **Exports** in `app/services/exporters.py`: CSV (Python `csv`), XLSX (`openpyxl`), PDF (WeasyPrint/ReportLab). Graphs via `matplotlib` → embed as PNG in PDF.
- **Email** in `app/services/emailer.py`: SMTP settings from config, send attachments.
- **Background jobs**: use FastAPI `BackgroundTasks` initially; optional Celery/RQ for heavier PDFs.
- **Configuration**: add `REPORT_DEFAULT_TZ`, `REPORT_EMAIL_FROM`, SMTP creds, default date ranges.

## Data Filters (apply to all endpoints)
- `date_from`, `date_to` (defaults: today or last 30 days).
- `job_ids`, `job_public_ids` (maps to `JobOpenings.id` or `job_id`).
- `company_ids`, `pipeline_ids`, `pipeline_stage_ids`.
- `pipeline_stage_status` (from `PipelineStageStatus.option`).
- `recruiter_ids`/`hr_ids` (maps to `User.id`).
- `status` (job status), `location`, `remote`, `work_mode`.

## Endpoints (proposed)
- `GET /reports/jobs/overview`
  - Metrics: total open positions, new jobs created (by day/week/month), aging per job (days open = now - created_at).
  - Filters: date range on `created_at`, `status`, `company_id`, `pipeline_id`.
- `GET /reports/jobs/{job_id}/funnel`
  - Metrics per job: candidates sourced/screened, offers, joining success ratio.
  - Uses `CandidateJobs`, `CandidateActivity` (type `pipeline`, `status`, `accepted`), `CandidateJobStatus`.
- `GET /reports/recruiters/performance`
  - Candidates sourced per recruiter; screened per recruiter; pipeline moves per recruiter.
  - Filters: recruiter ids, date range on `CandidateActivity.created_at`.
- `GET /reports/pipeline/velocity`
  - Avg time between pipeline stages per job or per pipeline.
  - Uses `CandidatePipelineStatus` ordered by `created_at`.
- `GET /reports/pipeline/dropout`
  - Dropout % per stage: count of candidates leaving/marked `rejected/dropped` at that stage ÷ entrants.
- `GET /reports/clawbacks/overview`
  - Total clawback cases, recovery rate. (Requires/assumes table; if absent, stub with TODO.)
- `POST /reports/exports`
  - Body: { `report_type`: `daily|monthly|hr|job|top_hr`, `format`: `csv|xlsx|pdf`, filters… }
  - Returns download URL or immediate file; can enqueue background job and email attachment.

### Default Templates (backed by `POST /reports/exports`)
- **Daily consolidated**: jobs overview + funnel snapshot + pipeline velocity (last 24h).
- **Monthly consolidated**: same over month, plus month-over-month deltas.
- **HR-wise**: recruiter performance + top N HR by hires/velocity.
- **Job-wise**: funnel + aging per job.
- **Top-performing HR**: rankings by hires, velocity, offer-to-join ratio, sourcing volume.

## Query Approach (sketch)
- **Open positions**: `JobOpenings.status == "ACTIVE"` and `deleted_at is NULL`.
- **New jobs by period**: `date_trunc('day/week/month', created_at)` group/count.
- **Job aging**: `DATEDIFF(now(), created_at)` (DB-specific; fallback in Python).
- **Funnel per job**:
  - Sourced: `CandidateActivity.type == pipeline|general` with `candidate_id` tied to job via `CandidateJobs`.
  - Screened: `CandidateActivity.type == pipeline` and `key_id`/stage denotes screening stage.
  - Offers: `CandidateJobStatus.type == accepted` (or offer status if modeled separately).
  - Join success: accepted/joined ÷ offers (or ÷ sourced, per business rule).
- **Pipeline velocity**: per candidate-job, sort `CandidatePipelineStatus` by `created_at`; diff consecutive timestamps; average per stage.
- **Dropout %**: exits at stage ÷ entrants to that stage (use `CandidateJobStatus` `rejected|dropped` with stage mapping if available).
- **Recruiter productivity**: group by `CandidateActivity.user_id` and/or `CandidateJobs.created_by`.

## Example Schemas (outline)
- `ReportFilter`: date_from/date_to, ids, pipeline_stage_status, pagination.
- `JobOverviewItem`: job_id, title, open_positions, aging_days, created_at.
- `FunnelMetrics`: job_id, sourced, screened, offers, joins, join_ratio.
- `RecruiterPerformance`: user_id, sourced, screened, moves, offers, joins, join_ratio.
- `PipelineVelocity`: job_id, stage_id, avg_hours, p50, p90.
- `DropoutMetric`: stage_id, entrants, exits, dropout_pct.

## Implementation Notes
- Keep SQL in helper functions; avoid heavy ORM graphs to reduce joins.
- Use `selectinload` only when needed; prefer aggregate queries with `session.execute`.
- Add DB indexes if missing: `JobOpenings.status`, `created_at`; `CandidateActivity.candidate_id/user_id/created_at`; `CandidatePipelineStatus.candidate_job_id/created_at/latest`; `CandidateJobs.job_id/candidate_id`.
- Timezone: normalize to UTC; convert to requested TZ in responses/exports.
- Validation: Pydantic schemas; enforce max date span for heavy endpoints.
- AuthZ: require admin/super-admin for performance/clawback; recruiters see own jobs by default.

## Exports & Email
- CSV: stream via `csv.writer`.
- XLSX: `openpyxl` or `xlsxwriter`; simple tables + optional charts.
- PDF: WeasyPrint (HTML/CSS) or ReportLab; embed matplotlib charts as PNG.
- Email: SMTP creds from settings; helper `send_report_email(to, subject, body_html, attachments=[])`.
- Background: FastAPI `BackgroundTasks` for small jobs; optional Celery/RQ for larger.

## FastAPI Routing Sketch
```python
# app/api/reports/jobs.py
router = APIRouter(prefix="/reports/jobs", tags=["reports:jobs"])

@router.get("/overview", response_model=JobOverviewResponse)
def job_overview(filters: ReportFilter = Depends()):
    return job_report_service.get_overview(filters)

@router.get("/{job_id}/funnel", response_model=JobFunnelResponse)
def job_funnel(job_id: int, filters: ReportFilter = Depends()):
    return job_report_service.get_funnel(job_id, filters)
```

## Minimal Delivery Plan
1) Add schemas (`app/schemas/reports.py`).  
2) Add query helpers (`app/repositories/report_queries.py`).  
3) Add services (`app/services/reports/{jobs,recruiters,pipeline,clawback}.py`).  
4) Add exporters + emailer (`app/services/{exporters,emailer}.py`).  
5) Add routers under `app/api/reports`.  
6) Wire into main FastAPI app; add dependency for auth/role guard.  
7) Add basic tests for each service query.  
8) Provide sample Postman/Thunder tests and cron examples for daily/monthly emails.

