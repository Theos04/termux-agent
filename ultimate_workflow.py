#!/usr/bin/env python3
"""
Advanced Workflow Builder - Complete Chrome Automation System
Integrates: CDP Connection, DOM Analysis, Crawling, Scraping, Data Extraction, Loops, Triggers, and Database Storage
"""

import os
import sys
import json
import time
import asyncio
import logging
import hashlib
import uuid
import re
import threading
import subprocess
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict, deque
from urllib.parse import urlparse, urljoin
from contextlib import contextmanager

# ============================================================================
# Dependency Installation
# ============================================================================

def install_dependencies():
    deps = ['requests', 'rich', 'websocket-client', 'beautifulsoup4', 'lxml']
    for dep in deps:
        try:
            __import__(dep.replace('-', '_'))
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", dep])

install_dependencies()

# ============================================================================
# Imports
# ============================================================================

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

try:
    import websocket
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client"])
    import websocket

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.syntax import Syntax
    from rich import box
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.markdown import Markdown
    from rich.tree import Tree
    from rich.columns import Columns
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    console = Console()
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rich"])
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.syntax import Syntax
    from rich import box
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.markdown import Markdown
    from rich.tree import Tree
    from rich.columns import Columns
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    console = Console()

# ============================================================================
# Configuration
# ============================================================================

@dataclass
class WorkflowConfig:
    """Global configuration for the workflow system"""
    base_dir: str = os.path.expanduser("~/chrome-workflows")
    workflows_dir: str = os.path.expanduser("~/chrome-workflows/workflows")
    scripts_dir: str = os.path.expanduser("~/chrome-workflows/scripts")
    data_dir: str = os.path.expanduser("~/chrome-workflows/data")
    results_dir: str = os.path.expanduser("~/chrome-workflows/results")
    logs_dir: str = os.path.expanduser("~/chrome-workflows/logs")
    db_path: str = os.path.expanduser("~/chrome-workflows/workflow.db")
    chrome_port: int = 9222
    api_base_url: str = "http://127.0.0.1:5000"
    default_session: str = "unstop"
    max_retries: int = 3
    timeout_seconds: int = 30
    verbose: bool = True

    def ensure_directories(self):
        """Create all necessary directories"""
        for dir_path in [self.base_dir, self.workflows_dir, self.scripts_dir,
                        self.data_dir, self.results_dir, self.logs_dir]:
            Path(dir_path).mkdir(parents=True, exist_ok=True)

# ============================================================================
# Database Manager
# ============================================================================

class DatabaseManager:
    """SQLite database for storing workflows, scripts, results, and history"""

    def __init__(self, config: WorkflowConfig = None):
        self.config = config or WorkflowConfig()
        self.db_path = Path(self.config.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database schema"""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()

            # Workflows table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    config TEXT,
                    steps TEXT,
                    metadata TEXT,
                    tags TEXT,
                    status TEXT DEFAULT 'draft',
                    version TEXT DEFAULT '1.0.0',
                    created_at TEXT,
                    updated_at TEXT,
                    execution_count INTEGER DEFAULT 0,
                    avg_duration REAL,
                    last_executed TEXT
                )
            """)

            # Scripts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scripts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    workflow_id TEXT,
                    code TEXT NOT NULL,
                    type TEXT DEFAULT 'js',
                    description TEXT,
                    tags TEXT,
                    metadata TEXT,
                    version INTEGER DEFAULT 1,
                    created_at TEXT,
                    updated_at TEXT,
                    execution_count INTEGER DEFAULT 0,
                    avg_duration REAL,
                    FOREIGN KEY (workflow_id) REFERENCES workflows(id)
                )
            """)

            # Script versions (history)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS script_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    script_id TEXT,
                    version INTEGER,
                    code TEXT,
                    metadata TEXT,
                    created_at TEXT,
                    FOREIGN KEY (script_id) REFERENCES scripts(id)
                )
            """)

            # Executions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS executions (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT,
                    workflow_name TEXT,
                    status TEXT,
                    steps_total INTEGER,
                    steps_completed INTEGER,
                    results TEXT,
                    error TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    duration REAL,
                    metadata TEXT,
                    FOREIGN KEY (workflow_id) REFERENCES workflows(id)
                )
            """)

            # Results table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS results (
                    id TEXT PRIMARY KEY,
                    execution_id TEXT,
                    step_id TEXT,
                    step_name TEXT,
                    data TEXT,
                    metadata TEXT,
                    status TEXT,
                    created_at TEXT,
                    FOREIGN KEY (execution_id) REFERENCES executions(id)
                )
            """)

            # Context history
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS context_history (
                    id TEXT PRIMARY KEY,
                    key TEXT,
                    value TEXT,
                    metadata TEXT,
                    created_at TEXT
                )
            """)

            # Crawl data
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS crawl_data (
                    id TEXT PRIMARY KEY,
                    base_url TEXT,
                    urls TEXT,
                    site_map TEXT,
                    metadata TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)

            conn.commit()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ----- Workflow Methods -----

    def save_workflow(self, workflow_data: Dict) -> str:
        workflow_id = workflow_data.get('id', str(uuid.uuid4()))
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO workflows (
                    id, name, description, config, steps, metadata, tags,
                    status, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                workflow_id,
                workflow_data.get('name', ''),
                workflow_data.get('description', ''),
                json.dumps(workflow_data.get('config', {})),
                json.dumps(workflow_data.get('steps', [])),
                json.dumps(workflow_data.get('metadata', {})),
                json.dumps(workflow_data.get('tags', [])),
                workflow_data.get('status', 'draft'),
                workflow_data.get('version', '1.0.0'),
                workflow_data.get('created_at', datetime.now().isoformat()),
                datetime.now().isoformat()
            ))
            conn.commit()
            return workflow_id

    def get_workflow(self, workflow_id: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,))
            row = cursor.fetchone()
            if row:
                result = dict(row)
                result['config'] = json.loads(result['config']) if result['config'] else {}
                result['steps'] = json.loads(result['steps']) if result['steps'] else []
                result['metadata'] = json.loads(result['metadata']) if result['metadata'] else {}
                result['tags'] = json.loads(result['tags']) if result['tags'] else []
                return result
            return None

    def get_workflow_by_name(self, name: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM workflows WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                result = dict(row)
                result['config'] = json.loads(result['config']) if result['config'] else {}
                result['steps'] = json.loads(result['steps']) if result['steps'] else []
                result['metadata'] = json.loads(result['metadata']) if result['metadata'] else {}
                result['tags'] = json.loads(result['tags']) if result['tags'] else []
                return result
            return None

    def list_workflows(self, status: str = None) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT * FROM workflows WHERE status = ? ORDER BY name", (status,))
            else:
                cursor.execute("SELECT * FROM workflows ORDER BY name")
            
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                result['steps'] = json.loads(result['steps']) if result['steps'] else []
                result['tags'] = json.loads(result['tags']) if result['tags'] else []
                results.append(result)
            return results

    def delete_workflow(self, workflow_id: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
            conn.commit()
            return cursor.rowcount > 0

    # ----- Script Methods -----

    def save_script(self, script_data: Dict) -> str:
        script_id = script_data.get('id', str(uuid.uuid4()))
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT version FROM scripts WHERE id = ?", (script_id,))
            existing = cursor.fetchone()
            version = (existing[0] + 1) if existing else 1
            
            cursor.execute("""
                INSERT OR REPLACE INTO scripts (
                    id, name, workflow_id, code, type, description,
                    tags, metadata, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                script_id,
                script_data.get('name', ''),
                script_data.get('workflow_id', ''),
                script_data.get('code', ''),
                script_data.get('type', 'js'),
                script_data.get('description', ''),
                json.dumps(script_data.get('tags', [])),
                json.dumps(script_data.get('metadata', {})),
                version,
                script_data.get('created_at', datetime.now().isoformat()),
                datetime.now().isoformat()
            ))
            
            # Save version history
            cursor.execute("""
                INSERT INTO script_versions (script_id, version, code, metadata, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                script_id, version,
                script_data.get('code', ''),
                json.dumps(script_data.get('metadata', {})),
                datetime.now().isoformat()
            ))
            
            conn.commit()
            return script_id

    def get_script(self, script_id: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scripts WHERE id = ?", (script_id,))
            row = cursor.fetchone()
            if row:
                result = dict(row)
                result['tags'] = json.loads(result['tags']) if result['tags'] else []
                result['metadata'] = json.loads(result['metadata']) if result['metadata'] else []
                return result
            return None

    def list_scripts(self, workflow_id: str = None) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if workflow_id:
                cursor.execute("SELECT * FROM scripts WHERE workflow_id = ? ORDER BY name", (workflow_id,))
            else:
                cursor.execute("SELECT * FROM scripts ORDER BY name")
            
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                result['tags'] = json.loads(result['tags']) if result['tags'] else []
                result['metadata'] = json.loads(result['metadata']) if result['metadata'] else []
                results.append(result)
            return results

    # ----- Execution Methods -----

    def save_execution(self, execution_data: Dict) -> str:
        exec_id = execution_data.get('id', str(uuid.uuid4()))
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO executions (
                    id, workflow_id, workflow_name, status, steps_total,
                    steps_completed, results, error, started_at, completed_at,
                    duration, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                exec_id,
                execution_data.get('workflow_id', ''),
                execution_data.get('workflow_name', ''),
                execution_data.get('status', 'pending'),
                execution_data.get('steps_total', 0),
                execution_data.get('steps_completed', 0),
                json.dumps(execution_data.get('results', [])),
                execution_data.get('error', ''),
                execution_data.get('started_at', datetime.now().isoformat()),
                execution_data.get('completed_at', ''),
                execution_data.get('duration', 0),
                json.dumps(execution_data.get('metadata', {}))
            ))
            conn.commit()
            return exec_id

    def get_executions(self, workflow_id: str = None, limit: int = 20) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if workflow_id:
                cursor.execute("""
                    SELECT * FROM executions WHERE workflow_id = ? 
                    ORDER BY started_at DESC LIMIT ?
                """, (workflow_id, limit))
            else:
                cursor.execute("SELECT * FROM executions ORDER BY started_at DESC LIMIT ?", (limit,))
            
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                result['results'] = json.loads(result['results']) if result['results'] else []
                result['metadata'] = json.loads(result['metadata']) if result['metadata'] else {}
                results.append(result)
            return results

    # ----- Result Methods -----

    def save_result(self, result_data: Dict) -> str:
        result_id = result_data.get('id', str(uuid.uuid4()))
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO results (
                    id, execution_id, step_id, step_name, data, metadata, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result_id,
                result_data.get('execution_id', ''),
                result_data.get('step_id', ''),
                result_data.get('step_name', ''),
                json.dumps(result_data.get('data', {})),
                json.dumps(result_data.get('metadata', {})),
                result_data.get('status', 'completed'),
                datetime.now().isoformat()
            ))
            conn.commit()
            return result_id

    def get_results(self, execution_id: str = None) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if execution_id:
                cursor.execute("SELECT * FROM results WHERE execution_id = ? ORDER BY created_at", (execution_id,))
            else:
                cursor.execute("SELECT * FROM results ORDER BY created_at DESC LIMIT 100")
            
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                result['data'] = json.loads(result['data']) if result['data'] else {}
                result['metadata'] = json.loads(result['metadata']) if result['metadata'] else {}
                results.append(result)
            return results

    # ----- Context Methods -----

    def save_context(self, key: str, value: Any, metadata: Dict = None) -> str:
        context_id = str(uuid.uuid4())
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO context_history (id, key, value, metadata, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                context_id,
                key,
                json.dumps(value, default=str),
                json.dumps(metadata or {}),
                datetime.now().isoformat()
            ))
            conn.commit()
            return context_id

    def get_context_history(self, key: str = None, limit: int = 50) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if key:
                cursor.execute("""
                    SELECT * FROM context_history WHERE key = ? 
                    ORDER BY created_at DESC LIMIT ?
                """, (key, limit))
            else:
                cursor.execute("SELECT * FROM context_history ORDER BY created_at DESC LIMIT ?", (limit,))
            
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                result['value'] = json.loads(result['value']) if result['value'] else None
                result['metadata'] = json.loads(result['metadata']) if result['metadata'] else {}
                results.append(result)
            return results

# ============================================================================
# Chrome Connection Manager
# ============================================================================

class ChromeConnection:
    """Manages Chrome DevTools Protocol connection"""

    def __init__(self, config: WorkflowConfig = None):
        self.config = config or WorkflowConfig()
        self.ws = None
        self.connected = False
        self.page_info = {}
        self._message_id = 0

    def connect(self, port: int = None) -> bool:
        """Connect to Chrome via CDP"""
        port = port or self.config.chrome_port
        
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/json", timeout=5)
            tabs = resp.json()
            
            page_tab = None
            for tab in tabs:
                if tab.get('type') == 'page':
                    page_tab = tab
                    break
            
            if not page_tab:
                console.print("[red]No page found in Chrome[/red]")
                return False
            
            self.page_info = {
                'title': page_tab.get('title', 'Untitled'),
                'url': page_tab.get('url', ''),
                'id': page_tab.get('id', '')
            }
            
            ws_url = page_tab.get('webSocketDebuggerUrl')
            self.ws = websocket.create_connection(ws_url, timeout=10)
            
            # Enable domains
            self._enable_domains()
            
            self.connected = True
            console.print(f"[green]✅ Connected to Chrome: {self.page_info['title']}[/green]")
            console.print(f"[dim]   URL: {self.page_info['url']}[/dim]")
            return True
            
        except requests.exceptions.ConnectionError:
            console.print("[red]❌ Chrome not running on port {port}[/red]")
            console.print("[yellow]Start Chrome with: chrome --remote-debugging-port=9222[/yellow]")
            return False
        except Exception as e:
            console.print(f"[red]Connection failed: {e}[/red]")
            return False

    def _enable_domains(self):
        """Enable CDP domains"""
        domains = [
            "Runtime.enable",
            "DOM.enable", 
            "Page.enable",
            "Network.enable",
            "Performance.enable"
        ]
        
        for i, domain in enumerate(domains, start=1):
            try:
                self.ws.send(json.dumps({"id": i, "method": domain}))
                self.ws.settimeout(2)
                try:
                    self.ws.recv()
                except:
                    pass
            except Exception as e:
                console.print(f"[yellow]Warning: Could not enable {domain}: {e}[/yellow]")

    def execute_js(self, script: str, await_promise: bool = False) -> Any:
        """Execute JavaScript and return result"""
        if not self.connected:
            return None
        
        self._message_id += 1
        cmd_id = self._message_id
        
        try:
            self.ws.send(json.dumps({
                "id": cmd_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": script,
                    "returnByValue": True,
                    "awaitPromise": await_promise
                }
            }))
            
            timeout = self.config.timeout_seconds
            start = time.time()
            
            while time.time() - start < timeout:
                try:
                    self.ws.settimeout(1)
                    resp = self.ws.recv()
                    data = json.loads(resp)
                    if data.get('id') == cmd_id:
                        result = data.get('result', {})
                        if 'result' in result:
                            return result['result'].get('value')
                        elif 'error' in result:
                            console.print(f"[red]JS Error: {result['error']}[/red]")
                            return None
                        return None
                except websocket.WebSocketTimeoutException:
                    continue
                except Exception as e:
                    console.print(f"[red]WebSocket error: {e}[/red]")
                    return None
            
            console.print("[yellow]Timeout waiting for JS response[/yellow]")
            return None
            
        except Exception as e:
            console.print(f"[red]Error executing JS: {e}[/red]")
            return None

    def navigate(self, url: str) -> bool:
        """Navigate to URL"""
        if not self.connected:
            return False
        
        result = self.execute_js(f"window.location.href = '{url}'")
        time.sleep(2)  # Wait for page to load
        return True

    def get_page_content(self) -> Dict:
        """Get comprehensive page content"""
        if not self.connected:
            return {}
        
        script = """
        (function() {
            const data = {
                url: window.location.href,
                title: document.title,
                timestamp: Date.now(),
                headers: [],
                paragraphs: [],
                links: [],
                forms: [],
                images: [],
                meta: {},
                text: document.body.innerText,
                html: document.documentElement.outerHTML
            };
            
            // Headers
            document.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(h => {
                data.headers.push({
                    level: h.tagName.toLowerCase(),
                    text: h.textContent.trim()
                });
            });
            
            // Paragraphs
            document.querySelectorAll('p').forEach(p => {
                const text = p.textContent.trim();
                if (text && text.length > 10) {
                    data.paragraphs.push(text);
                }
            });
            
            // Links
            document.querySelectorAll('a[href]').forEach(a => {
                data.links.push({
                    text: a.textContent.trim() || '',
                    href: a.href
                });
            });
            
            // Forms
            document.querySelectorAll('form').forEach(form => {
                data.forms.push({
                    action: form.action || '',
                    method: form.method || 'GET',
                    inputs: form.querySelectorAll('input, textarea, select').length
                });
            });
            
            // Images
            document.querySelectorAll('img[src]').forEach(img => {
                data.images.push({
                    src: img.src,
                    alt: img.alt || ''
                });
            });
            
            // Meta
            document.querySelectorAll('meta').forEach(meta => {
                const name = meta.getAttribute('name') || meta.getAttribute('property') || '';
                const content = meta.getAttribute('content') || '';
                if (name && content) {
                    data.meta[name] = content;
                }
            });
            
            return data;
        })()
        """
        return self.execute_js(script) or {}

    def close(self):
        """Close WebSocket connection"""
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
        self.connected = False

# ============================================================================
# Core Workflow Engine
# ============================================================================

class WorkflowStepType(Enum):
    """Types of workflow steps"""
    JS = "js"
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    EXTRACT = "extract"
    STORE = "store"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    API_CALL = "api_call"
    ASSERT = "assert"
    LOOP = "loop"
    CONDITIONAL = "conditional"
    TRIGGER = "trigger"
    CRAWL = "crawl"
    SCRAPE = "scrape"
    PARSE = "parse"
    EXPORT = "export"
    NOTIFY = "notify"

@dataclass
class WorkflowStep:
    """Individual workflow step definition"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: str = "js"
    name: str = ""
    description: str = ""
    params: Dict = field(default_factory=dict)
    condition: Optional[str] = None
    continue_on_error: bool = False
    retry_count: int = 0
    retry_delay: int = 1
    timeout: int = 30
    depends_on: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'WorkflowStep':
        return cls(**data)

@dataclass
class Workflow:
    """Complete workflow definition"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    config: Dict = field(default_factory=dict)
    steps: List[Dict] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    status: str = "draft"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    execution_count: int = 0
    avg_duration: Optional[float] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'Workflow':
        return cls(**data)

    def get_display_id(self) -> str:
        return self.id[:8]

# ============================================================================
# Workflow Execution Engine
# ============================================================================

class WorkflowEngine:
    """Executes workflows with full context management"""

    def __init__(self, config: WorkflowConfig = None):
        self.config = config or WorkflowConfig()
        self.db = DatabaseManager(self.config)
        self.chrome = ChromeConnection(self.config)
        self.context = {}
        self.executions = {}
        self._execution_id = None
        self._current_workflow = None
        self._listeners = []
        self.logger = logging.getLogger("WorkflowEngine")

    def connect_chrome(self, port: int = None) -> bool:
        """Connect to Chrome"""
        return self.chrome.connect(port)

    def execute_js(self, script: str, context: Dict = None) -> Any:
        """Execute JavaScript in Chrome"""
        if not self.chrome.connected:
            console.print("[red]Chrome not connected[/red]")
            return None
        
        # Merge context
        ctx = self.context.copy()
        if context:
            ctx.update(context)
        
        # Inject context variables
        if ctx:
            context_js = "\n".join([
                f"const {k} = {json.dumps(v, default=str)};"
                for k, v in ctx.items()
                if not k.startswith('_')
            ])
            full_script = f"""
            (function() {{
                {context_js}
                return (function() {{
                    {script}
                }})();
            }})()
            """
        else:
            full_script = f"""
            (function() {{
                return (function() {{
                    {script}
                }})();
            }})()
            """
        
        return self.chrome.execute_js(full_script)

    def execute_step(self, step: WorkflowStep, context: Dict) -> Dict:
        """Execute a single workflow step"""
        step_type = step.type
        step_name = step.name or f"Step_{step.id}"
        result = {
            'step_id': step.id,
            'step_name': step_name,
            'type': step_type,
            'status': 'running',
            'started_at': datetime.now().isoformat(),
            'result': None,
            'error': None,
            'metadata': {}
        }

        try:
            params = step.params
            retry_count = step.retry_count
            retry_delay = step.retry_delay

            for attempt in range(retry_count + 1):
                try:
                    if step_type == WorkflowStepType.JS.value:
                        code = params.get('code', '')
                        if not code:
                            # Try loading from script library
                            script_id = params.get('script_id')
                            if script_id:
                                script = self.db.get_script(script_id)
                                if script:
                                    code = script.get('code', '')
                        result['result'] = self.execute_js(code, context)
                        result['status'] = 'completed'
                        break

                    elif step_type == WorkflowStepType.NAVIGATE.value:
                        url = params.get('url')
                        if not url:
                            raise ValueError("URL required for navigate")
                        self.chrome.navigate(url)
                        result['result'] = {'url': url, 'status': 'navigated'}
                        result['status'] = 'completed'
                        break

                    elif step_type == WorkflowStepType.CLICK.value:
                        selector = params.get('selector')
                        if not selector:
                            raise ValueError("Selector required for click")
                        script = f"""
                        (function() {{
                            const el = document.querySelector('{selector}');
                            if (el) {{
                                el.click();
                                return {{ success: true, selector: '{selector}' }};
                            }}
                            return {{ success: false, error: 'Element not found' }};
                        }})()
                        """
                        result['result'] = self.execute_js(script, context)
                        result['status'] = 'completed'
                        break

                    elif step_type == WorkflowStepType.FILL.value:
                        selector = params.get('selector')
                        value = params.get('value')
                        if not selector or value is None:
                            raise ValueError("Selector and value required for fill")
                        script = f"""
                        (function() {{
                            const el = document.querySelector('{selector}');
                            if (el) {{
                                el.value = '{value}';
                                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                                return {{ success: true, value: '{value}' }};
                            }}
                            return {{ success: false, error: 'Element not found' }};
                        }})()
                        """
                        result['result'] = self.execute_js(script, context)
                        result['status'] = 'completed'
                        break

                    elif step_type == WorkflowStepType.EXTRACT.value:
                        selector = params.get('selector')
                        attribute = params.get('attribute', 'textContent')
                        var_name = params.get('variable_name')
                        
                        script = f"""
                        (function() {{
                            const el = document.querySelector('{selector}');
                            if (el) {{
                                let value = el.{attribute};
                                if (typeof value === 'string') {{
                                    value = value.trim();
                                }}
                                return {{ success: true, value: value }};
                            }}
                            return {{ success: false, error: 'Element not found' }};
                        }})()
                        """
                        extract_result = self.execute_js(script, context)
                        result['result'] = extract_result
                        result['status'] = 'completed'
                        
                        if var_name and extract_result and extract_result.get('success'):
                            context[var_name] = extract_result.get('value')
                            self.db.save_context(var_name, extract_result.get('value'))
                            result['metadata']['stored_in_context'] = var_name
                        break

                    elif step_type == WorkflowStepType.STORE.value:
                        var_name = params.get('variable_name')
                        var_value = params.get('value')
                        if var_name:
                            context[var_name] = var_value
                            self.db.save_context(var_name, var_value)
                            result['result'] = {'stored': var_name, 'value': var_value}
                            result['status'] = 'completed'
                        else:
                            raise ValueError("variable_name required for store")
                        break

                    elif step_type == WorkflowStepType.WAIT.value:
                        seconds = params.get('seconds', 1)
                        time.sleep(seconds)
                        result['result'] = {'waited': seconds}
                        result['status'] = 'completed'
                        break

                    elif step_type == WorkflowStepType.SCREENSHOT.value:
                        filename = params.get('filename', f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                        script = f"""
                        (function() {{
                            const canvas = document.createElement('canvas');
                            const ctx = canvas.getContext('2d');
                            // Simple screenshot via CDP is better, but this is a fallback
                            return {{ filename: '{filename}', status: 'captured' }};
                        }})()
                        """
                        result['result'] = self.execute_js(script, context)
                        result['status'] = 'completed'
                        break

                    elif step_type == WorkflowStepType.API_CALL.value:
                        method = params.get('method', 'GET')
                        url = params.get('url')
                        headers = params.get('headers', {})
                        body = params.get('body', {})
                        
                        if not url:
                            raise ValueError("URL required for API call")
                        
                        if method.upper() == 'GET':
                            resp = requests.get(url, headers=headers, timeout=step.timeout)
                        else:
                            resp = requests.request(method, url, headers=headers, json=body, timeout=step.timeout)
                        
                        result['result'] = {
                            'status_code': resp.status_code,
                            'headers': dict(resp.headers),
                            'body': resp.json() if resp.headers.get('content-type', '').startswith('application/json') else resp.text
                        }
                        result['status'] = 'completed'
                        break

                    elif step_type == WorkflowStepType.ASSERT.value:
                        condition = params.get('condition')
                        expected = params.get('expected')
                        operator = params.get('operator', 'equals')
                        
                        if not condition:
                            raise ValueError("Condition required for assert")
                        
                        actual = self.execute_js(condition, context)
                        
                        if operator == 'equals':
                            assert str(actual) == str(expected), f"Assertion failed: {actual} != {expected}"
                        elif operator == 'contains':
                            assert str(expected) in str(actual), f"Assertion failed: {expected} not in {actual}"
                        elif operator == 'greater':
                            assert float(actual) > float(expected), f"Assertion failed: {actual} <= {expected}"
                        elif operator == 'less':
                            assert float(actual) < float(expected), f"Assertion failed: {actual} >= {expected}"
                        
                        result['result'] = {'passed': True, 'actual': actual, 'expected': expected}
                        result['status'] = 'completed'
                        break

                    elif step_type == WorkflowStepType.LOOP.value:
                        iterations = params.get('iterations', 5)
                        variable_name = params.get('variable_name', 'loop_index')
                        loop_code = params.get('code', '')
                        loop_script_id = params.get('script_id')
                        
                        if loop_script_id:
                            script = self.db.get_script(loop_script_id)
                            if script:
                                loop_code = script.get('code', '')
                        
                        if not loop_code:
                            raise ValueError("Loop code or script_id required")
                        
                        loop_results = []
                        for i in range(iterations):
                            context[variable_name] = i
                            loop_result = self.execute_js(loop_code, context)
                            loop_results.append({
                                'iteration': i,
                                'result': loop_result
                            })
                        
                        result['result'] = {'iterations': iterations, 'results': loop_results}
                        result['status'] = 'completed'
                        break

                    elif step_type == WorkflowStepType.CRAWL.value:
                        max_pages = params.get('max_pages', 20)
                        start_url = params.get('start_url')
                        
                        if not start_url:
                            start_url = self.chrome.page_info.get('url')
                        
                        if not start_url:
                            raise ValueError("Start URL required for crawl")
                        
                        crawl_result = self._crawl_site(start_url, max_pages)
                        result['result'] = crawl_result
                        result['status'] = 'completed'
                        break

                    elif step_type == WorkflowStepType.SCRAPE.value:
                        selector = params.get('selector')
                        attribute = params.get('attribute', 'textContent')
                        scrape_type = params.get('scrape_type', 'single')
                        
                        if scrape_type == 'single':
                            script = f"""
                            (function() {{
                                const el = document.querySelector('{selector}');
                                if (el) {{
                                    let value = el.{attribute};
                                    if (typeof value === 'string') value = value.trim();
                                    return {{ success: true, value: value }};
                                }}
                                return {{ success: false, error: 'Element not found' }};
                            }})()
                            """
                        else:
                            script = f"""
                            (function() {{
                                const els = document.querySelectorAll('{selector}');
                                const values = [];
                                els.forEach(el => {{
                                    let value = el.{attribute};
                                    if (typeof value === 'string') value = value.trim();
                                    if (value) values.push(value);
                                }});
                                return {{ success: true, values: values, count: values.length }};
                            }})()
                            """
                        
                        result['result'] = self.execute_js(script, context)
                        result['status'] = 'completed'
                        break

                    elif step_type == WorkflowStepType.TRIGGER.value:
                        target_workflow = params.get('target_workflow')
                        if not target_workflow:
                            raise ValueError("target_workflow required for trigger")
                        
                        # Execute the target workflow
                        engine = WorkflowEngine(self.config)
                        target = engine.load_workflow(target_workflow)
                        if target:
                            trigger_result = engine.execute(target, context)
                            result['result'] = {
                                'triggered': target_workflow,
                                'status': trigger_result.get('status')
                            }
                            result['status'] = 'completed'
                        else:
                            raise ValueError(f"Target workflow '{target_workflow}' not found")
                        break

                    elif step_type == WorkflowStepType.EXPORT.value:
                        format_type = params.get('format', 'json')
                        filename = params.get('filename', f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format_type}")
                        data_to_export = params.get('data', context)
                        
                        save_dir = Path(self.config.data_dir) / "exports"
                        save_dir.mkdir(parents=True, exist_ok=True)
                        filepath = save_dir / filename
                        
                        if format_type == 'json':
                            with open(filepath, 'w') as f:
                                json.dump(data_to_export, f, indent=2, default=str)
                        elif format_type == 'csv':
                            import csv
                            if isinstance(data_to_export, list) and data_to_export:
                                with open(filepath, 'w', newline='') as f:
                                    writer = csv.DictWriter(f, fieldnames=data_to_export[0].keys())
                                    writer.writeheader()
                                    writer.writerows(data_to_export)
                        else:
                            with open(filepath, 'w') as f:
                                f.write(str(data_to_export))
                        
                        result['result'] = {'file': str(filepath), 'format': format_type}
                        result['status'] = 'completed'
                        break

                    elif step_type == WorkflowStepType.NOTIFY.value:
                        message = params.get('message', 'Workflow step completed')
                        level = params.get('level', 'info')
                        
                        if level == 'info':
                            console.print(f"[cyan]ℹ️ {message}[/cyan]")
                        elif level == 'success':
                            console.print(f"[green]✅ {message}[/green]")
                        elif level == 'warning':
                            console.print(f"[yellow]⚠️ {message}[/yellow]")
                        elif level == 'error':
                            console.print(f"[red]❌ {message}[/red]")
                        
                        result['result'] = {'message': message, 'level': level}
                        result['status'] = 'completed'
                        break

                    else:
                        raise ValueError(f"Unknown step type: {step_type}")

                except Exception as e:
                    if attempt < retry_count:
                        console.print(f"[yellow]Retry {attempt+1}/{retry_count} for step '{step_name}': {e}[/yellow]")
                        time.sleep(retry_delay)
                        continue
                    raise e

        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)
            self.logger.error(f"Step '{step_name}' failed: {e}")

        result['completed_at'] = datetime.now().isoformat()
        
        # Save result to database
        self.db.save_result({
            'execution_id': self._execution_id,
            'step_id': step.id,
            'step_name': step_name,
            'data': result.get('result', {}),
            'metadata': result.get('metadata', {}),
            'status': result['status']
        })
        
        return result

    def _crawl_site(self, start_url: str, max_pages: int = 20) -> Dict:
        """Crawl a site starting from a URL"""
        visited = set()
        queue = deque([start_url])
        discovered_urls = set([start_url])
        page_data = {}
        
        while queue and len(visited) < max_pages:
            url = queue.popleft()
            if url in visited:
                continue
            
            visited.add(url)
            console.print(f"[dim]Crawling: {url}[/dim]")
            
            # Navigate to URL
            if url != start_url:
                self.chrome.navigate(url)
            
            # Get page data
            data = self.chrome.get_page_content()
            page_data[url] = {
                'title': data.get('title', ''),
                'headers': data.get('headers', []),
                'paragraphs': data.get('paragraphs', [])[:10],
                'links': data.get('links', [])[:20],
                'forms': data.get('forms', []),
                'meta': data.get('meta', {})
            }
            
            # Extract new links
            for link in data.get('links', []):
                href = link.get('href', '')
                if href and not href.startswith(('javascript:', 'mailto:', '#')):
                    # Only same domain
                    if start_url in href or href.startswith('/'):
                        if href.startswith('/'):
                            parsed = urlparse(start_url)
                            href = f"{parsed.scheme}://{parsed.netloc}{href}"
                        if href not in discovered_urls:
                            discovered_urls.add(href)
                            queue.append(href)
            
            time.sleep(0.5)
        
        return {
            'start_url': start_url,
            'pages_visited': len(visited),
            'urls_discovered': len(discovered_urls),
            'urls': list(discovered_urls),
            'page_data': page_data
        }

    def load_workflow(self, identifier: str) -> Optional[Workflow]:
        """Load a workflow by ID or name"""
        # Try ID first
        workflow_data = self.db.get_workflow(identifier)
        if workflow_data:
            return Workflow.from_dict(workflow_data)
        
        # Try name
        workflow_data = self.db.get_workflow_by_name(identifier)
        if workflow_data:
            return Workflow.from_dict(workflow_data)
        
        return None

    def execute(self, workflow: Union[Workflow, str], context: Dict = None) -> Dict:
        """Execute a workflow"""
        if isinstance(workflow, str):
            workflow = self.load_workflow(workflow)
            if not workflow:
                return {'error': f'Workflow "{workflow}" not found'}
        
        self._current_workflow = workflow
        self._execution_id = str(uuid.uuid4())
        self.context = context or {}
        
        # Merge workflow config context
        if workflow.config.get('context'):
            self.context.update(workflow.config['context'])
        
        execution_result = {
            'id': self._execution_id,
            'workflow_id': workflow.id,
            'workflow_name': workflow.name,
            'status': 'running',
            'steps_total': len(workflow.steps),
            'steps_completed': 0,
            'results': [],
            'error': None,
            'started_at': datetime.now().isoformat(),
            'metadata': {}
        }
        
        start_time = time.time()
        
        try:
            for step_data in workflow.steps:
                step = WorkflowStep.from_dict(step_data)
                
                # Check dependencies
                if step.depends_on:
                    for dep_id in step.depends_on:
                        if dep_id not in [r['step_id'] for r in execution_result['results']]:
                            console.print(f"[yellow]Waiting for dependency: {dep_id}[/yellow]")
                            continue
                
                # Check condition
                if step.condition:
                    condition_result = self.execute_js(step.condition, self.context)
                    if not condition_result:
                        console.print(f"[dim]Skipping step '{step.name}' - condition not met[/dim]")
                        continue
                
                # Execute step
                step_result = self.execute_step(step, self.context)
                execution_result['results'].append(step_result)
                execution_result['steps_completed'] += 1
                
                # Update step results in context
                if step_result['status'] == 'completed':
                    self.context[f"_step_{step.id}"] = step_result['result']
                
                if step_result['status'] == 'failed' and not step.continue_on_error:
                    execution_result['status'] = 'failed'
                    execution_result['error'] = step_result.get('error', 'Step failed')
                    break
            
            if execution_result['status'] == 'running':
                execution_result['status'] = 'completed'
        
        except Exception as e:
            execution_result['status'] = 'failed'
            execution_result['error'] = str(e)
            self.logger.error(f"Workflow execution failed: {e}")
        
        execution_result['duration'] = time.time() - start_time
        execution_result['completed_at'] = datetime.now().isoformat()
        
        # Save execution
        self.db.save_execution(execution_result)
        
        # Update workflow stats
        workflow.execution_count += 1
        if workflow.avg_duration:
            workflow.avg_duration = (workflow.avg_duration + execution_result['duration']) / 2
        else:
            workflow.avg_duration = execution_result['duration']
        self.db.save_workflow(workflow.to_dict())
        
        # Log
        console.print(f"\n[bold]Execution {execution_result['status']}:[/bold]")
        console.print(f"  Workflow: {workflow.name}")
        console.print(f"  Duration: {execution_result['duration']:.2f}s")
        console.print(f"  Steps: {execution_result['steps_completed']}/{execution_result['steps_total']}")
        
        return execution_result

    def get_workflow_status(self, workflow_id: str) -> Dict:
        """Get status of a workflow"""
        workflow = self.load_workflow(workflow_id)
        if not workflow:
            return {'error': f'Workflow "{workflow_id}" not found'}
        
        executions = self.db.get_executions(workflow_id, limit=1)
        latest = executions[0] if executions else None
        
        return {
            'workflow_id': workflow.id,
            'workflow_name': workflow.name,
            'status': workflow.status,
            'execution_count': workflow.execution_count,
            'avg_duration': workflow.avg_duration,
            'last_execution': latest
        }

# ============================================================================
# Workflow Builder - Fluent API
# ============================================================================

class WorkflowBuilder:
    """Fluent API for building workflows"""

    def __init__(self, name: str = None, description: str = None):
        self.workflow = Workflow(
            name=name or f"workflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            description=description or "",
            config={},
            steps=[],
            metadata={},
            tags=[]
        )
        self.db = DatabaseManager()

    def configure(self, **kwargs) -> 'WorkflowBuilder':
        """Configure workflow settings"""
        for key, value in kwargs.items():
            self.workflow.config[key] = value
        return self

    def set_context(self, **kwargs) -> 'WorkflowBuilder':
        """Set context variables"""
        if 'context' not in self.workflow.config:
            self.workflow.config['context'] = {}
        self.workflow.config['context'].update(kwargs)
        return self

    def set_metadata(self, key: str, value: Any) -> 'WorkflowBuilder':
        self.workflow.metadata[key] = value
        return self

    def add_tag(self, tag: str) -> 'WorkflowBuilder':
        if tag not in self.workflow.tags:
            self.workflow.tags.append(tag)
        return self

    def add_step(self, step_type: str, name: str = None, **params) -> 'WorkflowBuilder':
        """Add a step to the workflow"""
        step = WorkflowStep(
            type=step_type,
            name=name or f"{step_type}_{len(self.workflow.steps) + 1}",
            params=params
        )
        self.workflow.steps.append(step.to_dict())
        return self

    def js(self, code: str, name: str = None, **kwargs) -> 'WorkflowBuilder':
        """Add a JavaScript step"""
        return self.add_step('js', name, code=code, **kwargs)

    def navigate(self, url: str, name: str = "Navigate") -> 'WorkflowBuilder':
        """Add a navigate step"""
        return self.add_step('navigate', name, url=url)

    def click(self, selector: str, name: str = "Click") -> 'WorkflowBuilder':
        """Add a click step"""
        return self.add_step('click', name, selector=selector)

    def fill(self, selector: str, value: str, name: str = "Fill") -> 'WorkflowBuilder':
        """Add a fill step"""
        return self.add_step('fill', name, selector=selector, value=value)

    def extract(self, selector: str, variable_name: str = None, 
                attribute: str = 'textContent', name: str = "Extract") -> 'WorkflowBuilder':
        """Add an extract step"""
        return self.add_step('extract', name, 
                           selector=selector, variable_name=variable_name, attribute=attribute)

    def store(self, variable_name: str, value: Any, name: str = "Store") -> 'WorkflowBuilder':
        """Add a store step"""
        return self.add_step('store', name, variable_name=variable_name, value=value)

    def wait(self, seconds: int = 1, name: str = "Wait") -> 'WorkflowBuilder':
        """Add a wait step"""
        return self.add_step('wait', name, seconds=seconds)

    def screenshot(self, filename: str = None, name: str = "Screenshot") -> 'WorkflowBuilder':
        """Add a screenshot step"""
        return self.add_step('screenshot', name, filename=filename)

    def api_call(self, method: str, url: str, headers: Dict = None, 
                 body: Dict = None, name: str = "API Call") -> 'WorkflowBuilder':
        """Add an API call step"""
        return self.add_step('api_call', name, method=method, url=url, 
                           headers=headers or {}, body=body or {})

    def assert_equals(self, condition: str, expected: Any, 
                      name: str = "Assert") -> 'WorkflowBuilder':
        """Add an assert step"""
        return self.add_step('assert', name, condition=condition, 
                           expected=expected, operator='equals')

    def assert_contains(self, condition: str, expected: str, 
                        name: str = "Assert Contains") -> 'WorkflowBuilder':
        """Add an assert contains step"""
        return self.add_step('assert', name, condition=condition, 
                           expected=expected, operator='contains')

    def loop(self, iterations: int, code: str = None, script_id: str = None,
             variable_name: str = 'loop_index', name: str = "Loop") -> 'WorkflowBuilder':
        """Add a loop step"""
        return self.add_step('loop', name, iterations=iterations, 
                           code=code, script_id=script_id, variable_name=variable_name)

    def crawl(self, start_url: str = None, max_pages: int = 20, 
              name: str = "Crawl") -> 'WorkflowBuilder':
        """Add a crawl step"""
        return self.add_step('crawl', name, start_url=start_url, max_pages=max_pages)

    def scrape(self, selector: str, attribute: str = 'textContent', 
               scrape_type: str = 'single', name: str = "Scrape") -> 'WorkflowBuilder':
        """Add a scrape step"""
        return self.add_step('scrape', name, selector=selector, 
                           attribute=attribute, scrape_type=scrape_type)

    def trigger(self, target_workflow: str, name: str = "Trigger") -> 'WorkflowBuilder':
        """Add a trigger step"""
        return self.add_step('trigger', name, target_workflow=target_workflow)

    def export(self, format: str = 'json', filename: str = None, 
               data: Dict = None, name: str = "Export") -> 'WorkflowBuilder':
        """Add an export step"""
        return self.add_step('export', name, format=format, filename=filename, data=data)

    def notify(self, message: str, level: str = 'info', name: str = "Notify") -> 'WorkflowBuilder':
        """Add a notification step"""
        return self.add_step('notify', name, message=message, level=level)

    def conditional(self, condition: str, steps: List[Dict], 
                    else_steps: List[Dict] = None, name: str = "Conditional") -> 'WorkflowBuilder':
        """Add a conditional block"""
        return self.add_step('conditional', name, condition=condition, 
                           steps=steps, else_steps=else_steps or [])

    def build(self) -> Workflow:
        """Build and return the workflow"""
        self.workflow.updated_at = datetime.now().isoformat()
        return self.workflow

    def save(self) -> str:
        """Save the workflow to database"""
        workflow = self.build()
        workflow_id = self.db.save_workflow(workflow.to_dict())
        console.print(f"[green]✅ Workflow saved: {workflow.name} (ID: {workflow_id})[/green]")
        return workflow_id

    def execute(self, context: Dict = None) -> Dict:
        """Execute the workflow immediately"""
        workflow = self.build()
        engine = WorkflowEngine()
        return engine.execute(workflow, context)

# ============================================================================
# Advanced CLI - Complete Interactive Interface
# ============================================================================

class AdvancedWorkflowCLI:
    """Complete interactive CLI for workflow management"""

    def __init__(self):
        self.config = WorkflowConfig()
        self.config.ensure_directories()
        self.db = DatabaseManager(self.config)
        self.engine = WorkflowEngine(self.config)
        self.current_workflow = None
        self.context = {}
        self._running = True

    def run(self):
        """Main CLI loop"""
        while self._running:
            console.clear()
            self._show_header()
            
            menu = Table(show_header=False, box=box.MINIMAL_HEAVY_HEAD)
            menu.add_column("Option", style="cyan", width=8)
            menu.add_column("Action", style="white")
            menu.add_column("Description", style="dim")
            
            menu.add_row("1", "[green]Build Workflow[/green]", "Interactive workflow builder")
            menu.add_row("2", "[blue]Run Workflow[/blue]", "Execute a workflow")
            menu.add_row("3", "[cyan]Edit Workflow[/cyan]", "Edit existing workflow")
            menu.add_row("4", "[magenta]List Workflows[/magenta]", "Show all workflows")
            menu.add_row("5", "[yellow]Script Library[/yellow]", "Manage JavaScript scripts")
            menu.add_row("6", "[red]Delete Workflow[/red]", "Delete a workflow")
            menu.add_row("7", "[white]Execution History[/white]", "View workflow execution logs")
            menu.add_row("8", "[green]Workflow Stats[/green]", "Show workflow statistics")
            menu.add_row("9", "[bold]Connect Chrome[/bold]", "Connect to Chrome browser")
            menu.add_row("0", "[red]Exit[/red]", "Exit")
            
            console.print(menu)
            console.print()
            
            choice = Prompt.ask("Select option", choices=["0","1","2","3","4","5","6","7","8","9"])
            
            if choice == "0":
                self._running = False
                break
            elif choice == "1":
                self._build_workflow_interactive()
            elif choice == "2":
                self._run_workflow_interactive()
            elif choice == "3":
                self._edit_workflow_interactive()
            elif choice == "4":
                self._list_workflows()
            elif choice == "5":
                self._script_library_interactive()
            elif choice == "6":
                self._delete_workflow_interactive()
            elif choice == "7":
                self._show_execution_history()
            elif choice == "8":
                self._show_stats()
            elif choice == "9":
                self._connect_chrome()
            
            if choice != "0":
                console.print()
                Prompt.ask("Press Enter to continue...")

    def _show_header(self):
        """Show dashboard header"""
        workflows = self.db.list_workflows()
        scripts = self.db.list_scripts()
        
        header = f"""
╔══════════════════════════════════════════════════════════════╗
║     🚀 Advanced Workflow Builder v3.0                       ║
║     Complete Chrome Automation System                       ║
╠══════════════════════════════════════════════════════════════╣
║  📋 Workflows: {len(workflows)}  |  📜 Scripts: {len(scripts)}  |  🔗 Chrome: {'✅' if self.engine.chrome.connected else '❌'}  ║
╚══════════════════════════════════════════════════════════════╝
        """
        console.print(Panel(header, border_style="cyan"))

    def _build_workflow_interactive(self):
        """Interactive workflow builder"""
        console.print(Panel("[bold green]🏗️ Build Workflow[/bold green]", border_style="green"))
        
        name = Prompt.ask("Workflow name")
        if not name:
            console.print("[red]Name required[/red]")
            return
        
        description = Prompt.ask("Description", default="")
        
        builder = WorkflowBuilder(name, description)
        
        # Configure Chrome connection
        if Confirm.ask("Configure Chrome connection?", default=True):
            port = int(Prompt.ask("Chrome port", default="9222"))
            builder.configure(chrome_port=port)
        
        # Add steps
        while True:
            console.print("\n[bold]Add a step:[/bold]")
            console.print("  1. JavaScript")
            console.print("  2. Navigate")
            console.print("  3. Click")
            console.print("  4. Fill")
            console.print("  5. Extract")
            console.print("  6. Store")
            console.print("  7. Wait")
            console.print("  8. Screenshot")
            console.print("  9. API Call")
            console.print(" 10. Assert")
            console.print(" 11. Loop")
            console.print(" 12. Crawl")
            console.print(" 13. Scrape")
            console.print(" 14. Trigger")
            console.print(" 15. Export")
            console.print(" 16. Notify")
            console.print("  0. Done")
            
            choice = Prompt.ask("Select step type", choices=["0","1","2","3","4","5","6","7","8","9","10","11","12","13","14","15","16"])
            
            if choice == "0":
                break
            
            step_name = Prompt.ask("Step name", default=f"Step_{len(builder.workflow.steps) + 1}")
            
            if choice == "1":
                console.print("[yellow]Enter JavaScript code (press Ctrl+D when done):[/yellow]")
                lines = []
                try:
                    while True:
                        line = input()
                        lines.append(line)
                except EOFError:
                    pass
                code = "\n".join(lines)
                builder.js(code, step_name)
            
            elif choice == "2":
                url = Prompt.ask("URL")
                builder.navigate(url, step_name)
            
            elif choice == "3":
                selector = Prompt.ask("CSS selector")
                builder.click(selector, step_name)
            
            elif choice == "4":
                selector = Prompt.ask("CSS selector")
                value = Prompt.ask("Value")
                builder.fill(selector, value, step_name)
            
            elif choice == "5":
                selector = Prompt.ask("CSS selector")
                var_name = Prompt.ask("Store in variable (optional)", default="")
                builder.extract(selector, var_name if var_name else None, name=step_name)
            
            elif choice == "6":
                var_name = Prompt.ask("Variable name")
                value = Prompt.ask("Value")
                try:
                    value = json.loads(value)
                except:
                    pass
                builder.store(var_name, value, step_name)
            
            elif choice == "7":
                seconds = int(Prompt.ask("Seconds", default="1"))
                builder.wait(seconds, step_name)
            
            elif choice == "8":
                filename = Prompt.ask("Filename (optional)", default="")
                builder.screenshot(filename if filename else None, step_name)
            
            elif choice == "9":
                method = Prompt.ask("Method", default="GET")
                url = Prompt.ask("URL")
                builder.api_call(method, url, name=step_name)
            
            elif choice == "10":
                condition = Prompt.ask("JavaScript condition")
                expected = Prompt.ask("Expected value")
                try:
                    expected = json.loads(expected)
                except:
                    pass
                builder.assert_equals(condition, expected, step_name)
            
            elif choice == "11":
                iterations = int(Prompt.ask("Iterations", default="5"))
                console.print("[yellow]Enter loop code (press Ctrl+D when done):[/yellow]")
                lines = []
                try:
                    while True:
                        line = input()
                        lines.append(line)
                except EOFError:
                    pass
                code = "\n".join(lines)
                var_name = Prompt.ask("Variable name", default="loop_index")
                builder.loop(iterations, code, variable_name=var_name, name=step_name)
            
            elif choice == "12":
                max_pages = int(Prompt.ask("Max pages", default="20"))
                start_url = Prompt.ask("Start URL (optional)", default="")
                builder.crawl(start_url if start_url else None, max_pages, step_name)
            
            elif choice == "13":
                selector = Prompt.ask("CSS selector")
                scrape_type = Prompt.ask("Scrape type (single/multiple)", default="single")
                builder.scrape(selector, scrape_type=scrape_type, name=step_name)
            
            elif choice == "14":
                target = Prompt.ask("Target workflow name or ID")
                builder.trigger(target, step_name)
            
            elif choice == "15":
                format_type = Prompt.ask("Format (json/csv/text)", default="json")
                filename = Prompt.ask("Filename (optional)", default="")
                builder.export(format_type, filename if filename else None, name=step_name)
            
            elif choice == "16":
                message = Prompt.ask("Message")
                level = Prompt.ask("Level (info/success/warning/error)", default="info")
                builder.notify(message, level, step_name)
            
            console.print("[green]✅ Step added[/green]")
        
        # Tags
        tags = Prompt.ask("Tags (comma-separated)", default="")
        if tags:
            for tag in tags.split(','):
                builder.add_tag(tag.strip())
        
        # Save
        workflow_id = builder.save()
        console.print(f"[green]✅ Workflow '{name}' saved! ID: {workflow_id}[/green]")
        
        if Confirm.ask("Execute workflow now?", default=False):
            execution = builder.execute()
            self._display_execution_result(execution)

    def _run_workflow_interactive(self):
        """Run a workflow interactively"""
        workflows = self.db.list_workflows()
        if not workflows:
            console.print("[yellow]No workflows found[/yellow]")
            return
        
        console.print("\n[bold cyan]Select workflow to run:[/bold cyan]")
        for i, wf in enumerate(workflows, 1):
            console.print(f"  {i}. {wf['name']} ({wf.get('status', 'draft')}) - {len(wf.get('steps', []))} steps")
        
        choice = Prompt.ask("Enter workflow number or name")
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(workflows):
                workflow_id = workflows[idx]['id']
                workflow_name = workflows[idx]['name']
            else:
                workflow_id = choice
                workflow_name = choice
        except ValueError:
            workflow_id = choice
            workflow_name = choice
        
        # Load workflow
        workflow = self.engine.load_workflow(workflow_id)
        if not workflow:
            console.print(f"[red]Workflow '{workflow_name}' not found[/red]")
            return
        
        # Optional context
        context = {}
        if Confirm.ask("Add custom context?", default=False):
            context_str = Prompt.ask("Context (JSON format)")
            try:
                context = json.loads(context_str) if context_str else {}
            except:
                console.print("[yellow]Invalid JSON, using empty context[/yellow]")
        
        # Check Chrome connection
        if not self.engine.chrome.connected:
            if Confirm.ask("Connect to Chrome?", default=True):
                port = int(Prompt.ask("Chrome port", default="9222"))
                self.engine.connect_chrome(port)
        
        # Execute
        console.print(f"[yellow]Executing workflow '{workflow.name}'...[/yellow]")
        result = self.engine.execute(workflow, context)
        self._display_execution_result(result)

    def _display_execution_result(self, result: Dict):
        """Display execution results"""
        console.print()
        console.print(Panel(
            f"[bold]Execution Results:[/bold]\n"
            f"  Status: {'✅ Success' if result.get('status') == 'completed' else '❌ Failed'}\n"
            f"  Steps: {result.get('steps_completed', 0)}/{result.get('steps_total', 0)}\n"
            f"  Duration: {result.get('duration', 0):.2f}s\n"
            f"  ID: {result.get('id', 'N/A')}\n"
            f"  Started: {result.get('started_at', 'N/A')}\n"
            f"  Completed: {result.get('completed_at', 'N/A')}",
            title="📊 Execution Results",
            border_style="green" if result.get('status') == 'completed' else "red"
        ))
        
        # Show step details
        if result.get('results'):
            step_table = Table(title="Step Results", box=box.SIMPLE)
            step_table.add_column("#", style="cyan", width=4)
            step_table.add_column("Step", style="white")
            step_table.add_column("Status", style="green")
            step_table.add_column("Result", style="dim")
            
            for i, step in enumerate(result['results'], 1):
                status = "✅" if step['status'] == 'completed' else "❌"
                result_str = str(step.get('result', {}))[:50]
                step_table.add_row(str(i), step['step_name'], status, result_str)
            
            console.print(step_table)

    def _edit_workflow_interactive(self):
        """Edit an existing workflow"""
        workflows = self.db.list_workflows()
        if not workflows:
            console.print("[yellow]No workflows found[/yellow]")
            return
        
        console.print("\n[bold cyan]Select workflow to edit:[/bold cyan]")
        for i, wf in enumerate(workflows, 1):
            console.print(f"  {i}. {wf['name']} ({wf.get('status', 'draft')}) - {len(wf.get('steps', []))} steps")
        
        choice = Prompt.ask("Enter workflow number or name")
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(workflows):
                workflow_id = workflows[idx]['id']
                workflow_name = workflows[idx]['name']
            else:
                workflow_id = choice
                workflow_name = choice
        except ValueError:
            workflow_id = choice
            workflow_name = choice
        
        workflow_data = self.db.get_workflow(workflow_id)
        if not workflow_data:
            workflow_data = self.db.get_workflow_by_name(workflow_name)
        
        if not workflow_data:
            console.print(f"[red]Workflow not found[/red]")
            return
        
        workflow = Workflow.from_dict(workflow_data)
        
        console.print(f"[cyan]Editing workflow: {workflow.name}[/cyan]")
        
        # Show steps
        if workflow.steps:
            table = Table(title="Current Steps", box=box.ROUNDED)
            table.add_column("#", style="cyan", width=4)
            table.add_column("Name", style="green")
            table.add_column("Type", style="yellow")
            table.add_column("ID", style="dim")
            
            for i, step in enumerate(workflow.steps, 1):
                table.add_row(str(i), step.get('name', 'unnamed'), 
                            step.get('type', 'unknown'), step.get('id', '')[:8])
            console.print(table)
        
        console.print("\n[bold]Edit options:[/bold]")
        console.print("  1. Edit step")
        console.print("  2. Add step")
        console.print("  3. Remove step")
        console.print("  4. Rename workflow")
        console.print("  5. Edit description")
        console.print("  6. Edit tags")
        console.print("  0. Back")
        
        edit_choice = Prompt.ask("Select", choices=["0","1","2","3","4","5","6"])
        
        if edit_choice == "0":
            return
        
        elif edit_choice == "1":
            step_num = int(Prompt.ask("Step number to edit")) - 1
            if 0 <= step_num < len(workflow.steps):
                step = workflow.steps[step_num]
                console.print(f"[bold]Editing step: {step.get('name')}[/bold]")
                
                # Show current params
                console.print(f"  Type: {step.get('type')}")
                console.print(f"  Params: {json.dumps(step.get('params', {}), indent=2)}")
                
                # Edit code if JS step
                if step.get('type') in ['js', 'loop']:
                    console.print("[yellow]Enter new code (press Ctrl+D when done):[/yellow]")
                    lines = []
                    try:
                        while True:
                            line = input()
                            lines.append(line)
                    except EOFError:
                        pass
                    new_code = "\n".join(lines)
                    if new_code.strip():
                        step['params']['code'] = new_code
                        console.print("[green]✅ Code updated[/green]")
                
                # Edit other params
                if Confirm.ask("Edit other parameters?", default=False):
                    param_key = Prompt.ask("Parameter key")
                    param_value = Prompt.ask("Parameter value")
                    try:
                        param_value = json.loads(param_value)
                    except:
                        pass
                    step['params'][param_key] = param_value
                
                # Save
                self.db.save_workflow(workflow.to_dict())
                console.print("[green]✅ Workflow updated[/green]")
        
        elif edit_choice == "2":
            # Use builder to add step
            builder = WorkflowBuilder(workflow.name, workflow.description)
            builder.workflow = workflow
            # Add step using the same interactive process
            console.print("[yellow]Adding a step...[/yellow]")
            # Simplified: just add a JS step
            step_name = Prompt.ask("Step name")
            console.print("[yellow]Enter JavaScript code (press Ctrl+D when done):[/yellow]")
            lines = []
            try:
                while True:
                    line = input()
                    lines.append(line)
            except EOFError:
                pass
            code = "\n".join(lines)
            if code.strip():
                new_step = {
                    'id': str(uuid.uuid4())[:8],
                    'type': 'js',
                    'name': step_name,
                    'params': {'code': code},
                    'continue_on_error': False,
                    'retry_count': 0
                }
                workflow.steps.append(new_step)
                self.db.save_workflow(workflow.to_dict())
                console.print(f"[green]✅ Step '{step_name}' added[/green]")
        
        elif edit_choice == "3":
            step_num = int(Prompt.ask("Step number to remove")) - 1
            if 0 <= step_num < len(workflow.steps):
                removed = workflow.steps.pop(step_num)
                self.db.save_workflow(workflow.to_dict())
                console.print(f"[green]✅ Removed step: {removed.get('name')}[/green]")
        
        elif edit_choice == "4":
            new_name = Prompt.ask("New name")
            if new_name:
                workflow.name = new_name
                self.db.save_workflow(workflow.to_dict())
                console.print(f"[green]✅ Renamed to: {new_name}[/green]")
        
        elif edit_choice == "5":
            new_desc = Prompt.ask("New description", default=workflow.description)
            workflow.description = new_desc
            self.db.save_workflow(workflow.to_dict())
            console.print("[green]✅ Description updated[/green]")
        
        elif edit_choice == "6":
            tags_str = Prompt.ask("Tags (comma-separated)", default=",".join(workflow.tags))
            workflow.tags = [t.strip() for t in tags_str.split(',') if t.strip()]
            self.db.save_workflow(workflow.to_dict())
            console.print("[green]✅ Tags updated[/green]")

    def _list_workflows(self):
        """List all workflows with details"""
        workflows = self.db.list_workflows()
        if not workflows:
            console.print("[yellow]No workflows found[/yellow]")
            return
        
        table = Table(title=f"📋 Workflows ({len(workflows)})", box=box.ROUNDED)
        table.add_column("Name", style="green")
        table.add_column("Status", style="magenta")
        table.add_column("Steps", style="cyan", width=6)
        table.add_column("Executions", style="yellow", width=10)
        table.add_column("Avg Duration", style="blue", width=12)
        table.add_column("ID", style="dim", width=10)
        table.add_column("Tags", style="dim")
        
        status_colors = {
            'draft': 'dim',
            'active': 'green',
            'running': 'blue',
            'completed': 'green',
            'failed': 'red'
        }
        
        for wf in workflows:
            color = status_colors.get(wf.get('status', 'draft'), 'white')
            tags_str = ", ".join(wf.get('tags', []))[:20]
            avg_dur = f"{wf.get('avg_duration', 0):.2f}s" if wf.get('avg_duration') else "N/A"
            
            table.add_row(
                wf['name'],
                f"[{color}]{wf.get('status', 'draft')}[/{color}]",
                str(len(wf.get('steps', []))),
                str(wf.get('execution_count', 0)),
                avg_dur,
                wf['id'][:8],
                tags_str
            )
        
        console.print(table)

    def _script_library_interactive(self):
        """Manage script library"""
        console.print(Panel("[bold cyan]📜 Script Library[/bold cyan]", border_style="cyan"))
        
        while True:
            scripts = self.db.list_scripts()
            if scripts:
                table = Table(title=f"Scripts ({len(scripts)})", box=box.ROUNDED)
                table.add_column("Name", style="green")
                table.add_column("Type", style="yellow")
                table.add_column("Workflow", style="dim")
                table.add_column("Executions", style="blue")
                table.add_column("ID", style="dim")
                
                for script in scripts:
                    table.add_row(
                        script.get('name', 'unnamed'),
                        script.get('type', 'js'),
                        script.get('workflow_id', '')[:8],
                        str(script.get('execution_count', 0)),
                        script.get('id', '')[:8]
                    )
                console.print(table)
            
            console.print("\n[bold]Options:[/bold]")
            console.print("  1. Create script")
            console.print("  2. View script")
            console.print("  3. Edit script")
            console.print("  4. Delete script")
            console.print("  0. Back")
            
            choice = Prompt.ask("Select", choices=["0","1","2","3","4"])
            
            if choice == "0":
                break
            elif choice == "1":
                name = Prompt.ask("Script name")
                workflow_id = Prompt.ask("Workflow ID (optional)", default="")
                console.print("[yellow]Enter JavaScript code (press Ctrl+D when done):[/yellow]")
                lines = []
                try:
                    while True:
                        line = input()
                        lines.append(line)
                except EOFError:
                    pass
                code = "\n".join(lines)
                
                script_id = self.db.save_script({
                    'name': name,
                    'code': code,
                    'workflow_id': workflow_id,
                    'type': 'js',
                    'description': f"Script: {name}",
                    'tags': []
                })
                console.print(f"[green]✅ Script saved! ID: {script_id}[/green]")
            
            elif choice == "2":
                script_id = Prompt.ask("Script ID")
                script = self.db.get_script(script_id)
                if script:
                    console.print(f"[bold]Name:[/bold] {script.get('name')}")
                    console.print(f"[bold]ID:[/bold] {script.get('id')}")
                    console.print(f"[bold]Type:[/bold] {script.get('type')}")
                    console.print(f"[bold]Created:[/bold] {script.get('created_at', 'N/A')}")
                    console.print(f"\n[bold]Code:[/bold]")
                    syntax = Syntax(script.get('code', ''), "javascript", theme="monokai", line_numbers=True)
                    console.print(syntax)
                else:
                    console.print("[red]Script not found[/red]")
            
            elif choice == "3":
                script_id = Prompt.ask("Script ID")
                script = self.db.get_script(script_id)
                if script:
                    console.print("[yellow]Enter new code (press Ctrl+D when done):[/yellow]")
                    lines = []
                    try:
                        while True:
                            line = input()
                            lines.append(line)
                    except EOFError:
                        pass
                    new_code = "\n".join(lines)
                    if new_code.strip():
                        script['code'] = new_code
                        self.db.save_script(script)
                        console.print("[green]✅ Script updated[/green]")
                else:
                    console.print("[red]Script not found[/red]")
            
            elif choice == "4":
                script_id = Prompt.ask("Script ID")
                if Confirm.ask(f"Delete script '{script_id}'?"):
                    self.db.delete_script(script_id)
                    console.print("[green]✅ Script deleted[/green]")

    def _delete_workflow_interactive(self):
        """Delete a workflow"""
        workflows = self.db.list_workflows()
        if not workflows:
            console.print("[yellow]No workflows found[/yellow]")
            return
        
        console.print("\n[bold cyan]Select workflow to delete:[/bold cyan]")
        for i, wf in enumerate(workflows, 1):
            console.print(f"  {i}. {wf['name']} ({wf.get('status', 'draft')})")
        
        choice = Prompt.ask("Enter workflow number or name")
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(workflows):
                workflow_id = workflows[idx]['id']
                workflow_name = workflows[idx]['name']
            else:
                workflow_id = choice
                workflow_name = choice
        except ValueError:
            workflow_id = choice
            workflow_name = choice
        
        if Confirm.ask(f"Delete workflow '{workflow_name}'?"):
            if self.db.delete_workflow(workflow_id):
                console.print(f"[green]✅ Deleted workflow: {workflow_name}[/green]")
            else:
                console.print("[red]Failed to delete workflow[/red]")

    def _show_execution_history(self):
        """Show execution history"""
        executions = self.db.get_executions(limit=20)
        if not executions:
            console.print("[yellow]No execution history[/yellow]")
            return
        
        table = Table(title="📊 Execution History", box=box.ROUNDED)
        table.add_column("Workflow", style="green")
        table.add_column("Status", style="magenta", width=10)
        table.add_column("Steps", style="cyan", width=6)
        table.add_column("Duration", style="blue", width=10)
        table.add_column("Started", style="dim")
        table.add_column("ID", style="dim", width=10)
        
        for exec_data in executions:
            status_color = "green" if exec_data.get('status') == 'completed' else "red"
            duration = f"{exec_data.get('duration', 0):.2f}s" if exec_data.get('duration') else "N/A"
            
            table.add_row(
                exec_data.get('workflow_name', 'Unknown'),
                f"[{status_color}]{exec_data.get('status', 'unknown')}[/{status_color}]",
                f"{exec_data.get('steps_completed', 0)}/{exec_data.get('steps_total', 0)}",
                duration,
                exec_data.get('started_at', '')[:16],
                exec_data.get('id', '')[:8]
            )
        
        console.print(table)
        
        # Option to view details
        if Confirm.ask("View execution details?", default=False):
            exec_id = Prompt.ask("Execution ID")
            results = self.db.get_results(exec_id)
            if results:
                console.print(f"[bold]Execution {exec_id} results:[/bold]")
                for result in results:
                    status_color = "green" if result.get('status') == 'completed' else "red"
                    console.print(f"  {result.get('step_name')}: [{status_color}]{result.get('status')}[/{status_color}]")
                    if result.get('data'):
                        console.print(f"    Data: {str(result['data'])[:200]}")
            else:
                console.print("[yellow]No results found for this execution[/yellow]")

    def _show_stats(self):
        """Show workflow statistics"""
        workflows = self.db.list_workflows()
        executions = self.db.get_executions(limit=100)
        
        total_workflows = len(workflows)
        total_executions = len(executions)
        completed = len([e for e in executions if e.get('status') == 'completed'])
        failed = len([e for e in executions if e.get('status') == 'failed'])
        avg_duration = sum(e.get('duration', 0) for e in executions) / len(executions) if executions else 0
        
        stats = Panel(
            f"[bold]📊 Workflow Statistics[/bold]\n\n"
            f"  Total Workflows: {total_workflows}\n"
            f"  Total Executions: {total_executions}\n"
            f"  Completed: {completed}\n"
            f"  Failed: {failed}\n"
            f"  Success Rate: {(completed/total_executions*100 if total_executions else 0):.1f}%\n"
            f"  Avg Duration: {avg_duration:.2f}s\n"
            f"  Workflows with Steps: {len([w for w in workflows if w.get('steps')])}\n"
            f"  Total Scripts: {len(self.db.list_scripts())}",
            title="📈 Statistics",
            border_style="cyan"
        )
        console.print(stats)

    def _connect_chrome(self):
        """Connect to Chrome browser"""
        console.print(Panel("[bold yellow]🔗 Connect to Chrome[/bold yellow]", border_style="yellow"))
        
        port = int(Prompt.ask("Chrome port", default=str(self.config.chrome_port)))
        
        if self.engine.connect_chrome(port):
            console.print("[green]✅ Connected to Chrome[/green]")
            
            # Get page info
            content = self.engine.chrome.get_page_content()
            if content:
                console.print(f"  Title: {content.get('title', 'Unknown')}")
                console.print(f"  URL: {content.get('url', 'Unknown')}")
                
                if Confirm.ask("View page content?", default=False):
                    console.print(Panel(
                        f"Headers: {len(content.get('headers', []))}\n"
                        f"Paragraphs: {len(content.get('paragraphs', []))}\n"
                        f"Links: {len(content.get('links', []))}\n"
                        f"Forms: {len(content.get('forms', []))}\n"
                        f"Images: {len(content.get('images', []))}",
                        title="📄 Page Content Summary",
                        border_style="dim"
                    ))
        else:
            console.print("[red]Failed to connect to Chrome[/red]")
            console.print("[yellow]Make sure Chrome is running with: chrome --remote-debugging-port=9222[/yellow]")

# ============================================================================
# Main Entry Point
# ============================================================================

def setup_logging():
    """Setup logging configuration"""
    log_dir = Path.home() / "chrome-workflows" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "workflow.log")
        ]
    )

def main():
    """Main entry point"""
    setup_logging()
    
    # Ensure directories exist
    config = WorkflowConfig()
    config.ensure_directories()
    
    try:
        cli = AdvancedWorkflowCLI()
        cli.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
    except Exception as e:
        logging.exception("Fatal error")
        console.print(f"[red]Error: {e}[/red]")
        console.print("[dim]Check logs for details[/dim]")

if __name__ == "__main__":
    main()
