
# from fastapi import APIRouter, Depends
# from sqlalchemy.orm import Session
# from datetime import datetime
# from collections import defaultdict
# import logging
# from app.database_layer.db_config import get_db
# from app.database_layer.db_model import Candidates, CandidateJobs, CandidateJobStatus, User
# from app.services.emailer import EmailService
# from app.celery.tasks.cooling_period_tasks import send_daily_cooling_period_reminders

# logger = logging.getLogger("app_logger")
 
# router = APIRouter()
 
# @router.get("/candidate_metrics")
# def candidate_metrics(db: Session = Depends(get_db)):
#     today = datetime.utcnow()
   
#     # Total candidates
#     total_candidates = db.query(Candidates).count()
#     print("Total candidates:", total_candidates)
   
#     # Candidates with joined status - joined with candidate details
#     joined_candidates_data = (
#         db.query(
#             Candidates.candidate_id,
#             Candidates.candidate_name,
#             Candidates.candidate_email,
#             Candidates.candidate_phone_number,
#             CandidateJobStatus.cooling_period_closed,
#             Candidates.assigned_to,
#         )
#         .join(CandidateJobs, CandidateJobs.candidate_id == Candidates.candidate_id)
#         .join(CandidateJobStatus, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
#         .filter(CandidateJobStatus.type == "JOINED")
#         .all()
#     )
#     print("Joined candidates data:", joined_candidates_data)
   
#     # Group candidates by assigned_to user
#     user_candidates = defaultdict(list)
    
#     result_candidate = []
#     for row in joined_candidates_data:
#         remaining_days = None
#         if row.cooling_period_closed:
#             remaining_days = (row.cooling_period_closed - today).days
#             if remaining_days < 0:
#                 remaining_days = 0
        
#         candidate_info = {
#             "candidate_id": row.candidate_id,
#             "candidate_name": row.candidate_name,
#             "candidate_email": row.candidate_email,
#             "candidate_phone_number": row.candidate_phone_number,
#             "assigned_to": row.assigned_to,
#             "cooling_period_remaining_days": remaining_days,
#         }
        
#         result_candidate.append(candidate_info)
        
#         # Group by assigned_to user
#         if row.assigned_to:
#             user_candidates[row.assigned_to].append(candidate_info)
    
#     # Fetch user details and prepare grouped data
#     grouped_by_user = {}
#     for user_id, candidates in user_candidates.items():
#         user = db.query(User).filter(User.id == user_id).first()
#         if user:
#             grouped_by_user[user.email] = {
#                 "user_id": user_id,
#                 "user_name": user.username,
#                 "user_email": user.email,
#                 "candidates": candidates
#             }
 
#     return {
#         "total_candidates": total_candidates,
#         "joined_candidates": result_candidate,
#         "grouped_by_user": grouped_by_user
#     }

# from app.database_layer.db_model import NotificationUser

# @router.post("/send_cooling_period_reminders")
# def send_cooling_period_reminders(db: Session = Depends(get_db)):
#     """
#     Send cooling period reminder emails to assigned users.
#     Each user gets one email with all their assigned candidates.
#     """
#     try:
#         today = datetime.utcnow()
        
#         # Fetch candidates with joined status
#         joined_candidates_data = (
#             db.query(
#                 Candidates.candidate_id,
#                 Candidates.candidate_name,
#                 Candidates.candidate_email,
#                 Candidates.candidate_phone_number,
#                 CandidateJobStatus.cooling_period_closed,
#                 Candidates.assigned_to,
#             )
#             .join(CandidateJobs, CandidateJobs.candidate_id == Candidates.candidate_id)
#             .join(CandidateJobStatus, CandidateJobStatus.candidate_job_id == CandidateJobs.id)
#             .filter(CandidateJobStatus.type == "JOINED")
#             .distinct()  # Ensure unique candidates
#             .all()
#         )
        
#         # Group candidates by assigned_to user
#         user_candidates = defaultdict(list)
#         seen_candidates = set()  # Track unique candidates per user
        
#         for row in joined_candidates_data:
#             remaining_days = None
#             if row.cooling_period_closed:
#                 remaining_days = (row.cooling_period_closed - today).days
#                 if remaining_days < 0:
#                     remaining_days = 0
            
#             candidate_key = (row.assigned_to, row.candidate_id)
            
#             # Only add if not already seen for this user
#             if candidate_key not in seen_candidates:
#                 seen_candidates.add(candidate_key)
                
#                 candidate_info = {
#                     "candidate_id": row.candidate_id,
#                     "candidate_name": row.candidate_name,
#                     "candidate_email": row.candidate_email,
#                     "candidate_phone_number": row.candidate_phone_number,
#                     "cooling_period_remaining_days": remaining_days,
#                 }
                
#                 if row.assigned_to:
#                     user_candidates[row.assigned_to].append(candidate_info)
        
#         # Send emails to each assigned user
#         email_service = EmailService()
#         email_results = []
        
#         for user_id, candidates in user_candidates.items():
#             # Fetch user details
#             user = db.query(User).filter(User.id == user_id).first()
            
#             if not user or not user.email:
#                 logger.warning(f"User {user_id} not found or has no email. Skipping.")
#                 email_results.append({
#                     "user_id": user_id,
#                     "status": "failed",
#                     "reason": "User not found or no email"
#                 })
#                 continue
            
#             # Send email with all candidates for this user
#             try:
#                 success = email_service.send_cooling_period_reminder(
#                     to_email=user.email,
#                     recipient_name=user.username or "User",
#                     candidates=candidates
#                 )
#                 if success:
#                     logger.info(f"Cooling period reminder email sent to {user.email}")
#                     notification = NotificationUser(
#                     user_id=user_id,
#                     created_by=user_id
#                 )

#                 db.add(notification)
#                 db.commit()

                
#                 email_results.append({
#                     "user_id": user_id,
#                     "user_email": user.email,
#                     "candidate_count": len(candidates),
#                     "status": "sent" if success else "failed",
#                     "candidates": [c["candidate_name"] for c in candidates]
#                 })
                
#                 logger.info(f"Email {'sent' if success else 'failed'} to {user.email} with {len(candidates)} candidate(s)")
                
#             except Exception as e:
#                 logger.error(f"Error sending email to {user.email}: {str(e)}")
#                 email_results.append({
#                     "user_id": user_id,
#                     "user_email": user.email,
#                     "status": "failed",
#                     "reason": str(e)
#                 })
        
#         return {
#             "message": "Cooling period reminder emails processing completed",
#             "total_users_notified": len(email_results),
#             "email_results": email_results,
#             "details": user_candidates
#         }
        
#     except Exception as e:
#         logger.error(f"Error in send_cooling_period_reminders: {str(e)}")
#         return {
#             "message": "Error sending reminders",
#             "error": str(e)
#         }


# @router.post("/trigger_daily_cooling_period_reminders")
# def trigger_daily_cooling_period_reminders():
#     """
#     Manually trigger the daily cooling period reminder email task via Celery.
#     This endpoint queues the task to run in the background.
    
#     Returns:
#         dict: Task ID and status information
#     """
#     try:
#         # Trigger the Celery task
#         task = send_daily_cooling_period_reminders.apply_async()
        
#         return {
#             "message": "Daily cooling period reminder task has been queued",
#             "task_id": task.id,
#             "status": "queued",
#             "note": "The task will be processed by Celery workers. Use the task_id to check status."
#         }
        
#     except Exception as e:
#         logger.error(f"Error triggering daily cooling period reminders: {str(e)}")
#         return {
#             "message": "Error triggering task",
#             "error": str(e)
#         }


# @router.get("/check_cooling_period_task/{task_id}")
# def check_cooling_period_task(task_id: str):
#     """
#     Check the status of a cooling period reminder task.
    
#     Args:
#         task_id: The Celery task ID
    
#     Returns:
#         dict: Task status and result information
#     """
#     try:
#         from celery.result import AsyncResult
#         from app.celery.celery_config import celery_app
        
#         task_result = AsyncResult(task_id, app=celery_app)
        
#         response = {
#             "task_id": task_id,
#             "status": task_result.state,
#             "ready": task_result.ready(),
#             "successful": task_result.successful() if task_result.ready() else None,
#         }
        
#         # Add result if task is completed
#         if task_result.ready():
#             if task_result.successful():
#                 response["result"] = task_result.result
#             else:
#                 response["error"] = str(task_result.info)
        
#         return response
        
#     except Exception as e:
#         logger.error(f"Error checking task status: {str(e)}")
#         return {
#             "task_id": task_id,
#             "error": str(e)
#         }


from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from collections import defaultdict
import logging
from typing import List

from app.database_layer.db_config import get_db
from app.database_layer.db_model import (
    Candidates,
    CandidateJobs,
    CandidateJobStatus,
    User,
    NotificationUser,
)
from app.database_layer.db_schema import (
    NotificationUserCreate,
    NotificationUserResponse,
    NotificationUserCreateRequest
)
from app.services.emailer import EmailService
from app.celery.tasks.cooling_period_task import send_daily_cooling_period_reminders

logger = logging.getLogger("app_logger")

router = APIRouter(prefix="/api", tags=["Cooling Period / Clawback"])
# ------------------------------------------------------------------
# 🔐 PLACEHOLDER: Replace with real auth dependency
# ------------------------------------------------------------------
def get_current_admin_user():
    """
    Placeholder for JWT-based admin authentication.
    Replace with your actual auth dependency.
    """
    return {
        "id": 1,
        "role": "admin",  # admin | super_admin
    }


# ==================================================================
# 1️⃣ METRICS API (UNCHANGED – SAFE)
# ==================================================================
@router.get("/candidate_metrics")
def candidate_metrics(db: Session = Depends(get_db)):
    today = datetime.utcnow()

    total_candidates = db.query(Candidates).count()

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
        .all()
    )

    user_candidates = defaultdict(list)
    result_candidate = []

    for row in joined_candidates_data:
        remaining_days = None
        if row.cooling_period_closed:
            remaining_days = max((row.cooling_period_closed - today).days, 0)

        candidate_info = {
            "candidate_id": row.candidate_id,
            "candidate_name": row.candidate_name,
            "candidate_email": row.candidate_email,
            "candidate_phone_number": row.candidate_phone_number,
            "assigned_to": row.assigned_to,
            "cooling_period_remaining_days": remaining_days,
        }

        result_candidate.append(candidate_info)

        if row.assigned_to:
            user_candidates[row.assigned_to].append(candidate_info)

    grouped_by_user = {}
    for user_id, candidates in user_candidates.items():
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            grouped_by_user[user.email] = {
                "user_id": user_id,
                "user_name": user.username,
                "user_email": user.email,
                "candidates": candidates,
            }

    return {
        "total_candidates": total_candidates,
        "joined_candidates": result_candidate,
        "grouped_by_user": grouped_by_user,
    }


# ==================================================================
# 2️⃣ MANUAL EMAIL TRIGGER (UNCHANGED)
# ==================================================================
@router.post("/trigger_daily_cooling_period_reminders")
def trigger_daily_cooling_period_reminders():
    try:
        task = send_daily_cooling_period_reminders.apply_async()
        return {
            "message": "Daily cooling period reminder task queued",
            "task_id": task.id,
            "status": "queued",
        }
    except Exception as e:
        logger.error(f"Error triggering task: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to trigger task")


# # ==================================================================
# # 3️⃣ ADD NOTIFICATION USERS (ADMIN / SUPER ADMIN)
# # ==================================================================
# @router.post(
#     "/notifications/users",
#     response_model=List[NotificationUserResponse],
#     status_code=status.HTTP_201_CREATED,
# )
# def add_notification_users(
#     payload: dict,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_admin_user),
# ):
#     """
#     Add users who should receive manager-level clawback notifications.
#     """
#     if current_user["role"] not in ("admin", "super_admin"):
#         raise HTTPException(status_code=403, detail="Access denied")

#     user_ids = payload.get("user_id")
#     if not user_ids or not isinstance(user_ids, list):
#         raise HTTPException(status_code=400, detail="user_id must be a list")

#     created_records = []

#     for uid in user_ids:
#         exists = (
#             db.query(NotificationUser)
#             .filter(NotificationUser.user_id == uid)
#             .first()
#         )
#         if exists:
#             continue  # Prevent duplicates

#         notification_user = NotificationUser(
#             user_id=uid,
#             created_by=current_user["id"],
#         )
#         db.add(notification_user)
#         db.flush()
#         created_records.append(notification_user)

#     db.commit()
#     logger.info(f"Notification users added: {user_ids}")

#     return created_records

@router.post(
    "/notifications/users",
    response_model=List[NotificationUserResponse],
    status_code=status.HTTP_201_CREATED,
)
def add_notification_users(
    payload: NotificationUserCreateRequest,   # 👈 FIXED
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user),
):
    if current_user["role"] not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Access denied")

    user_ids = payload.user_id  # 👈 FIXED

    created_records = []

    for uid in user_ids:
        exists = (
            db.query(NotificationUser)
            .filter(NotificationUser.user_id == uid)
            .first()
        )
        if exists:
            continue

        notification_user = NotificationUser(
            user_id=uid,
            created_by=current_user["id"],
        )
        db.add(notification_user)
        db.flush()
        created_records.append(notification_user)

    db.commit()

    logger.info(f"Notification users added: {user_ids}")

    return created_records


# ==================================================================
# 4️⃣ DELETE NOTIFICATION USER (ADMIN / SUPER ADMIN)
# ==================================================================
@router.delete(
    "/notifications/users/{user_id}",
    status_code=status.HTTP_200_OK,
)
def delete_notification_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user),
):
    """
    Remove a user from clawback notification recipients.
    """
    if current_user["role"] not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Access denied")

    notification_user = (
        db.query(NotificationUser)
        .filter(NotificationUser.user_id == user_id)
        .first()
    )

    if not notification_user:
        raise HTTPException(status_code=404, detail="Notification user not found")

    db.delete(notification_user)
    db.commit()

    logger.info(f"Notification user deleted: {user_id}")

    return {
        "message": "Notification user removed successfully",
        "user_id": user_id,
    }

