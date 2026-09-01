# utils/helpers.py
"""Helper functions for the scraper framework"""

import time
import json
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path
import hashlib


def generate_session_name(scraper_name: str, partition: str = "default") -> str:
    """Generate a unique session name"""
    timestamp = int(time.time())
    return f"scraper_{partition}_{scraper_name}_{timestamp}"


def calculate_next_run(schedule: str, last_run: Optional[str] = None) -> Optional[str]:
    """
    Calculate next run time based on schedule
    
    Args:
        schedule: Cron expression or keyword ('daily', 'hourly', etc.)
        last_run: ISO format timestamp of last run
    """
    if not last_run:
        last_time = datetime.now()
    else:
        try:
            last_time = datetime.fromisoformat(last_run)
        except:
            last_time = datetime.now()
    
    # Handle common schedule keywords
    if schedule == 'daily':
        next_time = last_time + timedelta(days=1)
    elif schedule == 'hourly':
        next_time = last_time + timedelta(hours=1)
    elif schedule == 'weekly':
        next_time = last_time + timedelta(weeks=1)
    elif schedule == 'monthly':
        # Approximate monthly
        next_time = last_time + timedelta(days=30)
    else:
        # Cron-like scheduling (simplified)
        # For full cron support, use croniter library
        if '*/' in schedule and 'hour' in schedule:
            # Simple parsing for common patterns
            interval = schedule.split('/')[1].split()[0]
            if interval.isdigit():
                hours = int(interval)
                next_time = last_time + timedelta(hours=hours)
            else:
                next_time = None
        else:
            next_time = None
    
    return next_time.isoformat() if next_time else None


def format_duration(seconds: float) -> str:
    """Format duration in a human-readable way"""
    if seconds < 60:
        return f"{seconds:.2f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.2f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.2f}h"


def save_json_file(data: Any, filepath: str, indent: int = 2):
    """Save data to a JSON file"""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, 'w') as f:
        json.dump(data, f, indent=indent, default=str)


def load_json_file(filepath: str) -> Optional[Any]:
    """Load data from a JSON file"""
    path = Path(filepath)
    if not path.exists():
        return None
    
    with open(path, 'r') as f:
        return json.load(f)


def generate_hash(data: Any) -> str:
    """Generate a hash for data"""
    json_str = json.dumps(data, sort_keys=True, default=str)
    return hashlib.md5(json_str.encode()).hexdigest()[:8]


def safe_get(data: Dict, path: str, default=None):
    """Safely get a value from a nested dictionary using dot notation"""
    keys = path.split('.')
    current = data
    
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    
    return current


def truncate_string(text: str, max_length: int = 100) -> str:
    """Truncate a string to a maximum length"""
    if not text:
        return ''
    if len(text) <= max_length:
        return text
    return text[:max_length] + '...'


def is_retryable_error(error: str) -> bool:
    """Determine if an error is retryable"""
    retryable_errors = [
        'timeout',
        'connection',
        'network',
        'unreachable',
        'retry',
        'temporary'
    ]
    
    error_lower = error.lower()
    return any(keyword in error_lower for keyword in retryable_errors)
