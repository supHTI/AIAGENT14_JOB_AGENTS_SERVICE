"""
Auth dependencies for report endpoints.
Per requirement, only super_admin and admin roles may access report generation.
Validates tokens via external auth service API.
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import settings
from app.database_layer.db_config import get_db
from app.database_layer.db_model import User

ALLOWED_REPORT_ROLES = {"super_admin", "admin"}

bearer_scheme = HTTPBearer(auto_error=True)


def validate_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Validate JWT token via AUTH_SERVICE_URL and return the User object from DB.
    All authenticated users can access this endpoint, but role-based access control applies.
    """
    token = credentials.credentials
    
    try:
        # Call authentication service
        response = requests.post(
            f"{settings.AUTH_SERVICE_URL}",
            params={"token": token},
            headers={"accept": "application/json"}
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        # Assuming auth service returns JSON with user_id
        user_data = response.json()
        user_id = user_data.get("user_id")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token response")
        
        # Fetch user from DB
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return user
        
    except requests.RequestException:
        raise HTTPException(status_code=503, detail="Authentication service unavailable")


def require_report_admin(
    user: User = Depends(validate_token)
):
    """
    Dependency to enforce that only super_admin or admin can access report endpoints.
    Validates token via auth service and checks user role from database.
    """
    # Get role name from database
    role_name = None
    if user.role and user.role.name:
        role_name = user.role.name.lower()
    
    if role_name not in ALLOWED_REPORT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "errorCode": "FORBIDDEN",
                "message": "You do not have permission to generate reports.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "path": "/reports",
            },
        )
    return user


def get_user_email(
    user: User = Depends(validate_token)
) -> str:
    """
    Get user email from database (not from token).
    The user is already fetched from DB via validate_token which gets user_id from auth service.
    """
    if not user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User email not found in database."
        )
    return user.email

