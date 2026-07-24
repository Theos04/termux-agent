# scheduler_setup.py
from celery.schedules import crontab
from celery_config import app
from chrome_tasks import health_check_all_sessions, periodic_session_restart

# Configure periodic tasks
app.conf.beat_schedule = {
    # Health check every 5 minutes
    'health-check': {
        'task': 'chrome_tasks.health_check_all_sessions',
        'schedule': crontab(minute='*/5'),
    },
    # Periodic restart every 6 hours
    'periodic-restart': {
        'task': 'chrome_tasks.periodic_session_restart',
        'schedule': crontab(minute='0', hour='*/6'),
    },
    # Start specific sessions at specific times
    'start-unstop-morning': {
        'task': 'chrome_tasks.start_chrome_session',
        'schedule': crontab(hour=9, minute=0, day_of_week='mon-fri'),
        'args': (6,),  # Session ID 6
    },
    'start-quora-afternoon': {
        'task': 'chrome_tasks.start_chrome_session',
        'schedule': crontab(hour=14, minute=0),
        'args': (29,),  # Session ID 29
    },
}

if __name__ == '__main__':
    # Start Celery beat
    app.start()
