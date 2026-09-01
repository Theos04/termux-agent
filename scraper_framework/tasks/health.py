"""Health check tasks for scrapers"""

import logging
from datetime import datetime
from typing import Dict, List

from celery import group, chord
from celery_config import app as celery_app
from scraper_framework.core.registry import ScraperRegistry
from scraper_framework.core.engine import ScraperEngine

logger = logging.getLogger(__name__)


@celery_app.task(name='health_check_partition', queue='chrome')
def health_check_partition(partition: str = "default"):
    """
    Check health of all scrapers in a partition
    """
    registry = ScraperRegistry()
    scrapers = registry.get_all_scrapers(partition)

    health_status = {
        'partition': partition,
        'timestamp': datetime.now().isoformat(),
        'total_scrapers': len(scrapers),
        'scrapers': []
    }

    for name, config in scrapers.items():
        status = {
            'name': name,
            'active': config.active,
            'last_run': config.last_run,
            'run_count': config.run_count,
            'success_count': config.success_count,
            'error_count': config.error_count,
            'healthy': True
        }

        # Check if scraper has been running successfully
        if config.run_count > 0:
            success_rate = config.success_count / config.run_count
            if success_rate < 0.5:  # Less than 50% success rate
                status['healthy'] = False
                status['warning'] = f"Low success rate: {success_rate*100:.1f}%"

        health_status['scrapers'].append(status)

    logger.info(f"✅ Health check completed for partition '{partition}'")
    return health_status


@celery_app.task(name='health_check_all', queue='chrome')
def health_check_all():
    """
    Check health of all partitions - NON-BLOCKING version.
    Returns a task ID for polling results.
    """
    registry = ScraperRegistry()
    partitions = list(registry.get_all_partitions())
    
    if not partitions:
        return {
            'success': True,
            'message': 'No partitions found',
            'partitions': 0,
            'status': 'completed'
        }
    
    # Create a group of health check tasks
    health_tasks = [
        health_check_partition.s(partition)
        for partition in partitions
    ]
    
    # Execute in parallel - no blocking .get()
    job = group(health_tasks)
    result = job.apply_async()
    
    logger.info(f"✅ Submitted health checks for {len(partitions)} partitions")
    logger.info(f"   Task Group ID: {result.id}")
    
    return {
        'success': True,
        'timestamp': datetime.now().isoformat(),
        'partitions': len(partitions),
        'group_id': result.id,
        'status': 'submitted',
        'message': f'Health checks submitted. Poll /api/tasks/{result.id} for results.'
    }


@celery_app.task(name='health_check_all_sync', queue='chrome')
def health_check_all_sync():
    """
    Check health of all partitions - SYNCHRONOUS version.
    WARNING: Only use for small deployments or debugging.
    For production, use health_check_all() which is non-blocking.
    """
    registry = ScraperRegistry()
    partitions = registry.get_all_partitions()

    results = {}
    for partition in partitions:
        # Call directly instead of .delay().get()
        results[partition] = health_check_partition(partition)

    return {
        'success': True,
        'timestamp': datetime.now().isoformat(),
        'partitions': len(partitions),
        'results': results
    }


@celery_app.task(name='recover_failed_scrapers', queue='chrome')
def recover_failed_scrapers(partition: str = "default", max_failures: int = 3):
    """
    Attempt to recover failed scrapers
    """
    registry = ScraperRegistry()
    scrapers = registry.get_all_scrapers(partition)

    recovered = []
    failed = []

    for name, config in scrapers.items():
        if config.error_count >= max_failures:
            logger.warning(f"⚠️ Scraper {name} has {config.error_count} failures, attempting recovery")

            try:
                # Reset error count and reactivate
                config.error_count = 0
                config.active = True
                registry.add_scraper(config, partition)
                recovered.append(name)
                logger.info(f"✅ Recovered scraper: {name}")
            except Exception as e:
                logger.error(f"❌ Failed to recover {name}: {e}")
                failed.append(name)

    return {
        'partition': partition,
        'recovered': recovered,
        'failed': failed
    }
