"""
Dimension Mapping Module

This module provides dimension mapping for different social media platforms.
Maps user input to actual dimensions for various platforms.

Author: [Supriyo Chowdhury]
Version: 1.0
Last Modified: [2024-12-19]
"""

# Dimension mapping dictionary
DIMENSION_MAP = {
    "1": {
        "name": "Instagram",
        "width": 1080,
        "height": 1080,
        "description": "Instagram Square Post"
    },
    "instagram": {
        "name": "Instagram",
        "width": 1080,
        "height": 1080,
        "description": "Instagram Square Post"
    },
    "2": {
        "name": "Instagram Story",
        "width": 1080,
        "height": 1920,
        "description": "Instagram Story"
    },
    "instagram_story": {
        "name": "Instagram Story",
        "width": 1080,
        "height": 1920,
        "description": "Instagram Story"
    },
    "3": {
        "name": "Facebook",
        "width": 1200,
        "height": 630,
        "description": "Facebook Post"
    },
    "facebook": {
        "name": "Facebook",
        "width": 1200,
        "height": 630,
        "description": "Facebook Post"
    },
    "4": {
        "name": "LinkedIn",
        "width": 1200,
        "height": 627,
        "description": "LinkedIn Post"
    },
    "linkedin": {
        "name": "LinkedIn",
        "width": 1200,
        "height": 627,
        "description": "LinkedIn Post"
    },
    "5": {
        "name": "Twitter",
        "width": 1200,
        "height": 675,
        "description": "Twitter Post"
    },
    "twitter": {
        "name": "Twitter",
        "width": 1200,
        "height": 675,
        "description": "Twitter Post"
    },
    "6": {
        "name": "LinkedIn Carousel",
        "width": 1080,
        "height": 1080,
        "description": "LinkedIn Carousel"
    },
    "linkedin_carousel": {
        "name": "LinkedIn Carousel",
        "width": 1080,
        "height": 1080,
        "description": "LinkedIn Carousel"
    }
}

def get_dimension(dimension_input: str) -> dict:
    """
    Get dimension details based on user input.
    
    Args:
        dimension_input (str): User input for dimension (e.g., "1", "instagram", "Instagram")
    
    Returns:
        dict: Dimension details with name, width, height, and description
    """
    # Normalize input
    dimension_input = dimension_input.lower().strip()
    
    # Check if input exists in mapping
    if dimension_input in DIMENSION_MAP:
        return DIMENSION_MAP[dimension_input]
    
    # Try to find by name
    for key, value in DIMENSION_MAP.items():
        if value["name"].lower() == dimension_input:
            return value
    
    # Default to Instagram if not found
    return DIMENSION_MAP["1"]

def get_all_dimensions() -> list:
    """
    Get all available dimensions.
    
    Returns:
        list: List of all dimension options
    """
    # Return unique dimensions (avoid duplicates from numeric and string keys)
    seen = set()
    dimensions = []
    for key, value in DIMENSION_MAP.items():
        if isinstance(key, str) and not key.isdigit():
            if value["name"] not in seen:
                seen.add(value["name"])
                dimensions.append({
                    "id": key,
                    "name": value["name"],
                    "width": value["width"],
                    "height": value["height"],
                    "description": value["description"]
                })
    return dimensions

