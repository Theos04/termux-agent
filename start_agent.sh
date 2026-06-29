#!/data/data/com.termux/files/usr/bin/bash
# Start termux-agent in background with wake lock
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

mkdir -p "$ROOT/logs"

# Acquire wake lock so Termux stays alive
termux-wake-lock 2>/dev/null || true

# Stop existing instance
if [ -f "$ROOT/.agent.pid" ]; then
    OLD_PID=$(cat "$ROOT/.agent.pid")
    kill "$OLD_PID" 2>/dev/null || true
    rm -f "$ROOT/.agent.pid"
fi

nohup python run_agent.py run --api --workers 3 \
    > "$ROOT/logs/agent.log" 2>&1 &

echo $! > "$ROOT/.agent.pid"
echo "Agent started (PID $(cat "$ROOT/.agent.pid"))"
echo "Log: $ROOT/logs/agent.log"
echo "Dashboard: http://localhost:9227/"
