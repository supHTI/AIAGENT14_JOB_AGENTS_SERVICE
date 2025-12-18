from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from collections import defaultdict
import logging
from typing import List
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

from app.database_layer.db_config import get_db
from app.database_layer.db_model import (
    Candidates,
    CandidateJobs,
    CandidateJobStatus,
    User,
    NotificationUser,
    Session,
    Role,
)
from app.database_layer.db_schema import (
    NotificationUserCreate,
    NotificationUserResponse,
)
from app.services.emailer import EmailService
from app.celery.tasks.cooling_period_task import send_daily_cooling_period_reminders
from app.core import settings

logger = logging.getLogger("app_logger")

router = APIRouter(prefix="/api", tags=["Cooling Period / Clawback"])
security = HTTPBearer()

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


# Fixing KeyError for 'role' by ensuring the role is fetched from the database

def validate_token(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """
    Validate the authentication token by decoding JWT and getting user information from sessions table.
    """
    token = credentials.credentials
    try:
        # Decode JWT token to get session_id
        decoded_token = jwt.decode(
            token, 
            settings.JWT_SECRET_KEY, 
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": True}
        )

        session_id = decoded_token.get("sub")
        if not session_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing session_id")

        # Query sessions table to get user_id
        session_record = db.query(Session).filter(
            Session.session_id == session_id,
            Session.is_active == True
        ).first()

        if not session_record:
            raise HTTPException(status_code=401, detail="Invalid or expired session")

        # Fetch user and role information
        user = db.query(User).filter(User.id == session_record.user_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        role = db.query(Role).filter(Role.id == user.role_id).first()
        if not role:
            raise HTTPException(status_code=401, detail="Role not found")

        # Get user information
        user_data = {
            "id": user.id,
            "session_id": session_id,
            "role": role.name,
        }

        return user_data

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidSignatureError:
        raise HTTPException(status_code=401, detail="Invalid token signature")
    except jwt.DecodeError:
        raise HTTPException(status_code=401, detail="Token cannot be decoded")
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail="Invalid token or authentication failed"
        )


# ==================================================================
# 1️⃣ METRICS API (UNCHANGED – SAFE)
# ==================================================================
@router.get("/candidate_metrics")
def candidate_metrics(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    user = validate_token(credentials, db)
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
def trigger_daily_cooling_period_reminders(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    user = validate_token(credentials, db)
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


# ==================================================================
# 3️⃣ ADD NOTIFICATION USERS (ADMIN / SUPER ADMIN)
# ==================================================================
@router.post(
    "/notifications/users",
    response_model=List[NotificationUserResponse],
    status_code=status.HTTP_201_CREATED,
)
def add_notification_users(
    payload: dict,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    user_data = validate_token(credentials, db)
    """
    Add admin/superadmin users who should receive manager-level clawback notifications.
    
    Only users with 'admin' or 'super_admin' role can be added.
    Only users with 'admin' or 'super_admin' role can trigger this API.
    
    Request body:
    {
        "user_id": [1, 2, 3]  # List of admin/superadmin user IDs to add
    }
    """
    # Validate current user is admin or super_admin
    if user_data["role"] not in ("Admin", "SuperAdmin"):
        raise HTTPException(status_code=403, detail="Access denied: Only admin or super_admin can trigger this API")

    user_ids = payload.get("user_id")
    if not user_ids or not isinstance(user_ids, list):
        raise HTTPException(status_code=400, detail="user_id must be a list")

    if not user_ids:  # Check for empty list
        raise HTTPException(status_code=400, detail="user_id list cannot be empty")

    created_records = []
    failed_users = []

    for uid in user_ids:
        try:
            # Validate user exists
            user = db.query(User).filter(User.id == uid).first()
            if not user:
                failed_users.append({"user_id": uid, "error": "User not found"})
                continue
            
            # Validate user is admin or super_admin by checking role relationship
            user_role = db.query(Role).filter(Role.id == user.role_id).first()

            if not user_role or user_role.name not in ("Admin", "SuperAdmin"):
                failed_users.append({"user_id": uid, "error": "User must be admin or super_admin"})
                continue
            
            # Check if notification user already exists
            exists = (
                db.query(NotificationUser)
                .filter(NotificationUser.user_id == uid)
                .first()
            )
            if exists:
                failed_users.append({"user_id": uid, "error": "Already in notification list"})
                continue  # Skip duplicates

            # Create notification user
            notification_user = NotificationUser(
                user_id=uid,
                created_by=user_data["id"],
            )
            db.add(notification_user)
            db.flush()
            created_records.append(notification_user)
            
        except Exception as e:
            logger.error(f"Error adding notification user {uid}: {str(e)}", exc_info=True)
            failed_users.append({"user_id": uid, "error": str(e)})
            db.rollback()
            continue

    try:
        db.commit()
        logger.info(f"Notification users added: {[u.user_id for u in created_records]}")
        
        # Log any failed users
        if failed_users:
            logger.warning(f"Some users failed to add: {failed_users}")
        
    except Exception as e:
        logger.error(f"Error committing notification users: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to commit notification users: {str(e)}"
        )

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
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    user = validate_token(credentials, db)
    """
    Remove an admin/superadmin user from clawback notification recipients.
    Only admin or super_admin users can trigger this API.
    """
    # Validate current user is admin or super_admin
    if user["role"] not in  ("Admin", "SuperAdmin"):
        raise HTTPException(status_code=403, detail="Access denied: Only admin or super_admin can trigger this API")

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

