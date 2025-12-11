"""
Job Post Planning Prompt Template

This module contains prompt templates for planning job post structure
using Gemini AI.

Author: [Supriyo Chowdhury]
Version: 1.0
Last Modified: [2024-12-19]
"""

JOB_POST_PLANNING_PROMPT = """You are an expert job post designer and strategist. Your task is to analyze the job details and create a comprehensive plan for a professional job posting.

Job Details:
- Job Title: {job_title}
- Company: {company_name}
- Location: {location}
- Job Type: {job_type}
- Work Mode: {work_mode}
- Experience: {min_exp} - {max_exp} years
- Salary: {salary_info}
- Additional Info: {additional_info}
- Design Type: {type}
- Dimension: {width}x{height} pixels ({dimension_name})

Instructions: {instructions}

Based on the job details above, create a comprehensive plan for the job post. Return ONLY a valid JSON object with the following structure:

{{
    "image_prompt": "A detailed description of what image should be generated. This should be specific and professional. Examples: 'A professional person in business attire working at a modern office desk', 'A diverse team collaborating in a tech startup environment', 'A healthcare professional in a hospital setting'. The image should be relevant to the job role and industry.",
    "layout": {{
        "logo_placement": "top-left|top-right|top-center|bottom-left|bottom-right|bottom-center|center",
        "logo_size": "small|medium|large",
        "company_name_placement": "next_to_logo|below_logo|separate|integrated",
        "company_name_size": "small|medium|large",
        "image_placement": "left|right|top|bottom|center|background|split|overlay",
        "image_size": "small|medium|large|full",
        "hiring_text": "We Are Hiring|Join Our Team|Career Opportunity|Now Hiring|Open Position",
        "hiring_text_placement": "top|center|bottom|badge|banner",
        "hiring_text_style": "bold|italic|badge|banner|highlight",
        "location_icon_style": "svg|emoji|custom",
        "content_layout": "vertical|horizontal|grid|card|hero|split",
        "text_alignment": "left|center|right|justify",
        "orientation": "portrait|landscape|square",
        "sections": [
            {{
                "name": "header",
                "position": "top",
                "elements": ["logo", "company_name", "hiring_text"],
                "height_percentage": 15
            }},
            {{
                "name": "main_content",
                "position": "center",
                "elements": ["job_title", "location_with_icon", "key_details", "image"],
                "height_percentage": 60
            }},
            {{
                "name": "footer",
                "position": "bottom",
                "elements": ["cta", "contact_info", "social_media"],
                "height_percentage": 25
            }}
        ]
    }},
    "show_details": {{
        "job_title": true,
        "company_name": true,
        "location": true,
        "job_type": true,
        "work_mode": true,
        "experience": true,
        "salary": {show_salary},
        "contact_details": {show_contact}
    }},
    "social_media": ["linkedin", "facebook", "twitter", "instagram", "whatsapp"],
    "color_template": {{
        "primary": "#hex_color",
        "secondary": "#hex_color",
        "accent": "#hex_color",
        "background": "#hex_color",
        "text": "#hex_color",
        "description": "Brief description of the color scheme and why it fits the job"
    }},
    "hero_ui": true|false
}}

Important guidelines:
1. image_prompt: Be specific about the image. Consider the job role, industry, and what would appeal to the target candidates. Think about professional settings, diverse representation, and modern work environments.
2. layout: Design a layout that makes sense for the dimension ({width}x{height}). Consider where the logo and generated image should be placed for maximum visual impact.
3. show_details: Only show essential information. Don't overcrowd the post. If salary_info is false, set salary to false. If contact_details is not provided, set contact_details to false.
4. social_media: Select 2-4 relevant social media platforms that make sense for this job posting.
5. color_template: Choose colors that match the design type ({type}) and are professional yet appealing.
6. hero_ui: Decide if a hero-style layout (large image/visual at top) would work well for this dimension and job type.

Return ONLY the JSON object, no explanations or markdown formatting.
"""

def get_job_post_planning_prompt(
    job_title: str,
    company_name: str,
    location: str,
    job_type: str,
    work_mode: str,
    skills_required: str,
    min_exp: float,
    max_exp: float,
    salary_info: str,
    deadline: str,
    additional_info: str,
    type: str,
    dimension_name: str,
    width: int,
    height: int,
    instructions: str,
    show_salary: bool = True,
    show_contact: bool = False
) -> str:
    """
    Generate the job post planning prompt.
    
    Args:
        job_title: Job title
        company_name: Company name
        location: Job location
        job_type: Type of job
        work_mode: Work mode (ONSITE, REMOTE, HYBRID)
        skills_required: Required skills
        min_exp: Minimum experience
        max_exp: Maximum experience
        salary_info: Salary information
        deadline: Application deadline
        additional_info: Additional information
        type: Design type (corporate, creative, minimal, vibrant, tech, professional)
        dimension_name: Dimension name (Instagram, Facebook, etc.)
        width: Width in pixels
        height: Height in pixels
        instructions: User instructions
        show_salary: Whether to show salary
        show_contact: Whether to show contact details
    
    Returns:
        str: Formatted prompt string
    """
    return JOB_POST_PLANNING_PROMPT.format(
        job_title=job_title or "Not specified",
        company_name=company_name or "Not specified",
        location=location or "Not specified",
        job_type=job_type or "Not specified",
        work_mode=work_mode or "Not specified",
        skills_required=skills_required or "Not specified",
        min_exp=min_exp or 0,
        max_exp=max_exp or 0,
        salary_info=salary_info or "Not specified",
        deadline=deadline or "Not specified",
        additional_info=additional_info or "",
        type=type or "professional",
        dimension_name=dimension_name or "Instagram",
        width=width,
        height=height,
        instructions=instructions or "Create an attractive and professional job posting.",
        show_salary="true" if show_salary else "false",
        show_contact="true" if show_contact else "false"
    )

