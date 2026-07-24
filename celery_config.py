from celery import Celery
import os
from datetime import timedelta

# Redis configuration
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

# Create Celery app
app = Celery(
    'chrome_manager',
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['chrome_tasks']  # Tasks are in this file
)

# Celery configuration
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Kolkata',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3000,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    result_expires=86400,  # Results expire after 24 hours
    
    # Queue definitions
    task_queues={
        'chrome': {
            'exchange': 'chrome',
            'routing_key': 'chrome',
        },
        'default': {
            'exchange': 'default',
            'routing_key': 'default',
        },
    },
    
    # Task routing
    task_routes={
        'chrome_tasks.*': {'queue': 'chrome'},
    },
    
    # Beat schedule for periodic tasks
    beat_schedule={
        'health-check-every-5-minutes': {
            'task': 'chrome_tasks.scheduled_health_check',
            'schedule': timedelta(minutes=5),
            'options': {'queue': 'chrome'}
        },
        'deepseek-message-every-hour': {
            'task': 'chrome_tasks.scheduled_deepseek_message',
            'schedule': timedelta(hours=1),
            'options': {'queue': 'chrome'}
        },
    }
)

if __name__ == '__main__':
    app.start()
