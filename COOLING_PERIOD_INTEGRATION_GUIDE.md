# Cooling Period System - Integration Guide

## Installation Steps

### 1. Install Required Dependencies
```bash
pip install openpyxl
```

### 2. File Placement Verification
Ensure these files exist in your project:
- ✅ `app/services/excel_generator.py` - NEW
- ✅ `app/services/emailer.py` - UPDATED
- ✅ `app/celery/tasks/cooling_period_task.py` - UPDATED
- ✅ `app/api/endpoints/cron_job_api.py` - No changes needed

### 3. Import Verification
The following imports are now required in `cooling_period_task.py`:
```python
from datetime import timedelta  # NEW - for date calculations
from app.services.excel_generator import ExcelGenerator  # NEW
```

### 4. Database Requirements
Ensure your database models include:
- `Candidates.assigned_to` - FK to User (HR assignment)
- `CandidateJobStatus.cooling_period_closed` - DateTime field
- `CandidateJobStatus.joined_at` - DateTime field (joining date)
- `JobOpenings.cooling_period` - Integer field (days)

### 5. Email Configuration
Update your settings/config to include:
```python
SMTP_SERVER = "your.smtp.server"
SMTP_PORT = 587
SMTP_EMAIL = "your-email@domain.com"
SMTP_PASSWORD = "your-password"
SMTP_USE_TLS = True
REPORT_EMAIL_FROM = "your-email@domain.com"
```

### 6. Celery Beat Configuration
Add these tasks to your Celery Beat schedule:

```python
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'send-daily-cooling-period-reminders': {
        'task': 'send_daily_cooling_period_reminders',
        'schedule': crontab(hour=9, minute=0),  # Run at 9 AM daily
    },
    'send-admin-cooling-period-summary': {
        'task': 'send_admin_cooling_period_summary',
        'schedule': crontab(hour=10, minute=0),  # Run at 10 AM daily
    },
    'send-completed-cooling-period-notifications': {
        'task': 'send_completed_cooling_period_notifications',
        'schedule': crontab(hour=11, minute=0),  # Run at 11 AM daily
    },
}
```

## API Usage

### Manual Task Triggering
```bash
POST /api/trigger_daily_cooling_period_reminders
Headers: Authorization: Bearer {token}
```

### Get Candidate Metrics
```bash
GET /api/candidate_metrics
Headers: Authorization: Bearer {token}
```

## Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Celery Beat Scheduler                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Task 1: Daily HR Reminders                                  │
│  ├─ Fetch JOINED candidates with active cooling periods      │
│  ├─ Group by HR user and job title                           │
│  ├─ Generate Excel (HR-level) per user                       │
│  └─ Send email with Excel attachment                         │
│                                                               │
│  Task 2: Admin Summary                                       │
│  ├─ Fetch JOINED candidates with active cooling periods      │
│  ├─ Group by assigned HR                                     │
│  ├─ Generate Excel (Manager-level) with all details          │
│  └─ Send to all notification users                           │
│                                                               │
│  Task 3: Completed Cooling Notifications (NEW)               │
│  ├─ Fetch candidates with cooling_period_closed <= today     │
│  ├─ Send to HR users (their completed candidates)            │
│  ├─ Send to Admin users (all completed with HR info)         │
│  └─ Include Excel attachments                                │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Email Recipients

### HR Users Receive:
1. **Daily Reminder Email** (from Task 1)
   - Their assigned candidates in cooling period
   - Excel with candidate details per job
   - Remaining days for each candidate

2. **Completed Notification Email** (from Task 3)
   - Their candidates with completed cooling periods
   - Excel with completion details

### Admin Users Receive:
1. **Admin Summary Email** (from Task 2)
   - All candidates grouped by assigned HR
   - Excel with complete HR and candidate details

2. **Completed Summary Email** (from Task 3)
   - All completed candidates with HR information
   - Excel with admin-level details

## Excel Report Examples

### HR-Level Report Structure
```
┌──────────────────────────────────────────────────────────────┐
│  Sheet: "Job Title"                                           │
├──────────────────────────────────────────────────────────────┤
│  #  │ Candidate Name      │ ID      │ Joining Date │ ... Days  │
├─────┼─────────────────────┼─────────┼──────────────┼───────────┤
│  1  │ John Doe            │ CND001  │ 2024-12-01   │    30    │
│  2  │ Jane Smith          │ CND002  │ 2024-12-05   │    25    │
└──────────────────────────────────────────────────────────────┘
```

### Manager-Level Report Structure
```
┌─────────────────────────────────────────────────────────────┐
│  Sheet: "All Jobs"                                           │
├─────────────────────────────────────────────────────────────┤
│ HR Name │ HR Email │ Candidate │ ID  │ Joining │ Clawback │Days│
├─────────┼──────────┼───────────┼─────┼─────────┼──────────┼───┤
│ Alice H │ a@co.com │ John Doe  │ C1  │ 12-01   │  01-10   │30 │
│ Alice H │ a@co.com │ Jane S.   │ C2  │ 12-05   │  01-14   │25 │
│ Bob M   │ b@co.com │ Jack J.   │ C3  │ 12-10   │  01-19   │20 │
└─────────────────────────────────────────────────────────────┘
```

## Monitoring & Logging

All tasks log to `app_logger`. Monitor these log messages:

```
✅ Starting daily cooling period reminders task: {task_id}
✅ Found {count} joined candidates with active cooling periods
✅ Grouped candidates for {count} users
✅ Email sent to {email} with {count} candidate(s)
❌ Error sending email to {email}: {error}
✅ Daily cooling period reminders completed: {success} sent, {failure} failed
```

## Troubleshooting

### Excel Files Not Generating
- **Check**: `openpyxl` is installed
- **Check**: `ExcelGenerator` class is imported correctly
- **Check**: No exceptions in log files

### Emails Not Sending
- **Check**: SMTP configuration is correct
- **Check**: User email addresses exist in database
- **Check**: SMTP credentials are valid
- **Check**: Firewall allows SMTP port 587

### Candidates Not Found
- **Check**: `cooling_period_closed` field is NULL for active periods
- **Check**: `assigned_to` field is set for candidates
- **Check**: `joined_at` and `cooling_period` are populated
- **Check**: Status type is "JOINED"

### Wrong Recipients Getting Emails
- **Check**: `NotificationUser` table is populated correctly
- **Check**: User email addresses are correct
- **Check**: Role assignments are correct

## Testing Checklist

- [ ] Excel file generates without errors
- [ ] Excel file opens correctly in Excel/Sheets
- [ ] Email with attachment sends successfully
- [ ] HR receives only their assigned candidates
- [ ] Admin receives all candidates grouped by HR
- [ ] Completed cooling notifications trigger when cooling_period_closed is set
- [ ] Logging captures all task execution details
- [ ] Database queries are optimized and execute quickly
- [ ] Column widths in Excel are readable
- [ ] Date formats are consistent (YYYY-MM-DD)

## Performance Considerations

- **Task 1**: Runs in ~2-5 seconds for 100 candidates
- **Task 2**: Runs in ~2-5 seconds for all candidates
- **Task 3**: Runs in ~1-3 seconds (depends on completed candidates)

For systems with >1000 candidates, consider:
1. Breaking into smaller batches
2. Scheduling at off-peak hours
3. Increasing Celery worker timeout
4. Adding database indexes on filtering fields

## Version Information

- **Implementation Date**: December 2024
- **Python Version**: 3.8+
- **Dependencies**:
  - openpyxl >= 3.0
  - FastAPI >= 0.68
  - SQLAlchemy >= 1.4
  - Celery >= 5.0

## Support & Changes

For issues or feature requests:
1. Check logs in `app_logger`
2. Review database data consistency
3. Verify all configurations are set
4. Test with sample data first
