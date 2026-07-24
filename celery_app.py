# celery_app.py
from celery import Celery

app = Celery(
    'workflow_tasks',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0'
)

app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    task_soft_time_limit=240,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_queue_max_priority=10,
    task_default_queue='default',
    task_default_priority=0,
)

# Auto-discover tasks
app.autodiscover_tasks(['workflow3', 'chrome_tasks'])
