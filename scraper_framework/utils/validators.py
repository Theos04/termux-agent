# utils/validators.py
"""Input validation utilities"""

import re
from typing import Dict, List, Optional
from urllib.parse import urlparse


def validate_url(url: str) -> bool:
    """Validate a URL"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False


def validate_selectors(selectors: Dict[str, str]) -> List[str]:
    """
    Validate CSS selectors
    
    Returns:
        List of invalid selector keys
    """
    invalid = []
    for key, selector in selectors.items():
        # Basic check: selector should not be empty
        if not selector or not selector.strip():
            invalid.append(key)
        # Check for potentially dangerous selectors
        if 'script' in selector.lower():
            invalid.append(key)
    return invalid


def validate_cron_schedule(schedule: str) -> bool:
    """
    Validate a cron schedule expression
    """
    # Basic cron pattern (simplified)
    cron_pattern = r'^(\*|[0-9]+)(\s+(\*|[0-9]+)){4,5}$'
    
    # Check for common schedule keywords
    common_schedules = ['daily', 'hourly', 'weekly', 'monthly']
    
    if schedule in common_schedules:
        return True
    
    if re.match(cron_pattern, schedule):
        return True
    
    return False


def validate_scraper_config(config: Dict) -> List[str]:
    """
    Validate scraper configuration
    
    Returns:
        List of validation errors
    """
    errors = []
    
    # Check required fields
    required = ['name', 'url', 'selectors']
    for field in required:
        if field not in config:
            errors.append(f"Missing required field: {field}")
    
    # Validate URL
    if 'url' in config and not validate_url(config['url']):
        errors.append(f"Invalid URL: {config['url']}")
    
    # Validate selectors
    if 'selectors' in config:
        invalid = validate_selectors(config['selectors'])
        if invalid:
            errors.append(f"Invalid selectors for fields: {', '.join(invalid)}")
    
    # Validate schedule
    if 'schedule' in config and not validate_cron_schedule(config['schedule']):
        errors.append(f"Invalid schedule: {config['schedule']}")
    
    return errors


def sanitize_data(data: Dict) -> Dict:
    """
    Sanitize extracted data
    """
    sanitized = {}
    for key, value in data.items():
        if isinstance(value, str):
            # Remove excess whitespace
            sanitized[key] = ' '.join(value.split())
        elif isinstance(value, list):
            # Sanitize list items
            sanitized[key] = [
                ' '.join(str(item).split()) if isinstance(item, str) else item
                for item in value
            ]
        else:
            sanitized[key] = value
    return sanitized
