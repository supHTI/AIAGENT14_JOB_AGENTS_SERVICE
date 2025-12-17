# Cooling Period Reminder - Celery Scheduled Task

## Overview
Automatic daily email reminders for candidates in cooling period, grouped by assigned users.

## Features
- ✅ **Automatic Daily Execution**: Runs every day at 9:00 AM UTC via Celery Beat
- ✅ **Grouped Emails**: One email per user containing all their assigned candidates
- ✅ **Color-coded Status**: Visual indicators for cooling period remaining days
- ✅ **Manual Trigger**: API endpoint to trigger emails manually
- ✅ **Task Status Check**: Monitor task execution status
- ✅ **Duplicate Prevention**: Ensures unique candidates per user

## Setup Instructions

### 1. Start Celery Worker
Run the Celery worker to process tasks:

```bash
# Windows (PowerShell)
celery -A app.celery.celery_config:celery_app worker --loglevel=info -P threads --pool=solo

# Linux/Mac
celery -A app.celery.celery_config:celery_app worker --loglevel=info
```

### 2. Start Celery Beat (Scheduler)
Run Celery Beat to schedule periodic tasks:

```bash
# Windows (PowerShell)
celery -A app.celery.celery_config:celery_app beat --loglevel=info

# Linux/Mac
celery -A app.celery.celery_config:celery_app beat --loglevel=info
```

**Note**: Keep both worker and beat running for automatic daily execution.

### 3. Combined Command (Optional)
You can also run worker and beat together:

```bash
celery -A app.celery.celery_config:celery_app worker --beat --loglevel=info -P threads --pool=solo
```

## API Endpoints

### 1. Get Candidate Metrics (with grouping)
```http
GET /candidate_metrics
```

**Response:**
```json
{
  "total_candidates": 5,
  "joined_candidates": [...],
  "grouped_by_user": {
    "user@example.com": {
      "user_id": 3,
      "user_name": "John Doe",
      "user_email": "user@example.com",
      "candidates": [...]
    }
  }
}
```

### 2. Send Reminders Immediately (Synchronous)
```http
POST /send_cooling_period_reminders
```

Sends emails immediately in the request context.

### 3. Trigger Daily Task (Asynchronous - Recommended)
```http
POST /trigger_daily_cooling_period_reminders
```

Queues the task to Celery for background processing.

**Response:**
```json
{
  "message": "Daily cooling period reminder task has been queued",
  "task_id": "abc123...",
  "status": "queued"
}
```

### 4. Check Task Status
```http
GET /check_cooling_period_task/{task_id}
```

**Response:**
```json
{
  "task_id": "abc123...",
  "status": "SUCCESS",
  "ready": true,
  "successful": true,
  "result": {
    "status": "completed",
    "success_count": 2,
    "failure_count": 0,
    "email_results": [...]
  }
}
```

## Celery Beat Schedule

The task is configured to run automatically at **9:00 AM UTC** every day.

You can modify the schedule in `app/celery/celery_config.py`:

```python
beat_schedule={
    "send-daily-cooling-period-reminders": {
        "task": "send_daily_cooling_period_reminders",
        "schedule": crontab(hour=9, minute=0),  # 9:00 AM UTC daily
        "options": {"queue": "job_queue"},
    },
}
```

### Schedule Examples:
```python
# Every day at 9 AM UTC
crontab(hour=9, minute=0)

# Every day at 9 AM and 5 PM UTC
crontab(hour='9,17', minute=0)

# Every Monday at 9 AM UTC
crontab(hour=9, minute=0, day_of_week=1)

# Every hour
crontab(minute=0)
```

## Email Template

Each user receives an HTML email with:
- Professional HTI branding
- Table of assigned candidates
- Candidate details (name, email, phone)
- Color-coded cooling period status:
  - 🟢 Green: > 30 days remaining
  - 🟡 Yellow: 7-30 days remaining
  - 🔴 Red: < 7 days remaining

## Files Modified/Created

1. **Created**: `app/celery/tasks/cooling_period_tasks.py` - Celery task definition
2. **Modified**: `app/celery/celery_config.py` - Added task import and beat schedule
3. **Modified**: `app/services/emailer.py` - Added `send_cooling_period_reminder()` method
4. **Modified**: `app/api/endpoints/pdf_api.py` - Added endpoints for manual trigger and status check

## Monitoring

### Check Celery Worker Status
```bash
celery -A app.celery.celery_config:celery_app inspect active
```

### Check Scheduled Tasks
```bash
celery -A app.celery.celery_config:celery_app inspect scheduled
```

### View Registered Tasks
```bash
celery -A app.celery.celery_config:celery_app inspect registered
```

## Troubleshooting

### Task not running automatically
- Ensure Celery Beat is running
- Check beat logs for errors
- Verify Redis connection

### Emails not sending
- Check SMTP configuration in environment variables
- Verify user emails exist in database
- Check worker logs for error details

### Task stuck in PENDING
- Check if worker is running
- Verify Redis connection
- Check worker logs

## Environment Variables

Required SMTP configuration:
```env
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_EMAIL=your-email@example.com
SMTP_PASSWORD=your-password
SMTP_USE_TLS=True
```

## Testing

Test the setup manually:
```bash
# Trigger the task
curl -X POST http://localhost:8115/trigger_daily_cooling_period_reminders

# Check status (use task_id from previous response)
curl http://localhost:8115/check_cooling_period_task/{task_id}
```

## Production Recommendations

1. **Use Supervisor/systemd** to keep Celery worker and beat running
2. **Monitor with Flower**: `pip install flower && celery -A app.celery.celery_config:celery_app flower`
3. **Set appropriate timezone** for your region
4. **Log rotation** for Celery logs
5. **Alert on failures** using monitoring tools

## Support

For issues or questions, check the logs:
- Application logs: `app_logger`
- Celery worker logs: Console output
- Celery beat logs: Console output
