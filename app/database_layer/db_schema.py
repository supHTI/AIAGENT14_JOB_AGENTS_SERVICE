from pydantic import BaseModel
from typing import Dict, Any, Optional

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