"""
Job Agent Prompt Template

This module contains the prompt template for extracting structured
information from resume data using AI.
"""

from langchain_core.prompts import PromptTemplate


class JobAgentPrompt:
    def __init__(self):
        pass

    def get_template(self):
        """
        Returns a prompt template for extracting structured resume information.
        """
        return PromptTemplate(
            input_variables=["jd_text"],
            template="""
            You are an Expert at extracting job details from a job description.

            Job Description:
            {jd_text}

            Task:
            Extract all relevant information from the job description and structure it in JSON format.

            Output Format:
            {{
            "title": "",
            "location": "",
            "deadline": "",
            "job_type": "",
            "remote": "",
            "openings": "",
            "work_mode": "",
            "salary_type": "",
            "currency": "",
            "min_salary": "",
            "max_salary": "",
            "skills_required": "",
            "min_exp": "",
            "max_exp": "",
            "min_age": "",
            "max_age": "",
            "education_qualification": "",
            "educational_specialization": "",
            "gender_preference": "",
            "communication": "",
            "cooling_period": "",
            "bulk": ""
            }}

            Field Specifications:
            - title: Job Title (max 150 characters). Extract the complete job title.
            - location: Entire location text (max 150 characters). Include full address or location details.
            - deadline: Date in format YYYY-MM-DD only. If not mentioned, leave blank.
            - job_type: Must be one of: "Part-Time", "Full-Time", "Contract", "Freelancing". Leave blank if not specified.
            - remote: Integer value 0 or 1. 1 if remote work is mentioned, 0 otherwise. Leave blank if unclear.
            - openings: Integer value representing number of job openings. Leave blank if not mentioned.
            - work_mode: Must be one of: "Onsite", "Remote", "Hybrid". Leave blank if not specified.
            - salary_type: Must be one of: "Monthly", "Weekly", "Daily", "Yearly". Leave blank if not specified.
            - currency: Currency code only (3 characters, e.g., "USD", "EUR", "INR"). Leave blank if not mentioned.
            - min_salary: Minimum salary as decimal number. Leave blank if not mentioned.
            - max_salary: Maximum salary as decimal number. Leave blank if not mentioned.
            - skills_required: Comma separated values of all skills mentioned. Leave blank if not mentioned.
            - min_exp: Minimum experience in years as decimal (e.g., 2.5). Leave blank if not mentioned.
            - max_exp: Maximum experience in years as decimal (e.g., 5.0). Leave blank if not mentioned.
            - min_age: Minimum age as integer. Leave blank if not mentioned.
            - max_age: Maximum age as integer. Leave blank if not mentioned.
            - education_qualification: Education qualification required (max 120 characters). Leave blank if not mentioned.
            - educational_specialization: Educational specialization or field of study (max 120 characters). Leave blank if not mentioned.
            - gender_preference: Must be one of: "Male", "Female", "Transgender", "No Gender Preference". Leave blank if not specified.
            - communication: Integer value 0 or 1. 1 if communication skills are required, 0 otherwise. Leave blank if unclear.
            - cooling_period: Cooling or Clawback Period in years as decimal (e.g., 1.5). Leave blank if not mentioned.
            - bulk: Integer value 0 or 1. 1 if bulk hiring is mentioned, 0 otherwise. Leave blank if unclear.

            Critical Rules:
            - Return ONLY the JSON object
            - Do NOT include ```json or ``` or any markdown formatting
            - Do NOT add any explanatory text before or after the JSON
            - Use null or empty string "" for missing information (prefer null for numeric fields, "" for text fields)
            - Ensure valid JSON syntax
            - For numeric fields (remote, openings, min_salary, max_salary, min_exp, max_exp, min_age, max_age, communication, cooling_period, bulk), use null if not available, not empty string
            - For text fields, use "" (empty string) if not available
            - Do not skip or miss any field. If not present keep it blank.
            """
        )


job_agent_template = JobAgentPrompt()