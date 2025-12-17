"""
Celery Tasks for Cooling Period Reminders

This module contains Celery background tasks for sending cooling period reminder emails.

Author: [System]
Version: 1.0
Last Modified: [2024-12-13]
"""

from app.celery.celery_config import celery_app
from app.database_layer.db_config import SessionLocal
from app.database_layer.db_model import Candidates, CandidateJobs, CandidateJobStatus, User
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
            .distinct()
            .all()
        )
        
        logger.info(f"Found {len(joined_candidates_data)} joined candidates")
        
        # Group candidates by assigned_to user
        user_candidates = defaultdict(list)
        seen_candidates = set()  # Track unique candidates per user
        
        for row in joined_candidates_data:
            remaining_days = None
            if row.cooling_period_closed:
                remaining_days = (row.cooling_period_closed - today).days
                if remaining_days < 0:
                    remaining_days = 0
            
            candidate_key = (row.assigned_to, row.candidate_id)
            
            # Only add if not already seen for this user
            if candidate_key not in seen_candidates:
                seen_candidates.add(candidate_key)
                
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
