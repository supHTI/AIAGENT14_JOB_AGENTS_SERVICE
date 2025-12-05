"""
HTML Generation Prompt Template

This module contains prompt templates for generating HTML job posts
using Gemini AI.

Author: [Supriyo Chowdhury]
Version: 1.0
Last Modified: [2024-12-19]
"""

import json

HTML_GENERATION_PROMPT = """
You are an expert web designer and content creator specializing in creating beautiful, 
professional job posting HTML designs for social media platforms.

Task: Create a complete, standalone HTML document for a job posting that will be displayed 
on {dimension_name} ({width}x{height} pixels).

Job Details:
- Job Title: {job_title}
- Company: {company_name}
- Location: {location}
- Job Type: {job_type}
- Work Mode: {work_mode}
- Skills Required: {skills_required}
- Experience: {min_exp} - {max_exp} years
- Salary: {salary_info}
- Deadline: {deadline}
- Additional Info: {additional_info}

Design Requirements:
- Dimension: {width}x{height} pixels (exact)
- Type: {type} (corporate, creative, minimal, vibrant, tech, professional)
- Language: {language}
- Logo URL: {logo_url}
- Image URLs: {image_urls}
- Call to Action: {cta_required}

Instructions:
{instructions}

Design Guidelines - CRITICAL REQUIREMENTS:

1. Company Logo and Name (MANDATORY):
   - If logo_url is provided: Display the company logo prominently and professionally
   - Logo should be properly sized (not too large, not too small) and placed according to layout plan
   - Company name MUST be displayed clearly and prominently, preferably near the logo
   - Use appropriate font size and weight for company name to ensure visibility
   - Logo and company name should work together as a cohesive brand element

2. Location Display (MANDATORY):
   - Location MUST be displayed with a location icon
   - Use SVG location icon (pin/marker icon) or Unicode location emoji (📍) 
   - Location icon and text should be visually connected
   - Example: "📍 New York, USA" or use SVG: <svg>...</svg> New York, USA
   - Make location easily readable and visually appealing

3. "We Are Hiring" or Similar Text (MANDATORY):
   - Include engaging hiring text such as:
     * "We Are Hiring!"
     * "Join Our Team"
     * "Career Opportunity"
     * "Now Hiring"
     * Or similar dynamic, engaging text
   - This text should be prominent and eye-catching
   - Use appropriate styling (bold, larger font, accent color)
   - Position it strategically (top, center, or as a badge/banner)

4. Image Placement (CRITICAL):
   - If image_urls are provided, place them strategically according to the layout plan
   - Images should complement, not overpower the content
   - Use proper image sizing, borders, shadows, or overlays for professional look
   - Images should be properly aligned and spaced
   - Consider using image overlays or text overlays on images if appropriate
   - Ensure images don't cover important text or information

5. Color Scheme:
   - Choose an appropriate color scheme based on the type:
     * Corporate: Professional blues, grays, whites
     * Creative: Vibrant colors, gradients, modern palettes
     * Minimal: Clean, simple, lots of white space
     * Vibrant: Bold, energetic colors
     * Tech: Modern, sleek, tech-inspired colors
     * Professional: Classic, trustworthy colors
   - Use colors from the planning agent's color_template if provided

6. Typography:
   - Use modern, readable web fonts (Google Fonts recommended)
   - Ensure good contrast and readability
   - Use font hierarchy (headings, body, captions)
   - Job title should be prominent and eye-catching
   - Company name should be clearly visible

7. Layout and Spacing:
   - Make it visually appealing and professional
   - Ensure all important information is visible and well-organized
   - Use proper spacing, padding, and margins
   - Follow the layout structure from planning agent if provided
   - Use CSS Grid or Flexbox for proper alignment
   - Ensure elements don't overlap inappropriately

8. Interactive Elements:
   - If cta_required is true, include a prominent, attractive call-to-action button
   - Button should be eye-catching and encourage action
   - Use appropriate colors and styling (hover effects if possible)
   - Social media icons should be included if specified in planning

9. Content Presentation:
   - Present job information clearly and attractively
   - Use the specified language for all text
   - Make it engaging and professional
   - Use icons or visual elements for different information types (job type, work mode, experience, etc.)
   - Consider using badges, cards, or sections to organize information

Output Requirements - STRICT:
- Return ONLY the complete HTML code
- Include all CSS inline or in <style> tag
- Make it a standalone HTML document (include <!DOCTYPE html>, <html>, <head>, <body>)
- Ensure the HTML is valid and can be rendered directly
- The HTML container/body MUST be exactly {width}x{height} pixels with overflow: hidden
- Use modern HTML5 and CSS3
- Include SVG icons for location and other elements (don't rely on external icon libraries)
- Use proper viewport and ensure content fits within {width}x{height} dimensions
- All elements must be properly aligned and contained within the specified dimensions
- Use absolute positioning or flexbox/grid for precise element placement
- Do not include any explanations, comments, or markdown formatting - just pure HTML

CRITICAL: The HTML must be designed to convert perfectly to PDF and images while maintaining:
- Exact dimensions: {width}x{height} pixels
- Proper orientation (portrait if height > width, landscape if width > height)
- All text readable and properly aligned
- All images properly placed and sized
- Company logo, name, location icon, and "We Are Hiring" text all visible and well-positioned

Generate the HTML now:
"""

def get_html_generation_prompt(
    dimension_name: str,
    width: int,
    height: int,
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
    language: str,
    logo_url: str,
    image_urls: list,
    cta_required: bool,
    instructions: str,
    contact_details: str = "",
    job_post_plan: dict = None
) -> str:
    """
    Generate the HTML generation prompt with all parameters filled in.
    
    Returns:
        str: Formatted prompt string
    """
    image_urls_str = ", ".join(image_urls) if image_urls else "None"
    cta_text = "Yes" if cta_required else "No"
    
    # Enhance instructions with planning agent output
    enhanced_instructions = instructions or "Create an attractive and professional job posting."
    if job_post_plan:
        layout = job_post_plan.get('layout', {})
        color_template = job_post_plan.get('color_template', {})
        show_details = job_post_plan.get('show_details', {})
        
        plan_info = f"""
        
PLANNING AGENT OUTPUT - FOLLOW THESE SPECIFICATIONS EXACTLY:

LAYOUT STRUCTURE:
- Logo Placement: {layout.get('logo_placement', 'top-left')}
- Logo Size: {layout.get('logo_size', 'medium')}
- Company Name Placement: {layout.get('company_name_placement', 'next_to_logo')}
- Company Name Size: {layout.get('company_name_size', 'medium')}
- Image Placement: {layout.get('image_placement', 'center')}
- Image Size: {layout.get('image_size', 'medium')}
- Hiring Text: "{layout.get('hiring_text', 'We Are Hiring')}"
- Hiring Text Placement: {layout.get('hiring_text_placement', 'top')}
- Hiring Text Style: {layout.get('hiring_text_style', 'bold')}
- Location Icon Style: {layout.get('location_icon_style', 'svg')}
- Content Layout: {layout.get('content_layout', 'vertical')}
- Text Alignment: {layout.get('text_alignment', 'left')}
- Orientation: {layout.get('orientation', 'portrait' if height > width else 'landscape')}
- Sections: {json.dumps(layout.get('sections', []), indent=2)}

COLOR TEMPLATE (USE THESE COLORS):
- Primary: {color_template.get('primary', '#000000')}
- Secondary: {color_template.get('secondary', '#FFFFFF')}
- Accent: {color_template.get('accent', '#007BFF')}
- Background: {color_template.get('background', '#FFFFFF')}
- Text: {color_template.get('text', '#000000')}
- Description: {color_template.get('description', '')}

SHOW DETAILS CONFIGURATION:
{json.dumps(show_details, indent=2)}

SOCIAL MEDIA ICONS: {', '.join(job_post_plan.get('social_media', []))}

HERO UI: {'Yes - Use hero-style layout with large visual/image at top' if job_post_plan.get('hero_ui', False) else 'No - Use standard layout'}

CRITICAL REQUIREMENTS:
1. Company logo MUST be placed at: {layout.get('logo_placement', 'top-left')} with size: {layout.get('logo_size', 'medium')}
2. Company name MUST be displayed with placement: {layout.get('company_name_placement', 'next_to_logo')} and size: {layout.get('company_name_size', 'medium')}
3. Location MUST include an icon (use {layout.get('location_icon_style', 'svg')} style) - example: "📍 {location or 'Location'}"
4. Hiring text MUST be: "{layout.get('hiring_text', 'We Are Hiring')}" placed at: {layout.get('hiring_text_placement', 'top')} with style: {layout.get('hiring_text_style', 'bold')}
5. Image (if provided) MUST be placed at: {layout.get('image_placement', 'center')} with size: {layout.get('image_size', 'medium')}
6. Use the exact colors from the color template above
7. Follow the section structure and height percentages from the layout
8. Ensure all elements are properly aligned and contained within {width}x{height} pixels

{enhanced_instructions}
"""
        enhanced_instructions = plan_info
    
    # Add contact details if provided
    if contact_details:
        enhanced_instructions += f"\n\nContact Details to include: {contact_details}"
    
    return HTML_GENERATION_PROMPT.format(
        dimension_name=dimension_name,
        width=width,
        height=height,
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
        language=language or "English",
        logo_url=logo_url or "None",
        image_urls=image_urls_str,
        cta_required=cta_text,
        instructions=enhanced_instructions
    )

