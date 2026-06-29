# termux-agent

Event-driven Chrome automation agent for **Termux on Android**. Orchestrates CDP scripts, Unstop scrapers, and JS executors with a task queue, worker pool, cron scheduler, and monitoring dashboard.

## Architecture

```
┌─────────────┐     emit      ┌───────────┐
│  Handlers   │──────────────▶│ Event Bus │──▶ subscribers / plugins
│ (plugins)   │               └─────┬─────┘
└──────▲──────┘                     │ persist
       │ execute                    ▼
┌──────┴──────┐  claim    ┌──────────────┐  enqueue   ┌───────────┐
│ Worker Pool │◀──────────│  Task Queue  │◀───────────│ Scheduler │
│  (N workers)│           │ priority +   │            │  (cron)   │
└─────────────┘           │ retry + TTL  │            └───────────┘
                          └──────┬───────┘
                                 ▼
                          agent.db  ◀────  Monitor API :9227
```

### Components

| Component | Description |
|-----------|-------------|
| **Event Bus** | Every action emits events; persisted to SQLite |
| **Task Queue** | Priority scheduling, exponential backoff retry, timeouts |
| **Worker Pool** | Parallel workers, one task each, auto-distribution |
| **Scheduler** | Cron-like future/periodic tasks |
| **Monitoring** | Dashboard, event history, failed task viewer |
| **Plugins** | `register_handler()` / `register_subscriber()` |

## MCP-style CDP tools

The agent uses **direct imports** (`cdpv116`, `fetch_page2`) — no subprocess.

| Task | Description |
|------|-------------|
| `session_start` | Start Chrome session with `name` + `url` |
| `session_stop` | Stop session |
| `session_list` | List sessions |
| `browser_navigate` | Navigate to URL (auto-starts session) |
| `browser_get_content` | Get text/html/links from page |
| `browser_execute_js` | Run JavaScript |
| `browser_click` | Click CSS selector |
| `browser_fill` | Fill input field |
| `browser_extract` | Structured job/page extraction |
| `browser_run_script` | Run scripts-library JS |
| `agent_act` | Multi-step context agent |

List tools: `GET /api/tools`

### Examples

```bash
# Start session + navigate
python run_agent.py submit session_start -p '{"name":"unstop","url":"https://unstop.com/internships"}'

# Fetch page content (starts session if needed)
python run_agent.py submit browser_navigate -p '{"name":"agent","url":"https://example.com"}'
python run_agent.py submit browser_get_content -p '{"name":"agent","format":"text"}'

# MCP context agent — multi-step
python run_agent.py submit agent_act -p '{"context":"unstop_jobs","name":"unstop"}'
python run_agent.py submit agent_act -p '{"context":"fetch_page","url":"https://example.com"}'

# Custom action sequence
python run_agent.py submit agent_act -p '{
  "name": "agent",
  "url": "https://unstop.com/internships",
  "actions": [
    {"type": "navigate"},
    {"type": "get_content", "format": "text"},
    {"type": "extract"}
  ]
}'
```

## Legacy task aliases

| Old task | Maps to |
|----------|---------|
| `fetch_page` | `browser_get_content` |
| `launch_chrome` | `session_start` |
| `run_js` | `browser_execute_js` |
| `unstop_list` | navigate to Unstop internships |
| `discovery` | `agent_act` with `unstop_jobs` context |

## Deploy from Windows

```powershell
cd C:\Users\mailt\Desktop\dashboard-daily\termux-agent

# Full deploy: git push + scp + restart agent
.\deploy.ps1

# Or with options:
.\deploy_to_termux.ps1                    # git push + scp
.\deploy_to_termux.ps1 -Mode git          # GitHub only → Termux git pull
.\deploy_to_termux.ps1 -Mode scp          # SCP hotfix only (1 password prompt)
.\deploy_to_termux.ps1 -Upgrade -Restart  # run upgrade.sh + restart
.\deploy_to_termux.ps1 -Message "fix cdp handlers"
```

Edit `deploy.config.json` to change SSH host/port.

### First-time Termux setup (after git clone)

```bash
cd ~/automation/chrome-launcher
bash upgrade.sh          # if SCP files blocked git pull
python run_agent.py run --api --workers 1
```

## Install on Termux

```bash
git clone https://github.com/Theos04/termux-agent.git
cd termux-agent
bash install_termux.sh
```

Or update existing install at `~/automation/chrome-launcher`:

```bash
cd ~/automation
git clone https://github.com/Theos04/termux-agent.git chrome-launcher
cd chrome-launcher && bash install_termux.sh
```

## Usage

```bash
# Start in background (wake lock + logging)
bash start_agent.sh

# Or foreground with dashboard
python run_agent.py run --api --workers 3

# Stop background agent
bash stop_agent.sh
```

Dashboard: `http://localhost:9227/` (or Tailscale IP from PC)

### Submit tasks

```bash
python run_agent.py submit echo -p '{"test": true}'
python run_agent.py submit launch_chrome -p '{"port": 9222}'
python run_agent.py submit fetch_page -p '{"url": "https://example.com"}'
python run_agent.py submit unstop_list -p '{"port": 9236}'
python run_agent.py submit cdp -p '{"script": "cdpv116.py", "args": []}'
python run_agent.py submit run_js -p '{"js": "document.title", "port": 9222}'
```

### Schedule periodic discovery

```bash
python run_agent.py schedule unstop-discovery discovery "0 0,6,12,18 * * *" \
  -p '{"sources": ["unstop"], "port": 9236}'
```

### Monitor

```bash
python run_agent.py status
python run_agent.py status --task-id 1
python run_agent.py failed
```

## Task types

See **MCP-style CDP tools** section above.

## HTTP API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Live dashboard |
| `/api/dashboard` | GET | Stats + recent events |
| `/api/tasks` | GET/POST | List or submit tasks |
| `/api/tasks/<id>` | GET | Task detail + events |
| `/api/tasks/failed` | GET | Failed tasks |
| `/api/events` | GET | Event history |
| `/api/schedules` | GET/POST | Cron schedules |

Legacy APIs still available: `api-server-9226.py` (port 9226), `api.py`

## Add a plugin

Create `handlers/my_plugin.py`:

```python
from agent.registry import register_handler

def handle_my_task(payload: dict) -> dict:
    return {"done": True}

register_handler("my_task", handle_my_task)
```

Import in `run_agent.py`:

```python
import handlers.my_plugin  # noqa: F401
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_DB_PATH` | `./agent.db` | SQLite database |
| `AGENT_WORKERS` | `3` | Worker count |
| `AGENT_DEFAULT_TIMEOUT` | `300` | Task timeout (seconds) |
| `AGENT_MAX_RETRIES` | `3` | Max retries |
| `AGENT_API_PORT` | `9227` | Monitor API port |
| `CHROME_LAUNCHER_DIR` | repo root | Script directory |

## Project layout

```
termux-agent/
├── agent/              # Core: events, queue, workers, scheduler
├── handlers/           # Task plugins
├── api/                # Monitor API + dashboard
├── scripts-library/    # JS scripts (unstop, reddit, etc.)
├── run_agent.py        # CLI
├── start_agent.sh      # Background daemon
├── install_termux.sh   # One-shot setup
├── cdpv116.py          # CDP session manager
├── fetch_page*.py      # Page fetchers
├── launch-chrome.py    # Chrome launcher
└── api-server-9226.py  # Legacy Flask API
```

## License

MIT
