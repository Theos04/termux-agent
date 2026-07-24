#!/bin/bash
# Start all components for Chrome Automation

cd /data/data/com.termux/files/home/automation/chrome-launcher

echo "🚀 Starting Chrome Automation System..."
echo "========================================="

# Check Redis
echo "📡 Checking Redis..."
if ! redis-cli ping > /dev/null 2>&1; then
    echo "Starting Redis..."
    redis-server --daemonize yes
    sleep 2
fi
echo "✅ Redis is running"

# Start Chrome API
echo "🌐 Starting Chrome API..."
pkill -f api.py || true
python api.py > logs/api.log 2>&1 &
sleep 3
echo "✅ API started (http://127.0.0.1:5000)"

# Start Celery Worker
echo "⚙️ Starting Celery Worker..."
pkill -f celery || true
celery -A celery_config worker \
    --loglevel=INFO \
    --concurrency=2 \
    --queues=chrome,default \
    --prefetch-multiplier=1 \
    --max-tasks-per-child=10 \
    --logfile=logs/celery_worker.log \
    --detach
sleep 2
echo "✅ Celery worker started"

# Start Celery Beat
echo "🔄 Starting Celery Beat..."
celery -A celery_config beat \
    --loglevel=INFO \
    --schedule=celerybeat-schedule \
    --logfile=logs/celery_beat.log \
    --detach
sleep 2
echo "✅ Celery Beat started"

# Start Flower (optional)
echo "🌸 Starting Flower monitoring..."
pkill -f flower || true
celery -A celery_config flower --port=5555 > logs/flower.log 2>&1 &
sleep 2
echo "✅ Flower started (http://127.0.0.1:5555)"

echo ""
echo "========================================="
echo "✅ ALL COMPONENTS STARTED!"
echo "========================================="
echo ""
echo "📋 Services:"
echo "  API:        http://127.0.0.1:5000"
echo "  Flower:     http://127.0.0.1:5555"
echo ""
echo "📁 Logs:"
echo "  Worker:     logs/celery_worker.log"
echo "  Beat:       logs/celery_beat.log"
echo "  API:        logs/api.log"
echo "  Tasks:      logs/task_outputs/"
echo ""
echo "🚀 Run scheduler: python chrome_scheduler.py"
