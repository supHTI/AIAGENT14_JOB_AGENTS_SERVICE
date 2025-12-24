"""
Celery Tasks for Cooling Period Reminders

This module contains Celery background tasks for sending cooling period reminder emails.

Author: [System]
Version: 1.0
Last Modified: [2024-12-13]
"""

from app.celery.celery_config import celery_app
from app.database_layer.db_config import SessionLocal
from app.database_layer.db_model import Candidates, CandidateJobs,CandidateJobStatusType, CandidateJobStatus, User, JobOpenings, NotificationUser
from app.services.emailer import EmailService
from app.services.excel_generator import ExcelGenerator
from collections import defaultdict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("app_logger")



@celery_app.task(bind=True, name="send_daily_cooling_period_reminders", queue="job_queue")
def send_daily_cooling_period_reminders(self):
    task_id = self.request.id
    db = SessionLocal()
    today = datetime.utcnow()

    try:
        logger.info(f"[{task_id}] HR cooling reminder started")

        joined_statuses = (
            db.query(CandidateJobStatus)
            .filter(CandidateJobStatus.type == CandidateJobStatusType.JOINED)
            .all()
        )

        hr_candidates = defaultdict(list)
        statuses_to_close = []

        for status in joined_statuses:
            cj = status.candidate_job
            candidate = cj.candidate
            job = cj.job

            # 1️⃣ uniqueness
            joined_count = (
                db.query(CandidateJobStatus)
                .filter(
                    CandidateJobStatus.candidate_job_id == cj.id,
                    CandidateJobStatus.type == CandidateJobStatusType.JOINED,
                )
                .count()
            )
            if joined_count != 1:
                continue

            # 2️⃣ already closed
            if status.cooling_period_closed:
                continue

            # 3️⃣ valid cooling
            if not job.cooling_period or job.cooling_period <= 0:
                continue

            # 4️⃣ joined_at
            if not status.joined_at:
                continue

            clawback_end = status.joined_at + timedelta(days=int(job.cooling_period))
            remaining_days = (clawback_end - today).days

            # 5️⃣ auto-close
            if remaining_days <= 0:
                status.cooling_period_closed = today
                statuses_to_close.append(status)
                remaining_days = 0

            hr_candidates[candidate.assigned_to].append({
                "candidate_id": candidate.candidate_id,
                "candidate_name": candidate.candidate_name,
                "joining_date": status.joined_at.date(),
                "clawback_end_date": clawback_end.date(),
                "days_remaining": remaining_days,
                "cooling_period_remaining_days": remaining_days,
                "job_title": job.title,
            })

        if statuses_to_close:
            db.commit()
            logger.info(f"[{task_id}] Closed {len(statuses_to_close)} cooling periods")

        email_service = EmailService()
        success, failed = 0, 0

        for hr_id, candidates in hr_candidates.items():
            if not hr_id:
                continue

            hr = db.query(User).filter(User.id == hr_id).first()
            if not hr or not hr.email:
                failed += 1
                continue

            # Group HR candidates by job title so Excel has one sheet per job
            job_grouped = defaultdict(list)
            for c in candidates:
                job_grouped[c.get('job_title', 'Unknown Job')].append(c)

            excel = ExcelGenerator.generate_hr_level_excel(job_grouped)

            sent = email_service.send_cooling_period_reminder(
                to_email=hr.email,
                recipient_name=hr.username or "HR",
                candidates=candidates,
                excel_attachment=excel,
                job_title="Cooling Period Reminder",
            )

            success += int(sent)
            failed += int(not sent)

        return {
            "task_id": task_id,
            "status": "completed",
            "success": success,
            "failed": failed,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"[{task_id}] HR reminder failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}

    finally:
        db.close()
@celery_app.task(bind=True, name="send_admin_cooling_period_summary", queue="job_queue")
def send_admin_cooling_period_summary(self):
    task_id = self.request.id
    db = SessionLocal()
    today = datetime.utcnow()

    try:
        logger.info(f"[{task_id}] Admin cooling summary started")

        joined_statuses = (
            db.query(CandidateJobStatus)
            .filter(CandidateJobStatus.type == CandidateJobStatusType.JOINED)
            .all()
        )

        hr_grouped = defaultdict(list)
        statuses_to_close = []

        for status in joined_statuses:
            cj = status.candidate_job
            candidate = cj.candidate
            job = cj.job
            
            # Fetch HR user from database using assigned_to ID
            hr = db.query(User).filter(User.id == candidate.assigned_to).first() if candidate.assigned_to else None

            # same 5 rules as API
            if status.cooling_period_closed:
                continue
            if not job.cooling_period or job.cooling_period <= 0:
                continue
            if not status.joined_at:
                continue

            joined_count = (
                db.query(CandidateJobStatus)
                .filter(
                    CandidateJobStatus.candidate_job_id == cj.id,
                    CandidateJobStatus.type == CandidateJobStatusType.JOINED,
                )
                .count()
            )
            if joined_count != 1:
                continue

            clawback_end = status.joined_at + timedelta(days=int(job.cooling_period))
            remaining_days = (clawback_end - today).days

            if remaining_days <= 0:
                status.cooling_period_closed = today
                statuses_to_close.append(status)
                remaining_days = 0

            hr_grouped[candidate.assigned_to].append({
                "candidate_name": candidate.candidate_name,
                "candidate_id": candidate.candidate_id,
                "joining_date": status.joined_at.date(),
                "clawback_end_date": clawback_end.date(),
                "days_remaining": remaining_days,
                "cooling_period_remaining_days": remaining_days,
                "job_title": job.title if job and getattr(job, 'title', None) else "Unknown Job",
                "hr_name": hr.username if hr else "Unassigned",
                "hr_email": hr.email if hr else None,
            })

        if statuses_to_close:
            db.commit()

        # Admin users
        admins = (
            db.query(NotificationUser.user_id, User.email, User.username)
            .join(User, User.id == NotificationUser.user_id)
            .all()
        )

        if not admins:
            return {"status": "completed", "message": "No admins configured"}

        # Build summary data: list of dicts with hr metadata and their candidates
        summary_data = []
        for hr_data in hr_grouped.values():
            hr_name = hr_data[0].get("hr_name") if hr_data else "Unassigned"
            hr_email = hr_data[0].get("hr_email") if hr_data and hr_data[0].get("hr_email") else None
            summary_data.append({
                "hr_name": hr_name,
                "hr_email": hr_email,
                "candidates": hr_data,
            })

        # Build a job_title -> rows mapping across HR buckets for manager report
        job_grouped = defaultdict(list)
        for hr in summary_data:
            hr_name = hr.get('hr_name', 'Unassigned')
            hr_email = hr.get('hr_email', None)
            for candidate in hr.get('candidates', []):
                job_title = candidate.get('job_title', 'Unknown Job')
                job_grouped[job_title].append({
                    'hr_name': hr_name,
                    'hr_email': hr_email,
                    'candidate_name': candidate.get('candidate_name'),
                    'candidate_id': candidate.get('candidate_id'),
                    'joining_date': str(candidate.get('joining_date')),
                    'clawback_end_date': str(candidate.get('clawback_end_date')),
                    'days_remaining': candidate.get('days_remaining', 0),
                })

        excel = ExcelGenerator.generate_manager_level_excel(
            "Cooling Period Summary",
            job_grouped,
        )

        email_service = EmailService()
        success, failed = 0, 0

        for _, email, name in admins:
            sent = email_service.send_admin_cooling_period_summary(
                to_email=email,
                recipient_name=name or "Admin",
                hr_candidates_summary=summary_data,
                excel_attachment=excel,
            )
            success += int(sent)
            failed += int(not sent)

        return {
            "task_id": task_id,
            "status": "completed",
            "success": success,
            "failed": failed,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"[{task_id}] Admin summary failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}

    finally:
        db.close()


@celery_app.task(bind=True, name="send_completed_cooling_period_notifications", queue="job_queue")
def send_completed_cooling_period_notifications(self):
    """
    Daily task to send notifications for candidates with completed cooling periods.
    Sends separate emails to HR users and admin users.
    
    For HR: Lists their completed candidates
    For Admin: Lists all completed candidates grouped by HR
    """
    task_id = self.request.id
    db = SessionLocal()
    
    try:
        logger.info(f"Starting completed cooling period notifications task: {task_id}")
        today = datetime.utcnow()
        
        # Find candidates whose cooling period has completed TODAY or earlier
        completed_candidates_data = (
            db.query(
                Candidates.candidate_id,
                Candidates.candidate_name,
                Candidates.assigned_to,
                CandidateJobStatus.cooling_period_closed,
                CandidateJobStatus.joined_at,
                User.username.label("assigned_hr_name"),
                User.email.label("assigned_hr_email"),
                JobOpenings.cooling_period,
            )
            .join(CandidateJobs, CandidateJobs.candidate_id == Candidates.candidate_id)
            .join(CandidateJobStatus, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .join(User, User.id == Candidates.assigned_to, isouter=True)
            .join(JobOpenings, JobOpenings.id == CandidateJobs.job_id)
            .filter(CandidateJobStatus.type == "JOINED")
            .filter(CandidateJobStatus.cooling_period_closed.isnot(None))
            .filter(CandidateJobStatus.cooling_period_closed <= today)  # Completed
            .all()
        )
        
        if not completed_candidates_data:
            logger.info("No candidates with completed cooling periods found.")
            return {
                "task_id": task_id,
                "status": "completed",
                "message": "No completed cooling periods",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        logger.info(f"Found {len(completed_candidates_data)} candidates with completed cooling periods")
        
        # Group by assigned HR
        hr_completed = defaultdict(list)
        all_completed_for_admin = []
        
        for row in completed_candidates_data:
            candidate_info = {
                "candidate_id": row.candidate_id,
                "candidate_name": row.candidate_name,
                "joining_date": row.joined_at.date() if row.joined_at else None,
                "cooling_end_date": row.cooling_period_closed.date() if row.cooling_period_closed else None,
                "cooling_period_days": int(row.cooling_period) if row.cooling_period else 0,
                "hr_name": row.assigned_hr_name or "Unassigned",
                "hr_email": row.assigned_hr_email,
            }
            
            hr_key = row.assigned_to if row.assigned_to else "unassigned"
            hr_completed[hr_key].append(candidate_info)
            all_completed_for_admin.append(candidate_info)
        
        # Send emails to HR users
        email_service = EmailService()
        email_results = []
        success_count = 0
        failure_count = 0
        
        logger.info(f"Sending completed cooling period notifications to {len(hr_completed)} HR users")
        
        for hr_user_id, candidates in hr_completed.items():
            if hr_user_id == "unassigned":
                continue  # Skip unassigned for now
            
            # Get HR user details
            hr_user = db.query(User).filter(User.id == hr_user_id).first()
            
            if not hr_user or not hr_user.email:
                logger.warning(f"HR User {hr_user_id} not found or has no email. Skipping.")
                failure_count += 1
                continue
            
            try:
                # Generate Excel for HR
                excel_data = ExcelGenerator.generate_completed_cooling_excel(
                    candidates,
                    include_hr_details=False
                )
                
                success = email_service.send_completed_cooling_notification(
                    to_email=hr_user.email,
                    recipient_name=hr_user.username or "HR User",
                    completed_candidates=candidates,
                    excel_attachment=excel_data,
                    is_admin=False,
                )
                
                if success:
                    success_count += 1
                else:
                    failure_count += 1
                
                email_results.append({
                    "user_id": hr_user_id,
                    "user_email": hr_user.email,
                    "candidate_count": len(candidates),
                    "status": "sent" if success else "failed",
                    "type": "hr"
                })
                
                logger.info(f"Completed cooling notification {'sent' if success else 'failed'} to HR {hr_user.email}")
                
            except Exception as e:
                failure_count += 1
                logger.error(f"Error sending completed notification to HR {hr_user_id}: {str(e)}", exc_info=True)
                email_results.append({
                    "user_id": hr_user_id,
                    "status": "failed",
                    "reason": str(e),
                    "type": "hr"
                })
        
        # Send emails to notification users (admins)
        notification_users = (
            db.query(NotificationUser.user_id, User.email, User.username)
            .join(User, User.id == NotificationUser.user_id)
            .all()
        )
        
        logger.info(f"Sending completed cooling period summary to {len(notification_users)} admin users")
        
        for notif_user in notification_users:
            user_id, user_email, user_name = notif_user
            
            if not user_email:
                logger.warning(f"Notification user {user_id} has no email. Skipping.")
                failure_count += 1
                continue
            
            try:
                # Generate Excel for admin - includes HR names
                excel_data = ExcelGenerator.generate_completed_cooling_excel(
                    all_completed_for_admin,
                    include_hr_details=True
                )
                
                success = email_service.send_completed_cooling_notification(
                    to_email=user_email,
                    recipient_name=user_name or "Admin",
                    completed_candidates=all_completed_for_admin,
                    excel_attachment=excel_data,
                    is_admin=True,
                )
                
                if success:
                    success_count += 1
                else:
                    failure_count += 1
                
                email_results.append({
                    "user_id": user_id,
                    "user_email": user_email,
                    "candidate_count": len(all_completed_for_admin),
                    "status": "sent" if success else "failed",
                    "type": "admin"
                })
                
                logger.info(f"Completed cooling summary {'sent' if success else 'failed'} to admin {user_email}")
                
            except Exception as e:
                failure_count += 1
                logger.error(f"Error sending completed summary to admin {user_id}: {str(e)}", exc_info=True)
                email_results.append({
                    "user_id": user_id,
                    "status": "failed",
                    "reason": str(e),
                    "type": "admin"
                })
        
        result = {
            "task_id": task_id,
            "status": "completed",
            "total_completed_candidates": len(all_completed_for_admin),
            "total_hrs_notified": len(hr_completed),
            "total_admins_notified": len(notification_users),
            "success_count": success_count,
            "failure_count": failure_count,
            "email_results": email_results,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Completed cooling period notifications finished: {success_count} sent, {failure_count} failed")
        
        return result
        
    except Exception as e:
        logger.error(f"Error in completed cooling period notifications task: {str(e)}", exc_info=True)
        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
    finally:
        db.close()