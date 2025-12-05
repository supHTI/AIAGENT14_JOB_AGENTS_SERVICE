from pydantic import BaseModel
from typing import Dict, Any

class JobAgentResponse(BaseModel):
    success: bool = True
    data: Dict[str, Any]
    metadata: Dict[str, Any]