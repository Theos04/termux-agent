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

| Type | Script | Description |
|------|--------|-------------|
| `fetch_page` | fetch_page.py | Fetch page content |
| `fetch_page2` | fetch_page2.py | Enhanced page fetch |
| `fetch_page_llm` | fetch_page_llm.py | LLM-ready page content |
| `fetch_page_job_read_more` | fetch_page_job_read_more.py | Job detail scraper |
| `launch_chrome` | launch-chrome.py | Start Chrome with CDP |
| `run_js` | run-js-any-chrome.py | Execute JS in Chrome |
| `dynamic_js` | dynamic_chrome_executor.py | Dynamic JS executor |
| `unstop_list` | get-list-unstop.py | Unstop job/hackathon lists |
| `web_scrape` | web_scraper_unstop.py | Unstop web scraper |
| `cdp` | cdpv116.py, cdp_*.py | Any CDP script |
| `discovery` | — | Periodic multi-source fetch |
| `fix_devtools` | fix_devtools.py | Repair DevTools connection |
| `shell` | any | Run arbitrary script |
| `echo` | — | Health check |

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
