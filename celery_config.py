# celery_config.py
"""Celery configuration for the scraper framework"""

from celery import Celery
from celery.schedules import crontab
import os
from datetime import timedelta

# Redis configuration
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

# Create Celery app - include ALL task modules
app = Celery(
    'scraper_framework',
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        'scraper_framework.tasks.scrapers',
        'scraper_framework.tasks.health',
        'scraper_framework.tasks.maintenance',
        'chrome_tasks',              # Original chrome tasks
        'chrome_tasks_enhanced',     # Enhanced chrome tasks
    ]
)

# Configure Celery
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    result_expires=86400,  # 24 hours
    
    # Queue definitions
    task_queues={
        'chrome': {
            'exchange': 'chrome',
            'routing_key': 'chrome',
        },
        'maintenance': {
            'exchange': 'maintenance',
            'routing_key': 'maintenance',
        },
        'default': {
            'exchange': 'default',
            'routing_key': 'default',
        },
    },
    
    # Task routing - route ALL tasks
    task_routes={
        'scraper_framework.tasks.scrapers.*': {'queue': 'chrome'},
        'scraper_framework.tasks.health.*': {'queue': 'chrome'},
        'scraper_framework.tasks.maintenance.*': {'queue': 'maintenance'},
        'chrome_tasks.*': {'queue': 'chrome'},           # Original chrome tasks
        'chrome_tasks_enhanced.*': {'queue': 'chrome'},  # Enhanced chrome tasks
    }
)

# Beat schedule for periodic tasks
app.conf.beat_schedule = {
    # Health checks
    'health_check_all_partitions': {
        'task': 'scraper_framework.tasks.health.health_check_all',
        'schedule': crontab(minute='*/15'),
    },
    
    # Daily maintenance
    'daily_maintenance': {
        'task': 'scraper_framework.tasks.maintenance.run_maintenance',
        'schedule': crontab(minute=0, hour=2),
        'args': ('default',),
    },
    
    # Partition scrapers - Default partition every 6 hours
    'default_partition_scrapers': {
        'task': 'scraper_framework.tasks.scrapers.run_partition_scrapers',
        'schedule': crontab(minute=0, hour='*/6'),
        'args': ('default',),
    },
    
    # Production partition every 4 hours
    'production_partition_scrapers': {
        'task': 'scraper_framework.tasks.scrapers.run_partition_scrapers',
        'schedule': crontab(minute=0, hour='*/4'),
        'args': ('production',),
    },
    
    # Staging partition every 12 hours
    'staging_partition_scrapers': {
        'task': 'scraper_framework.tasks.scrapers.run_partition_scrapers',
        'schedule': crontab(minute=0, hour='*/12'),
        'args': ('staging',),
    },
    
    # Chrome task health check every 5 minutes
    'health-check-every-5-minutes': {
        'task': 'chrome_tasks.scheduled_health_check',
        'schedule': timedelta(minutes=5),
        'options': {'queue': 'chrome'}
    },
    
    # Deepseek message every hour
    'deepseek-message-every-hour': {
        'task': 'chrome_tasks.scheduled_deepseek_message',
        'schedule': timedelta(hours=1),
        'options': {'queue': 'chrome'}
    },
}

if __name__ == '__main__':
    app.start()
