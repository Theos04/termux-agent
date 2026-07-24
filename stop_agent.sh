#!/data/data/com.termux/files/usr/bin/bash
# Stop background agent
ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ -f "$ROOT/.agent.pid" ]; then
    kill "$(cat "$ROOT/.agent.pid")" 2>/dev/null || true
    rm -f "$ROOT/.agent.pid"
    echo "Agent stopped"
else
    echo "No agent PID file found"
fi

termux-wake-unlock 2>/dev/null || true
