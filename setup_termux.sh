#!/data/data/com.termux/files/usr/bin/bash
# Quick setup after git pull
set -e
cd "$(dirname "$0")"
pip install -q -r requirements.txt
chmod +x install_termux.sh start_agent.sh stop_agent.sh 2>/dev/null || true
echo "Ready. Run: bash start_agent.sh"
