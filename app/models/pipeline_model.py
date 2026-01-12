# app/models/pipeline_model.py
import json
import logging
from fastapi import HTTPException
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core import settings
from app.prompt_templates.pipeline_agent_template import pipeline_agent_template

logger = logging.getLogger("app_logger")


class PipelineAgent:

    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model=settings.GOOGLE_MODEL_NAME,
            temperature=0.1,
            google_api_key=settings.GOOGLE_API_KEY
        )

    def extract_pipeline_data(self, jd_text: str) -> dict:
        try:
            prompt = pipeline_agent_template.get_template()
            chain = prompt | self.llm

            output = chain.invoke({"jd_text": jd_text})
            result_text = output.content.strip()

            return json.loads(result_text)

        except json.JSONDecodeError:
            logger.error("Invalid JSON from Pipeline Agent")
            raise HTTPException(500, "Failed to parse pipeline JSON")
        except Exception as e:
            raise HTTPException(500, str(e))


pipeline_agent = PipelineAgent()
