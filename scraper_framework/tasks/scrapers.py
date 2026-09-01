"""Celery tasks for partition-aware scraping"""

import logging
import time
from typing import Dict, Optional, List

from celery import Task, group, chord
from celery.result import GroupResult
from celery.utils.log import get_task_logger

from celery_config import app as celery_app
from scraper_framework.core.registry import ScraperRegistry
from scraper_framework.core.engine import ScraperEngine
from scraper_framework.core.models import ScraperConfig, ScrapeResult
from scraper_framework.core.exceptions import ScraperNotFoundError

logger = get_task_logger(__name__)


class ScraperTask(Task):
    """Base task for scrapers with partition support"""
    abstract = True

    def __init__(self):
        self.registry = ScraperRegistry()

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"❌ Task {task_id} failed: {exc}")
        logger.error(einfo.traceback)


@celery_app.task(base=ScraperTask, name='run_scheduled_scraper', queue='chrome', bind=True)
def run_scheduled_scraper(self, scraper_name: str, partition: str = "default"):
    """
    Run a single scraper by name from a specific partition
    """
    logger.info(f"📋 Running scheduled scraper: {scraper_name} (partition: {partition})")

    try:
        # Get scraper config
        config = self.registry.get_scraper(scraper_name, partition)
        if not config:
            return {
                'success': False,
                'error': f'Scraper not found: {scraper_name} in partition {partition}',
                'partition': partition,
                'scraper_name': scraper_name
            }

        if not config.active:
            logger.info(f"⏸️ Scraper {scraper_name} is inactive, skipping")
            return {
                'success': False,
                'message': f'Scraper {scraper_name} is inactive',
                'partition': partition,
                'scraper_name': scraper_name,
                'skipped': True
            }

        # Run the scraper directly
        engine = ScraperEngine(partition=partition)
        result = engine.run_scraper(config)

        # Update task state
        self.update_state(
            state='SUCCESS' if result.success else 'FAILURE',
            meta={
                'scraper_name': scraper_name,
                'partition': partition,
                'duration': result.duration,
                'data_count': len(result.data)
            }
        )

        return {
            'success': result.success,
            'scraper_name': scraper_name,
            'partition': partition,
            'timestamp': result.timestamp,
            'duration': result.duration,
            'data_count': len(result.data),
            'error': result.error,
            'task_id': self.request.id
        }

    except Exception as e:
        logger.error(f"❌ Failed to run scraper {scraper_name} in partition {partition}: {e}")
        return {
            'success': False,
            'error': str(e),
            'scraper_name': scraper_name,
            'partition': partition,
            'task_id': self.request.id if hasattr(self, 'request') else None
        }


@celery_app.task(base=ScraperTask, name='run_partition_scrapers_async', queue='chrome')
def run_partition_scrapers_async(partition: str = "default"):
    """
    Run all active scrapers in a partition ASYNCHRONOUSLY.
    Returns a task ID for polling results.
    This is the preferred method for production use.
    """
    logger.info(f"📋 Starting async execution for partition: {partition}")

    try:
        registry = ScraperRegistry()
        scrapers = registry.get_active_scrapers(partition)

        if not scrapers:
            return {
                'success': True,
                'partition': partition,
                'message': 'No active scrapers in partition',
                'total': 0,
                'results': [],
                'status': 'completed'
            }

        # Create a group of scraper tasks
        scraper_tasks = [
            run_scheduled_scraper.s(scraper.name, partition)
            for scraper in scrapers
        ]

        # Execute them in parallel
        job = group(scraper_tasks)
        result = job.apply_async()

        logger.info(f"✅ Submitted {len(scrapers)} scraper tasks for partition {partition}")
        logger.info(f"   Task Group ID: {result.id}")

        return {
            'success': True,
            'partition': partition,
            'total': len(scrapers),
            'group_id': result.id,
            'status': 'submitted',
            'message': f'Submitted {len(scrapers)} scrapers. Poll /api/tasks/{result.id} for results.'
        }

    except Exception as e:
        logger.error(f"❌ Failed to submit partition {partition}: {e}")
        return {
            'success': False,
            'partition': partition,
            'error': str(e),
            'status': 'failed'
        }


@celery_app.task(base=ScraperTask, name='run_partition_scrapers', queue='chrome')
def run_partition_scrapers(partition: str = "default", wait_for_results: bool = False):
    """
    Run all active scrapers in a specific partition.
    
    Args:
        partition: Partition name
        wait_for_results: If True, wait for all tasks to complete before returning.
                         If False, return immediately with group ID.
    
    Returns:
        If wait_for_results=True: Complete results dictionary
        If wait_for_results=False: Task group submission response
    """
    logger.info(f"📋 Running all scrapers in partition: {partition}")

    try:
        registry = ScraperRegistry()
        scrapers = registry.get_active_scrapers(partition)

        if not scrapers:
            return {
                'success': True,
                'partition': partition,
                'message': 'No active scrapers in partition',
                'total': 0,
                'results': []
            }

        # For synchronous execution (legacy/CLI), run sequentially
        if not wait_for_results:
            # Default behavior - run async
            return run_partition_scrapers_async(partition)

        # Wait for results (for CLI --sync mode)
        results = []
        engine = ScraperEngine(partition=partition)

        for scraper in scrapers:
            try:
                result = engine.run_scraper(scraper)
                results.append({
                    'success': result.success,
                    'scraper_name': scraper.name,
                    'duration': result.duration,
                    'error': result.error,
                    'data_count': len(result.data)
                })
                # Small delay between scrapers to avoid overwhelming
                time.sleep(1)
            except Exception as e:
                logger.error(f"❌ Failed to run scraper {scraper.name}: {e}")
                results.append({
                    'success': False,
                    'scraper_name': scraper.name,
                    'error': str(e)
                })

        return {
            'success': True,
            'partition': partition,
            'total': len(scrapers),
            'completed': len([r for r in results if r.get('success')]),
            'failed': len([r for r in results if not r.get('success')]),
            'results': results
        }

    except Exception as e:
        logger.error(f"❌ Failed to run partition {partition}: {e}")
        return {
            'success': False,
            'partition': partition,
            'error': str(e)
        }


@celery_app.task(base=ScraperTask, name='get_partition_results', queue='chrome')
def get_partition_results(group_id: str):
    """
    Get results from a previously submitted partition run.
    
    Args:
        group_id: The group ID returned by run_partition_scrapers_async
    """
    try:
        from celery.result import GroupResult
        result = GroupResult.restore(group_id)
        
        if not result:
            return {
                'success': False,
                'error': f'Group {group_id} not found or expired',
                'status': 'not_found'
            }
        
        if not result.ready():
            return {
                'success': True,
                'status': 'pending',
                'group_id': group_id,
                'completed': result.completed_count(),
                'total': len(result.results)
            }
        
        # Get all results
        results = result.get()
        
        return {
            'success': True,
            'status': 'completed',
            'group_id': group_id,
            'total': len(results),
            'completed': len([r for r in results if r.get('success')]),
            'failed': len([r for r in results if not r.get('success')]),
            'results': results
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get results for group {group_id}: {e}")
        return {
            'success': False,
            'error': str(e),
            'status': 'error'
        }


@celery_app.task(base=ScraperTask, name='run_all_partitions', queue='chrome')
def run_all_partitions(wait_for_results: bool = False):
    """
    Run scrapers across all partitions in parallel.
    """
    logger.info("📋 Running scrapers across all partitions")

    registry = ScraperRegistry()
    partitions = list(registry.get_all_partitions())

    if not wait_for_results:
        # Submit all partitions in parallel
        partition_tasks = [
            run_partition_scrapers_async.s(partition)
            for partition in partitions
        ]
        job = group(partition_tasks)
        result = job.apply_async()
        
        return {
            'success': True,
            'partitions': len(partitions),
            'group_id': result.id,
            'status': 'submitted'
        }

    # Synchronous execution (legacy)
    results = {}
    for partition in partitions:
        try:
            result = run_partition_scrapers(partition, wait_for_results=True)
            results[partition] = result
        except Exception as e:
            logger.error(f"❌ Failed to run partition {partition}: {e}")
            results[partition] = {
                'success': False,
                'partition': partition,
                'error': str(e)
            }

    return {
        'success': True,
        'partitions': len(partitions),
        'results': results
    }


@celery_app.task(base=ScraperTask, name='scrape_specific_url', queue='chrome', bind=True)
def scrape_specific_url(self, url: str, selectors: Dict[str, str],
                        session_name: Optional[str] = None,
                        take_screenshot: bool = True,
                        save_html: bool = True,
                        partition: str = "default",
                        timeout: int = 60):
    """
    Scrape a specific URL with custom selectors
    """
    logger.info(f"📋 Scraping specific URL: {url} (partition: {partition})")

    if not session_name:
        session_name = f"scrape_{int(time.time())}"

    config = ScraperConfig(
        name=f"custom_{session_name}",
        url=url,
        schedule="",
        selectors=selectors,
        take_screenshot=take_screenshot,
        save_html=save_html,
        session_name=session_name,
        partition=partition,
        timeout=timeout
    )

    engine = ScraperEngine(partition=partition)
    result = engine.run_scraper(config)

    return {
        'success': result.success,
        'url': url,
        'partition': partition,
        'data': result.data,
        'screenshot': result.screenshot_path,
        'html': result.html_path,
        'duration': result.duration,
        'error': result.error,
        'task_id': self.request.id  # Fixed: using self.request.id
    }
