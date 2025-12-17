"""
Celery Tasks for Cooling Period Reminders

This module contains Celery background tasks for sending cooling period reminder emails.

Author: [System]
Version: 1.0
Last Modified: [2024-12-13]
"""

from app.celery.celery_config import celery_app
from app.database_layer.db_config import SessionLocal
from app.database_layer.db_model import Candidates, CandidateJobs, CandidateJobStatus, User, JobOpenings, NotificationUser
from app.services.emailer import EmailService
from collections import defaultdict
from datetime import datetime
import logging

logger = logging.getLogger("app_logger")


@celery_app.task(bind=True, name="send_daily_cooling_period_reminders", queue="job_queue")
def send_daily_cooling_period_reminders(self):
    """
    Daily task to send cooling period reminder emails to assigned users.
    Each user gets one email with all their assigned candidates.
    
    This task is scheduled to run daily via Celery Beat.
    """
    task_id = self.request.id
    db = SessionLocal()
    
    try:
        logger.info(f"Starting daily cooling period reminders task: {task_id}")
        today = datetime.utcnow()
        
        # Fetch candidates with joined status
        joined_candidates_data = (
            db.query(
                Candidates.candidate_id,
                Candidates.candidate_name,
                Candidates.candidate_email,
                Candidates.candidate_phone_number,
                CandidateJobStatus.cooling_period_closed,
                Candidates.assigned_to,
            )
            .join(CandidateJobs, CandidateJobs.candidate_id == Candidates.candidate_id)
            .join(CandidateJobStatus, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .filter(CandidateJobStatus.type == "JOINED")
            .filter(Candidates.assigned_to.isnot(None))  # Only candidates with assigned users
            .distinct(Candidates.candidate_id, Candidates.assigned_to)  # Prevent duplicates
            .all()
        )
        
        logger.info(f"Found {len(joined_candidates_data)} joined candidates")
        
        # Group candidates by assigned_to user
        user_candidates = defaultdict(list)
        
        for row in joined_candidates_data:
            remaining_days = None
            if row.cooling_period_closed:
                remaining_days = (row.cooling_period_closed - today).days
                if remaining_days < 0:
                    remaining_days = 0
            
            candidate_info = {
                "candidate_id": row.candidate_id,
                "candidate_name": row.candidate_name,
                "candidate_email": row.candidate_email,
                "candidate_phone_number": row.candidate_phone_number,
                "cooling_period_remaining_days": remaining_days,
            }
            
            user_candidates[row.assigned_to].append(candidate_info)
        
        logger.info(f"Grouped candidates for {len(user_candidates)} users")
        
        # Send emails to each assigned user
        email_service = EmailService()
        email_results = []
        success_count = 0
        failure_count = 0
        
        for user_id, candidates in user_candidates.items():
            # Fetch user details
            user = db.query(User).filter(User.id == user_id).first()
            
            if not user or not user.email:
                logger.warning(f"User {user_id} not found or has no email. Skipping.")
                failure_count += 1
                email_results.append({
                    "user_id": user_id,
                    "status": "failed",
                    "reason": "User not found or no email"
                })
                continue
            
            # Send email with all candidates for this user
            try:
                success = email_service.send_cooling_period_reminder(
                    to_email=user.email,
                    recipient_name=user.username or "User",
                    candidates=candidates
                )
                
                if success:
                    success_count += 1
                else:
                    failure_count += 1
                
                email_results.append({
                    "user_id": user_id,
                    "user_email": user.email,
                    "candidate_count": len(candidates),
                    "status": "sent" if success else "failed",
                })
                
                logger.info(f"Email {'sent' if success else 'failed'} to {user.email} with {len(candidates)} candidate(s)")
                
            except Exception as e:
                failure_count += 1
                logger.error(f"Error sending email to {user.email}: {str(e)}", exc_info=True)
                email_results.append({
                    "user_id": user_id,
                    "user_email": user.email,
                    "status": "failed",
                    "reason": str(e)
                })
        
        result = {
            "task_id": task_id,
            "status": "completed",
            "total_users_notified": len(email_results),
            "success_count": success_count,
            "failure_count": failure_count,
            "email_results": email_results,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Daily cooling period reminders completed: {success_count} sent, {failure_count} failed")
        
        return result
        
    except Exception as e:
        logger.error(f"Error in daily cooling period reminders task: {str(e)}", exc_info=True)
        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
    finally:
        db.close()

@celery_app.task(bind=True, name="send_admin_cooling_period_summary", queue="job_queue")
def send_admin_cooling_period_summary(self):
    """
    Daily task to send cooling period summary to admin/superadmin users.
    Collects all candidates grouped by their assigned HR and sends to notification users.
    
    This task is scheduled to run daily via Celery Beat.
    """
    task_id = self.request.id
    db = SessionLocal()
    
    try:
        logger.info(f"Starting admin cooling period summary task: {task_id}")
        today = datetime.utcnow()
        
        # Fetch candidates with joined status
        joined_candidates_data = (
            db.query(
                Candidates.candidate_id,
                Candidates.candidate_name,
                Candidates.candidate_email,
                Candidates.candidate_phone_number,
                CandidateJobStatus.cooling_period_closed,
                Candidates.assigned_to,
                User.username.label("assigned_hr_name"),
                User.email.label("assigned_hr_email"),
            )
            .join(CandidateJobs, CandidateJobs.candidate_id == Candidates.candidate_id)
            .join(CandidateJobStatus, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
            .join(User, User.id == Candidates.assigned_to, isouter=True)
            .filter(CandidateJobStatus.type == "JOINED")
            .filter(Candidates.assigned_to.isnot(None))  # Only candidates with assigned users
            .distinct(Candidates.candidate_id, Candidates.assigned_to)
            .all()
        )
        
        logger.info(f"Found {len(joined_candidates_data)} joined candidates for admin summary")
        
        # Group candidates by assigned HR user
        hr_candidates = defaultdict(list)
        
        for row in joined_candidates_data:
            remaining_days = None
            if row.cooling_period_closed:
                remaining_days = (row.cooling_period_closed - today).days
                if remaining_days < 0:
                    remaining_days = 0
            
            candidate_info = {
                "candidate_id": row.candidate_id,
                "candidate_name": row.candidate_name,
                "candidate_email": row.candidate_email,
                "candidate_phone_number": row.candidate_phone_number,
                "cooling_period_remaining_days": remaining_days,
            }
            
            # Group by assigned HR
            hr_key = row.assigned_to if row.assigned_to else "unassigned"
            hr_candidates[hr_key].append({
                "hr_user_id": row.assigned_to,
                "hr_name": row.assigned_hr_name or "Unassigned",
                "hr_email": row.assigned_hr_email,
                "candidate": candidate_info,
            })
        
        # Fetch notification users (admin/superadmin)
        notification_users = (
            db.query(NotificationUser.user_id, User.email, User.username)
            .join(User, User.id == NotificationUser.user_id)
            .all()
        )
        
        if not notification_users:
            logger.info("No notification users found. Skipping admin summary email.")
            return {
                "task_id": task_id,
                "status": "completed",
                "message": "No notification users configured",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        logger.info(f"Sending admin summary to {len(notification_users)} notification users")
        
        # Prepare summary data for admins
        summary_data = []
        for hr_key, candidates_data in hr_candidates.items():
            if hr_key != "unassigned":
                hr_info = candidates_data[0] if candidates_data else {}
                summary_data.append({
                    "hr_user_id": hr_info.get("hr_user_id"),
                    "hr_name": hr_info.get("hr_name"),
                    "hr_email": hr_info.get("hr_email"),
                    "candidates": [c["candidate"] for c in candidates_data],
                    "candidate_count": len(candidates_data),
                })
            else:
                summary_data.append({
                    "hr_user_id": None,
                    "hr_name": "Unassigned",
                    "hr_email": None,
                    "candidates": [c["candidate"] for c in candidates_data],
                    "candidate_count": len(candidates_data),
                })
        
        # Send emails to each notification user
        email_service = EmailService()
        email_results = []
        success_count = 0
        failure_count = 0
        
        for notif_user in notification_users:
            user_id, user_email, user_name = notif_user
            
            if not user_email:
                logger.warning(f"Notification user {user_id} has no email. Skipping.")
                failure_count += 1
                email_results.append({
                    "user_id": user_id,
                    "status": "failed",
                    "reason": "No email found"
                })
                continue
            
            try:
                success = email_service.send_admin_cooling_period_summary(
                    to_email=user_email,
                    recipient_name=user_name or "Admin",
                    hr_candidates_summary=summary_data
                )
                
                if success:
                    success_count += 1
                else:
                    failure_count += 1
                
                email_results.append({
                    "user_id": user_id,
                    "user_email": user_email,
                    "status": "sent" if success else "failed",
                })
                
                logger.info(f"Admin summary email {'sent' if success else 'failed'} to {user_email}")
                
            except Exception as e:
                failure_count += 1
                logger.error(f"Error sending admin summary email to {user_email}: {str(e)}", exc_info=True)
                email_results.append({
                    "user_id": user_id,
                    "user_email": user_email,
                    "status": "failed",
                    "reason": str(e)
                })
        
        result = {
            "task_id": task_id,
            "status": "completed",
            "total_hrs_tracked": len(hr_candidates),
            "total_admins_notified": len(email_results),
            "success_count": success_count,
            "failure_count": failure_count,
            "email_results": email_results,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Admin cooling period summary completed: {success_count} sent, {failure_count} failed")
        
        return result
        
    except Exception as e:
        logger.error(f"Error in admin cooling period summary task: {str(e)}", exc_info=True)
        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
    finally:
        db.close()