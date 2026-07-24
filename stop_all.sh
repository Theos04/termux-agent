#!/bin/bash
# Stop all components

echo "🛑 Stopping Chrome Automation System..."
echo "========================================="

pkill -f api.py
pkill -f celery
pkill -f flower
pkill -f redis-server

echo "✅ All components stopped"

