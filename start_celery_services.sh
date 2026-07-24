#!/bin/bash
# start_celery_services.sh

echo "🚀 Starting Celery services..."

# Start Redis (if not already running)
echo "Starting Redis..."
redis-server --daemonize yes

# Start Celery worker
echo "Starting Celery worker..."
celery -A celery_config worker --loglevel=info --concurrency=4 &

# Start Celery beat (scheduler)
echo "Starting Celery beat..."
celery -A celery_config beat --loglevel=info &

# Start Flower (Celery monitoring)
echo "Starting Flower monitoring..."
celery -A celery_config flower --port=5555 &

echo "✅ All services started!"
echo "📊 Flower UI: http://localhost:5555"
echo "📝 Check logs for details"
