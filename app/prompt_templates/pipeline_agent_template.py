# # app/prompt_templates/pipeline_agent_template.py
# from langchain_core.prompts import PromptTemplate


# class PipelineAgentPrompt:
#     def get_template(self):
#         return PromptTemplate(
#             input_variables=["jd_text"],
#             template="""
# You are an expert in Job hiring workflows or Pipeline.

# Job Description:
# {jd_text}

# Task:
# Extract pipeline and interview process information.

# Rules:
# 1. If pipeline name, interview stages, remarks, or colors are explicitly mentioned:
#    - Extract them exactly.

# 2. If any information is missing:
#    - Auto-create it using ATS best practices.

# Pipeline Guidelines:
# - pipeline_name: infer from the job title if not explicitly mentioned.

# Interview Stage Rules:
# - interview_stages MUST be ordered
# - Each stage MUST contain statuses
# - Each stage MUST contain a color_code

# Status Rules (IMPORTANT):
# - Statuses MUST be decided dynamically by the LLM based on:
#   - Job role
#   - Stage purpose
#   - Seniority level
# - Status flows MUST be realistic for ATS workflows
# - Each status MUST contain:
#   - status_name
#   - description
#   - color_code

# Color Rules (CRITICAL):
# - If color is mentioned in the JD, use it exactly
# - If color is NOT mentioned:
#   → ALWAYS use SKY BLUE color
#   → HEX code MUST be: #E3F2FD

# - Color codes MUST be:
#   - Valid HEX values (e.g. #E3F2FD)
#   - Soft / pastel
#   - Suitable for ATS dashboards
#   - The color code should resemble the meaning of the stage/status.
# - NEVER return empty string for color_code

# Return ONLY valid JSON in this exact format:

# {{
#   "pipeline_name": "",
#   "remarks": "",
#   "interview_stages": [
#     {{
#       "stage_order": 1,
#       "stage_name": "",
#       "description": "",
#       "color_code": "",
#       "statuses": [
#         {{
#           "status_name": "",
#           "description": "",
#           "color_code": ""
#         }}
#       ]
#     }}
#   ]
# }}

# Critical Rules:
# - ALWAYS return valid JSON
# - NO markdown
# - NO explanation
# - NO comments
# """
#         )


# pipeline_agent_template = PipelineAgentPrompt()



from langchain_core.prompts import PromptTemplate


class PipelineAgentPrompt:
    def get_template(self):
        return PromptTemplate(
            input_variables=["jd_text"],
            template="""
You are an expert in Job hiring workflows and ATS pipeline design.

Job Description:
{jd_text}

Task:
Extract pipeline and interview process information.

Rules:
1. If pipeline name, interview stages, remarks, or colors are explicitly mentioned:
   - Extract them exactly.

2. If any information is missing:
   - Auto-create it using ATS best practices.

Pipeline Guidelines:
- pipeline_name: infer from the job title if not explicitly mentioned.

Interview Stage Rules:
- interview_stages MUST be ordered
- Each stage MUST contain statuses
- Each stage MUST contain a color_code

Status Rules (IMPORTANT):
- Statuses MUST be decided dynamically based on:
  - Job role
  - Stage purpose
  - Seniority level
- Status flows MUST be realistic for ATS workflows
- Each status MUST contain:
  - status_name
  - description
  - color_code
  - tag

Tag Rules (CRITICAL):
- Each status MUST have exactly ONE tag
- Tag MUST be chosen ONLY from:
  - Sourcing
  - Screening
  - Line Ups
  - Turn Ups
  - Selected
  - Offer Released
  - Offer Accepted

Color Rules (CRITICAL):
- If color is mentioned in the JD:
  → Use it EXACTLY as mentioned
- If color is NOT mentioned:
  → ALWAYS use SKY BLUE (#E3F2FD)
- NEVER return empty color_code

Return ONLY valid JSON in this exact format:

{{
  "pipeline_name": "",
  "remarks": "",
  "interview_stages": [
    {{
      "stage_order": 1,
      "stage_name": "",
      "description": "",
      "color_code": "",
      "statuses": [
        {{
          "status_name": "",
          "description": "",
          "color_code": "",
          "tag": ""
        }}
      ]
    }}
  ]
}}

Critical Rules:
- ALWAYS return valid JSON
- NO markdown
- NO explanation
- NO comments
"""
        )


pipeline_agent_template = PipelineAgentPrompt()
