#!/data/data/com.termux/files/usr/bin/bash
# Fix git pull after manual SCP deploy — backs up DB, resets to GitHub main
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "=== termux-agent upgrade ==="

if [ ! -d .git ]; then
    echo "Not a git repo. Cloning fresh..."
    cd ..
    mv chrome-launcher "chrome-launcher.bak.$(date +%s)" 2>/dev/null || true
    git clone https://github.com/Theos04/termux-agent.git chrome-launcher
    cd chrome-launcher
fi

# Backup agent database
if [ -f agent.db ]; then
    cp agent.db "agent.db.bak.$(date +%s)"
    echo "Backed up agent.db"
fi

echo "Fetching latest from GitHub..."
git fetch origin main

echo "Removing SCP-overlaid files that block merge..."
rm -rf agent api handlers
rm -f run_agent.py setup_termux.sh requirements.txt README.md
rm -f install_termux.sh start_agent.sh stop_agent.sh 2>/dev/null || true

git reset --hard origin/main
git pull origin main

pip install -q -r requirements.txt 2>/dev/null || pip install -r requirements.txt
chmod +x setup_termux.sh install_termux.sh start_agent.sh stop_agent.sh 2>/dev/null || true

echo ""
echo "=== Upgrade complete ==="
echo "Version: $(git log -1 --oneline)"
echo ""
echo "Start agent:"
echo "  python run_agent.py run --api --workers 1"
echo ""
echo "Test CDP (second terminal):"
echo '  python run_agent.py submit session_start -p '"'"'{"name":"unstop","url":"https://unstop.com/internships"}'"'"
echo '  python run_agent.py submit browser_get_content -p '"'"'{"name":"unstop","format":"text"}'"'"
