# schedulers/celery_beat.py
"""Celery Beat schedule configuration for multi-partition scraping"""

from celery.schedules import crontab
from celery_config import app

# Base schedules
SCHEDULES = {
    # Health checks
    'health_check_all_partitions': {
        'task': 'health_check_all',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
        'args': (),
    },
    
    # Maintenance
    'daily_maintenance': {
        'task': 'run_maintenance',
        'schedule': crontab(minute=0, hour=2),  # Daily at 2 AM
        'args': ('default',),
    },
    
    # Partition-specific scrapers
    'default_partition_scrapers': {
        'task': 'run_partition_scrapers',
        'schedule': crontab(minute=0, hour='*/6'),  # Every 6 hours
        'args': ('default',),
    },
    
    'production_partition_scrapers': {
        'task': 'run_partition_scrapers',
        'schedule': crontab(minute=0, hour='*/4'),  # Every 4 hours
        'args': ('production',),
    },
    
    'staging_partition_scrapers': {
        'task': 'run_partition_scrapers',
        'schedule': crontab(minute=0, hour='*/12'),  # Every 12 hours
        'args': ('staging',),
    },
    
    # Customer-specific
    'customer_a_scrapers': {
        'task': 'run_partition_scrapers',
        'schedule': crontab(minute=0, hour='*/8'),  # Every 8 hours
        'args': ('customer_a',),
    },
    
    'customer_b_scrapers': {
        'task': 'run_partition_scrapers',
        'schedule': crontab(minute=0, hour='*/12'),  # Every 12 hours
        'args': ('customer_b',),
    },
}

def setup_beat_schedule(active_partitions: list = None):
    """
    Setup Celery Beat schedule with active partitions
    
    Args:
        active_partitions: List of partitions to include. If None, include all.
    """
    if active_partitions is None:
        # Include all partitions that have scrapers
        from core.registry import ScraperRegistry
        registry = ScraperRegistry()
        active_partitions = list(registry.get_all_partitions())
    
    schedule = {}
    
    # Add health checks always
    schedule['health_check_all_partitions'] = SCHEDULES['health_check_all_partitions']
    
    # Add maintenance always
    schedule['daily_maintenance'] = SCHEDULES['daily_maintenance']
    
    # Add partitions
    for partition in active_partitions:
        schedule[f'{partition}_partition_scrapers'] = {
            'task': 'run_partition_scrapers',
            'schedule': get_partition_schedule(partition),
            'args': (partition,),
        }
    
    # Update app.conf.beat_schedule
    app.conf.beat_schedule = schedule
    
    return schedule


def get_partition_schedule(partition: str):
    """Get schedule for a partition based on its configuration"""
    schedules = {
        'default': crontab(minute=0, hour='*/6'),
        'production': crontab(minute=0, hour='*/4'),
        'staging': crontab(minute=0, hour='*/12'),
        'testing': crontab(minute='*/30'),  # Every 30 minutes
        'customer_a': crontab(minute=0, hour='*/8'),
        'customer_b': crontab(minute=0, hour='*/12'),
    }
    return schedules.get(partition, crontab(minute=0, hour='*/6'))


def print_schedule():
    """Print the current beat schedule"""
    print("\n📋 Celery Beat Schedule")
    print("=" * 50)
    
    for name, config in app.conf.beat_schedule.items():
        schedule = config.get('schedule')
        task = config.get('task')
        args = config.get('args', ())
        
        # Format schedule
        if hasattr(schedule, 'hour'):
            if schedule.hour == '*/6':
                schedule_str = "Every 6 hours"
            elif schedule.hour == '*/4':
                schedule_str = "Every 4 hours"
            elif schedule.hour == '*/8':
                schedule_str = "Every 8 hours"
            elif schedule.hour == '*/12':
                schedule_str = "Every 12 hours"
            elif schedule.minute == '*/30':
                schedule_str = "Every 30 minutes"
            elif schedule.hour == 2:
                schedule_str = "Daily at 2 AM"
            else:
                schedule_str = f"At {schedule.hour}:{schedule.minute}"
        else:
            schedule_str = str(schedule)
        
        print(f"\n📌 {name}")
        print(f"   Task: {task}")
        print(f"   Schedule: {schedule_str}")
        if args:
            print(f"   Args: {args}")
