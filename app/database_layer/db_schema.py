from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime



class JobAgentResponse(BaseModel):
    success: bool = True
    data: Dict[str, Any]
    metadata: Dict[str, Any]
    
    
class TaskLogsCreate(BaseModel):
    task_id: str
    type: str
    key_id: Optional[int] = None
    status: Optional[str] = None
    error: Optional[str] = None

# ---------------------------------------------------------
# BASE SCHEMA
# ---------------------------------------------------------

class NotificationUserBase(BaseModel):
    user_id: int = Field(..., description="User ID to receive notifications")
    created_by: int = Field(..., description="User ID who created this entry")


# ---------------------------------------------------------
# CREATE SCHEMA
# ---------------------------------------------------------

class NotificationUserCreate(NotificationUserBase):
    pass


# ---------------------------------------------------------
# RESPONSE / READ SCHEMA
# ---------------------------------------------------------

class NotificationUserResponse(NotificationUserBase):
    id: int
    created_at: datetime

    model_config = {
        "from_attributes": True  # Required for SQLAlchemy ORM
    }