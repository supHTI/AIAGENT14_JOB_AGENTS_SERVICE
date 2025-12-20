# Cooling Period System - Quick Reference

## What Changed

### 📧 Email Content
**BEFORE**: Email tables included phone numbers and emails
```
| # | Name | ID | Email | Phone | Days |
```

**AFTER**: Simplified email tables without contact info
```
| # | Name | ID | Days |
```

### 📊 Excel Generation
**NEW FEATURE**: All emails now include Excel attachments

1. **HR-Level Excel** (for HR users)
   - One file per email
   - Shows their assigned candidates
   - Columns: Name | ID | Joining | Clawback End | Days

2. **Manager-Level Excel** (for admins)
   - Shows all candidates grouped by HR
   - Columns: HR Name | HR Email | Candidate Name | ID | Joining | Clawback | Days

3. **Completed Cooling Excel** (for completed periods)
   - HR version: Candidate details only
   - Admin version: Candidate + HR details

### 🤖 New Celery Task
**NEW**: `send_completed_cooling_period_notifications`
- Triggers when cooling periods are completed (cooling_period_closed <= today)
- Sends separate emails to HR and Admin users
- HR gets: Their completed candidates
- Admin gets: All completed candidates with HR names

### 🎨 Enhanced Styling
- Excel headers: Blue (#438EFC) with white text
- Table borders and formatting: Professional appearance
- Color-coded status in emails (green for completed, purple for active)
- Consistent branding throughout

## Files Changed

| File | Type | What Changed |
|------|------|--------------|
| `app/services/excel_generator.py` | NEW | Complete Excel generation utility |
| `app/services/emailer.py` | MODIFIED | Updated email methods, added 2 new methods |
| `app/celery/tasks/cooling_period_task.py` | MODIFIED | Enhanced 2 tasks, added 1 new task |

## Key Code Changes

### 1. Excel Generation
```python
from app.services.excel_generator import ExcelGenerator

# Generate HR-level report
excel = ExcelGenerator.generate_hr_level_excel(
    job_title="Senior Developer",
    candidates=[...]
)

# Generate manager-level report
excel = ExcelGenerator.generate_manager_level_excel(
    job_title="Senior Developer",
    hr_candidates_data=[...]
)

# Generate completed report
excel = ExcelGenerator.generate_completed_cooling_excel(
    completed_candidates=[...],
    include_hr_details=True  # True for admin, False for HR
)
```

### 2. Email with Excel
```python
email_service.send_cooling_period_reminder(
    to_email="hr@company.com",
    recipient_name="Alice HR",
    candidates=[...],
    excel_attachment=excel_data,  # NEW parameter
    job_title="Senior Developer"   # NEW parameter
)
```

### 3. New Email Method
```python
email_service.send_completed_cooling_notification(
    to_email="user@company.com",
    recipient_name="John",
    completed_candidates=[...],
    excel_attachment=excel_data,
    is_admin=False  # True for admin, False for HR
)
```

### 4. New Task
```python
@celery_app.task(bind=True, name="send_completed_cooling_period_notifications")
def send_completed_cooling_period_notifications(self):
    # Sends notifications when cooling periods complete
    # Separate emails for HR and Admin users
    ...
```

## Database Queries

### What's Now Calculated
- ✅ Clawback end date from: `joined_at + cooling_period days`
- ✅ Remaining days from: `(clawback_end_date - today).days`
- ✅ Filters for active periods: `cooling_period_closed IS NULL`
- ✅ Filters for completed: `cooling_period_closed <= today`

### Joins Used
- ✅ CandidateJobs (to link candidates to jobs)
- ✅ CandidateJobStatus (for dates and status)
- ✅ JobOpenings (for cooling period and job title)
- ✅ User (for HR names and emails)

## Email Schedule (Recommended)

```
Task 1: 09:00 AM - Send HR Reminders
        ↓
        (Excel with their assigned candidates)

Task 2: 10:00 AM - Send Admin Summary
        ↓
        (Excel with all candidates by HR)

Task 3: 11:00 AM - Send Completed Notifications
        ↓
        (Excel for completed candidates)
```

## Data Structure Examples

### Candidate Info (HR Email)
```python
{
    "candidate_id": "CND001",
    "candidate_name": "John Doe",
    "joining_date": "2024-12-01",
    "clawback_end_date": "2025-01-10",
    "days_remaining": 30,
    "cooling_period_remaining_days": 30,
}
```

### Completed Candidate (HR)
```python
{
    "candidate_id": "CND001",
    "candidate_name": "John Doe",
    "joining_date": "2024-12-01",
    "cooling_end_date": "2025-01-10",
    "cooling_period_days": 40,
}
```

### Completed Candidate (Admin)
```python
{
    "candidate_id": "CND001",
    "candidate_name": "John Doe",
    "hr_name": "Alice HR",
    "hr_email": "alice@company.com",
    "joining_date": "2024-12-01",
    "cooling_end_date": "2025-01-10",
    "cooling_period_days": 40,
}
```

## Installation Checklist

- [ ] Install openpyxl: `pip install openpyxl`
- [ ] Copy `excel_generator.py` to `app/services/`
- [ ] Update `emailer.py` with new methods
- [ ] Update `cooling_period_task.py` with enhanced tasks
- [ ] Add to requirements.txt: `openpyxl>=3.0`
- [ ] Configure Celery Beat schedule
- [ ] Test with sample data
- [ ] Verify SMTP configuration
- [ ] Check database fields exist

## Verification Commands

```bash
# Test Excel generation
python -c "from app.services.excel_generator import ExcelGenerator; print('✓ Excel generator imported')"

# Test email service
python -c "from app.services.emailer import EmailService; print('✓ Email service updated')"

# Test tasks
python -c "from app.celery.tasks.cooling_period_task import send_completed_cooling_period_notifications; print('✓ New task imported')"
```

## Email Subjects

| Task | Email Subject |
|------|--------------|
| Task 1 | "Cooling Period Reminder - X Candidate(s) Assigned to You" |
| Task 2 | "Cooling Period Summary - Manager Report" |
| Task 3 | "✅ Cooling Period Completed - X Candidate(s)" |

## Key Improvements

| Feature | Before | After |
|---------|--------|-------|
| Excel Reports | ❌ None | ✅ 3 types |
| Completed Tracking | ❌ Not tracked | ✅ Separate notifications |
| Data Organization | Single list | ✅ By HR / By Job |
| Contact Privacy | ❌ In emails | ✅ In Excel only |
| Admin Visibility | ❌ Limited | ✅ Comprehensive |
| Date Calculations | ❌ Manual | ✅ Automatic |
| Error Handling | Basic | ✅ Enhanced |

## Next Steps

1. Deploy the three updated/new files
2. Install openpyxl dependency
3. Configure Celery Beat schedule
4. Test with sample data
5. Monitor logs for first execution
6. Adjust scheduling as needed

## Support

If any issues occur:
1. Check `app_logger` logs
2. Verify all imports are working
3. Confirm database fields exist
4. Test SMTP configuration
5. Review sample data in Excel files

---
**Last Updated**: December 2024
**Status**: Ready for Production
