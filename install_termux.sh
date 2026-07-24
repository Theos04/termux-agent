#!/data/data/com.termux/files/usr/bin/bash
# Full Termux install for termux-agent
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "=== termux-agent install ==="
echo "Directory: $ROOT"

# Core packages
pkg install -y python python-pip openssh termux-api 2>/dev/null || true
pip install --upgrade pip
pip install flask requests websocket-client rich

echo ""
echo "=== Quick test ==="
python run_agent.py submit echo -p '{"install": true}'

echo ""
echo "=== Install complete ==="
echo ""
echo "Start agent:"
echo "  bash start_agent.sh"
echo ""
echo "Or foreground:"
echo "  python run_agent.py run --api --workers 3"
echo ""
echo "Dashboard: http://localhost:9227/"
