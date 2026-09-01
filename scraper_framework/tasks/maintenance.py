"""Maintenance tasks for the scraper framework"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
import shutil

from celery import group, chord
from celery_config import app as celery_app
from scraper_framework.core.registry import ScraperRegistry

logger = logging.getLogger(__name__)


@celery_app.task(name='cleanup_old_results', queue='maintenance')
def cleanup_old_results(partition: str = "default", days_to_keep: int = 30):
    """
    Clean up old scraper results
    """
    from storage.partition_manager import PartitionStorageManager

    manager = PartitionStorageManager()
    storage = manager.get_storage(partition)

    # Get all results
    results = storage.get_results()

    # Calculate cutoff date
    cutoff = (datetime.now() - timedelta(days=days_to_keep)).isoformat()

    # Filter old results
    old_results = [r for r in results if r.get('timestamp', '') < cutoff]

    logger.info(f"Found {len(old_results)} old results to clean up")

    # TODO: Implement actual cleanup based on storage backend
    return {
        'partition': partition,
        'days_to_keep': days_to_keep,
        'old_count': len(old_results),
        'status': 'cleanup not implemented for this storage backend'
    }


@celery_app.task(name='cleanup_screenshots', queue='maintenance')
def cleanup_screenshots(days_to_keep: int = 7, screenshot_dir: str = "screenshots"):
    """
    Clean up old screenshot files
    """
    screenshot_path = Path(screenshot_dir)
    if not screenshot_path.exists():
        return {'status': 'screenshot directory not found'}

    cutoff = datetime.now() - timedelta(days=days_to_keep)
    deleted = 0
    total_size = 0

    for file in screenshot_path.glob("*.png"):
        mtime = datetime.fromtimestamp(file.stat().st_mtime)
        if mtime < cutoff:
            size = file.stat().st_size
            total_size += size
            file.unlink()
            deleted += 1

    logger.info(f"✅ Cleaned up {deleted} old screenshots ({total_size/1024/1024:.2f} MB)")

    return {
        'deleted': deleted,
        'total_size_mb': total_size / 1024 / 1024,
        'days_to_keep': days_to_keep
    }


@celery_app.task(name='cleanup_html_files', queue='maintenance')
def cleanup_html_files(days_to_keep: int = 7, html_dir: str = "html"):
    """
    Clean up old HTML files
    """
    html_path = Path(html_dir)
    if not html_path.exists():
        return {'status': 'HTML directory not found'}

    cutoff = datetime.now() - timedelta(days=days_to_keep)
    deleted = 0
    total_size = 0

    for file in html_path.glob("*.html"):
        mtime = datetime.fromtimestamp(file.stat().st_mtime)
        if mtime < cutoff:
            size = file.stat().st_size
            total_size += size
            file.unlink()
            deleted += 1

    logger.info(f"✅ Cleaned up {deleted} old HTML files ({total_size/1024/1024:.2f} MB)")

    return {
        'deleted': deleted,
        'total_size_mb': total_size / 1024 / 1024,
        'days_to_keep': days_to_keep
    }


@celery_app.task(name='run_maintenance', queue='maintenance')
def run_maintenance(partition: str = "default"):
    """
    Run all maintenance tasks for a partition - NON-BLOCKING version.
    Returns a task ID for polling results.
    """
    logger.info(f"🔄 Starting maintenance for partition '{partition}'")
    
    # Create a group of maintenance tasks
    maintenance_tasks = [
        cleanup_old_results.s(partition),
        cleanup_screenshots.s(),
        cleanup_html_files.s()
    ]
    
    # Execute in parallel - no blocking .get()
    job = group(maintenance_tasks)
    result = job.apply_async()
    
    logger.info(f"✅ Submitted maintenance tasks for partition '{partition}'")
    logger.info(f"   Task Group ID: {result.id}")
    
    return {
        'success': True,
        'partition': partition,
        'timestamp': datetime.now().isoformat(),
        'group_id': result.id,
        'status': 'submitted',
        'message': f'Maintenance tasks submitted. Poll /api/tasks/{result.id} for results.'
    }


@celery_app.task(name='run_maintenance_sync', queue='maintenance')
def run_maintenance_sync(partition: str = "default"):
    """
    Run all maintenance tasks for a partition - SYNCHRONOUS version.
    WARNING: Only use for debugging. For production, use run_maintenance().
    """
    results = {
        'partition': partition,
        'timestamp': datetime.now().isoformat(),
        'tasks': {}
    }

    # Call tasks directly instead of .delay().get()
    results['tasks']['cleanup_old_results'] = cleanup_old_results(partition)
    results['tasks']['cleanup_screenshots'] = cleanup_screenshots()
    results['tasks']['cleanup_html_files'] = cleanup_html_files()

    logger.info(f"✅ Maintenance completed for partition '{partition}'")
    return results
