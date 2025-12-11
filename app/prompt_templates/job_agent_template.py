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
            input_variables=["resume_data", "jd_text"],
            template="""
You are an Expert Resume Parser AI. Extract structured information from the provided resume data.

Resume Data:
{resume_data}

Job Description (for context):
{jd_text}

Task:
Extract all relevant information from the resume and structure it in JSON format.

Instructions:
1. Carefully read the resume data and extract all personal and professional details
2. Extract contact information (name, email, phone, location)
3. Extract all technical and soft skills mentioned
4. Calculate total years of experience
5. Extract education details with institution, degree, year
6. Extract work experience with company, role, duration, responsibilities
7. Extract certifications if mentioned
8. Extract languages known
9. Create a brief professional summary

Output Format:
Return ONLY a valid JSON object in this exact structure:
{{
    "candidate_name": "Full name of the candidate",
    "email": "Email address",
    "phone": "Phone number",
    "location": "Current location/city",
    "skills": ["skill1", "skill2", "skill3"],
    "experience_years": 5.5,
    "education": [
        {{
            "degree": "Degree name",
            "institution": "Institution name",
            "year": "Year of completion",
            "grade": "CGPA/Percentage"
        }}
    ],
    "work_experience": [
        {{
            "title": "Job title",
            "company": "Company name",
            "duration": "Duration (e.g., Jan 2020 - Dec 2023)",
            "responsibilities": ["responsibility1", "responsibility2"]
        }}
    ],
    "certifications": ["certification1", "certification2"],
    "languages": ["language1", "language2"]
}}

Critical Rules:
- Return ONLY the JSON object
- Do NOT include ```json or ``` or any markdown formatting
- Do NOT add any explanatory text before or after the JSON
- Use null for missing information
- Ensure valid JSON syntax
"""
        )


job_agent_template = JobAgentPrompt()