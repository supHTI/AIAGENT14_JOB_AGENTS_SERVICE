#pipeline_agent_api.py
from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from typing import Optional
from pydantic import BaseModel
import base64
import logging

from app.celery.tasks.pipeline_agent_tasks import pipeline_agent_task

logger = logging.getLogger("app_logger")

router = APIRouter(tags=["Pipeline Agent"])

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def is_image_file(filename: str) -> bool:
    return any(filename.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)


class PipelineAgentResponse(BaseModel):
    task_id: str
    status: str
    message: str


@router.post("/pipeline_agent", response_model=PipelineAgentResponse)
async def pipeline_agent(
    jd_text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    image_train: Optional[bool] = Form(None),
):
    if (not jd_text or not jd_text.strip()) and not file:
        raise HTTPException(400, "Either jd_text or file must be provided")

    task_data = {}

    if file:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(400, "Uploaded file is empty")

        is_img = is_image_file(file.filename)
        image_train = True if is_img else bool(image_train)

        task_data = {
            "file_content_b64": base64.b64encode(file_bytes).decode(),
            "filename": file.filename,
            "image_train": image_train,
        }
    else:
        task_data = {"jd_text": jd_text}

    task = pipeline_agent_task.delay(task_data)

    return PipelineAgentResponse(
        task_id=task.id,
        status="pending",
        message="Pipeline agent task queued successfully",
    )
