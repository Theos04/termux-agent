"""Task utilities for non-blocking task execution"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from celery import current_app
from celery.result import GroupResult

logger = logging.getLogger(__name__)


def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    Get the status of a Celery task or task group.
    
    Args:
        task_id: Celery task ID or GroupResult ID
    
    Returns:
        Status dictionary with task information
    """
    from celery.result import AsyncResult, GroupResult
    
    try:
        # Try to get as AsyncResult
        result = AsyncResult(task_id, app=current_app)
        
        if not result.ready():
            return {
                'success': True,
                'task_id': task_id,
                'status': 'pending',
                'ready': False
            }
        
        if result.failed():
            return {
                'success': False,
                'task_id': task_id,
                'status': 'failed',
                'ready': True,
                'error': str(result.result) if result.result else 'Unknown error'
            }
        
        return {
            'success': True,
            'task_id': task_id,
            'status': 'completed' if result.successful() else 'failed',
            'ready': True,
            'result': result.result if result.successful() else None
        }
        
    except Exception as e:
        logger.error(f"Failed to get status for task {task_id}: {e}")
        return {
            'success': False,
            'task_id': task_id,
            'error': str(e),
            'status': 'error'
        }


def get_group_status(group_id: str) -> Dict[str, Any]:
    """
    Get the status of a Celery task group.
    
    Args:
        group_id: GroupResult ID
    
    Returns:
        Status dictionary with group information
    """
    try:
        result = GroupResult.restore(group_id)
        
        if not result:
            return {
                'success': False,
                'error': f'Group {group_id} not found or expired',
                'status': 'not_found'
            }
        
        total = len(result.results)
        completed = result.completed_count()
        failed = len([r for r in result.results if r.failed()])
        pending = total - completed
        
        return {
            'success': True,
            'group_id': group_id,
            'total': total,
            'completed': completed,
            'failed': failed,
            'pending': pending,
            'ready': result.ready(),
            'status': 'completed' if result.ready() else 'running'
        }
        
    except Exception as e:
        logger.error(f"Failed to get status for group {group_id}: {e}")
        return {
            'success': False,
            'group_id': group_id,
            'error': str(e),
            'status': 'error'
        }


def wait_for_group(group_id: str, timeout: int = 3600, poll_interval: int = 5) -> Dict[str, Any]:
    """
    Wait for a task group to complete.
    WARNING: This is blocking - use only for CLI/scripts, not inside Celery tasks.
    
    Args:
        group_id: GroupResult ID
        timeout: Maximum time to wait in seconds
        poll_interval: Polling interval in seconds
    
    Returns:
        Complete results
    """
    import time
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        result = GroupResult.restore(group_id)
        
        if not result:
            return {
                'success': False,
                'error': f'Group {group_id} not found',
                'status': 'not_found'
            }
        
        if result.ready():
            return {
                'success': True,
                'status': 'completed',
                'results': result.get(),
                'total': len(result.results)
            }
        
        time.sleep(poll_interval)
    
    return {
        'success': False,
        'status': 'timeout',
        'error': f'Group {group_id} did not complete within {timeout}s'
    }

