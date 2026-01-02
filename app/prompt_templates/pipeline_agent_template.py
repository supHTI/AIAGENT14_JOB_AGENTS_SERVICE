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
                    You are an expert in Job hiring workflows and ATS pipeline design from either Job Description or Email Text.

                    Job Description or Email Text:
                    {jd_text}

                    A Pipeline is a sequence of stages that a candidate goes through during the hiring process.
                    A Stage is a part of a pipeline that a candidate goes through during the hiring process.
                    A Status is a part of a stage that a candidate goes through during the hiring process.
                    
                    Source of Information:
                    The Job Description or Email Text may contain a details of the hiring process,
                    If it contains the pipeline steps or stages, consider them exactly do not add any extra steps or stages.
                    If not then create the pipeline steps or stages based on the Job Description or Email Text.

                    Task:
                    1. Your task is to generate the pipeline and interview process information from the Job Description or Email Text.
                    

                    Pipeline Guidelines:
                    - pipeline_name: A pipeline name basically happens by the job title, or something similar to that.
                    - remarks: The remarks of the pipeline, it can be a short description of the pipeline.

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
                    - Tags are ENUMERATED VALUES, and they are:
                      - Sourcing
                      - Screening
                      - Line Ups
                      - Turn Ups
                      - Selected
                      - Offer Released
                      - Offer Accepted
                    - If any status can resemble any of the tags, then use the tag exactly. Every status will not have a tag.
                    Here the tags means: -
                      - Sourcing: When a candidate is sourced.
                      - Screening: When a candidate is screened.
                      - Line Ups: When a candidate is lined up for an interview.
                      - Turn Ups: When a candidate is turned up for an interview.
                      - Selected: When a candidate is selected.
                      - Offer Released: When a candidate is offered a job.
                      - Offer Accepted: When a candidate accepts the offer.
                    - Its not necessary that all kinds of tags will be there in a pipeline, it should be dynamic based on requirements.
                    - Do not put unnecessary tags or statuses, it should be dynamic based on requirements.
                    

                    Color Rules (CRITICAL):
                    - Generate color Hex Code based on the stage name and status name.
                    - It is mandatory to generate a color Hex Code for each stage and status.

                    Return ONLY valid JSON in this exact format:

                    {{
                      "pipeline_name": "",
                      "remarks": "",
                      "interview_stages": [
                        {{
                          "stage_order": 1, # auto order
                          "stage_name": "",
                          "description": "",
                          "color_code": "",
                          "statuses": [
                            {{
                              "status_name": "",
                              "description": "",
                              "color_code": "",
                              "tag": "",
                              "order": 1  # auto order
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
