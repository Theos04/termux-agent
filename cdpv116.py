#!/usr/bin/env python3
"""
Chrome Session Manager - Production v14
Fixed: Health monitor tolerance, session stability
"""

import os
import time
import subprocess
import shutil
import signal
import sys
import json
import re
import logging
import logging.handlers
import threading
import queue
import socket
import hashlib
import tempfile
from typing import Optional, Dict, List, Any, Tuple, Set
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import atexit

try:
    import psutil
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
    import psutil

try:
    import websocket
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client"])
    import websocket

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich import box
    from rich.progress import Progress, SpinnerColumn, TextColumn
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rich"])
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich import box
    from rich.progress import Progress, SpinnerColumn, TextColumn

from session_db import SessionDB
import requests

console = Console()

# ============================================================================
# Configuration
# ============================================================================

@dataclass
class Config:
    base_profile_dir: str = os.path.expanduser("~/chrome-sessions")
    debug_port_start: int = 9222
    debug_port_end: int = 9299
    js_scripts_dir: str = os.path.expanduser("~/chrome-scripts")
    display_start: int = 1
    display_end: int = 5
    max_launch_retries: int = 3
    launch_retry_delay: int = 2
    health_check_interval: int = 30  # Check every 30 seconds instead of 10
    health_check_timeout: int = 60   # Give Chrome 60 seconds to become responsive
    session_stabilization_time: int = 45  # Wait 45 seconds before first health check
    log_dir: Path = Path.home() / "chrome-logs"
    log_retention_days: int = 7
    max_log_files: int = 100
    devtools_connect_timeout: int = 60  # Increased timeout
    session_lock_timeout: float = 5.0
    max_session_restarts: int = 3
    restart_backoff_base: int = 3  # Increased backoff
    min_disk_space_mb: int = 100
    vnc_password: str = "chrome123"
    vnc_geometry: str = "1366x768"
    vnc_display: int = 1

# ============================================================================
# Logging Setup
# ============================================================================

def setup_logging(config: Config) -> logging.Logger:
    config.log_dir.mkdir(parents=True, exist_ok=True)

    try:
        cleanup_old_logs(config)
    except Exception as e:
        print(f"Warning: Could not clean old logs: {e}", file=sys.stderr)

    log_file = config.log_dir / "chrome_manager.log"

    handler = logging.handlers.RotatingFileHandler(
        str(log_file),
        maxBytes=10_485_760,
        backupCount=5
    )

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[handler, logging.StreamHandler()]
    )

    return logging.getLogger(__name__)

def cleanup_old_logs(config: Config):
    cutoff = time.time() - (config.log_retention_days * 24 * 3600)

    for log_file in config.log_dir.glob("*.log"):
        try:
            if log_file.stat().st_mtime < cutoff:
                log_file.unlink()
        except:
            pass

    log_files = sorted(
        config.log_dir.glob("*.log"),
        key=lambda x: x.stat().st_mtime
    )
    while len(log_files) > config.max_log_files:
        try:
            log_files[0].unlink()
            log_files.pop(0)
        except:
            break

logger = setup_logging(Config())

# ============================================================================
# JavaScript Manager
# ============================================================================

class JavaScriptManager:
    def __init__(self):
        self.scripts = {}
        self.load_scripts()

    def load_scripts(self):
        config = Config()
        if os.path.exists(config.js_scripts_dir):
            for filename in os.listdir(config.js_scripts_dir):
                if filename.endswith('.json'):
                    try:
                        path = os.path.join(config.js_scripts_dir, filename)
                        with open(path, 'r') as f:
                            script_data = json.load(f)
                            script_id = filename.replace('.json', '')
                            self.scripts[script_id] = script_data
                    except Exception:
                        pass

    def save_script(self, script_data: Dict) -> str:
        config = Config()
        script_id = hashlib.md5(
            f"{script_data.get('name', '')}_{time.time()}".encode()
        ).hexdigest()[:8]

        script_data['id'] = script_id
        script_data['created'] = datetime.now().isoformat()
        script_data['updated'] = datetime.now().isoformat()

        os.makedirs(config.js_scripts_dir, exist_ok=True)
        filename = f"{script_id}.json"
        path = os.path.join(config.js_scripts_dir, filename)

        with open(path, 'w') as f:
            json.dump(script_data, f, indent=2)

        self.scripts[script_id] = script_data
        return script_id

    def delete_script(self, script_id: str) -> bool:
        if script_id not in self.scripts:
            return False

        config = Config()
        filename = f"{script_id}.json"
        path = os.path.join(config.js_scripts_dir, filename)

        try:
            os.remove(path)
            del self.scripts[script_id]
            return True
        except:
            return False

    def get_script(self, script_id: str) -> Optional[Dict]:
        return self.scripts.get(script_id)

    def list_scripts(self) -> List[Dict]:
        return list(self.scripts.values())

# ============================================================================
# Display Manager - Fixed for Termux
# ============================================================================

class DisplayManager:
    def __init__(self, config: Config):
        self.config = config
        self.current_display = None
        self.vnc_port = None
        self.vnc_pid = None
        self._lock = threading.RLock()

    def _check_display(self) -> bool:
        """Check if DISPLAY is set and working"""
        display = os.environ.get('DISPLAY')
        if not display:
            return False
        
        # Try to connect to X display via TCP
        try:
            display_num = display.replace(':', '').replace('/', '')
            port = 6000 + int(display_num)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                if sock.connect_ex(('127.0.0.1', port)) == 0:
                    return True
        except:
            pass
        
        # Check if VNC is running
        try:
            result = subprocess.run(
                ['vncserver', '-list'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return True
        except:
            pass
        
        return False

    def _get_vnc_sessions(self) -> List[Dict[str, Any]]:
        """Get running VNC sessions"""
        try:
            result = subprocess.run(
                ['vncserver', '-list'],
                capture_output=True,
                text=True,
                timeout=5
            )
            sessions = []
            lines = result.stdout.strip().split('\n')
            for line in lines:
                match = re.search(r':(\d+)\s+(\d+)', line)
                if match:
                    display_num = int(match.group(1))
                    sessions.append({
                        'display': f":{display_num}",
                        'pid': int(match.group(2)),
                        'port': 5900 + display_num
                    })
            return sessions
        except Exception as e:
            logger.debug(f"Failed to list VNC sessions: {e}")
            return []

    def get_display(self) -> Tuple[Optional[str], Optional[int]]:
        """Get a working display"""
        
        # Check if DISPLAY is already set and working
        if self._check_display():
            self.current_display = os.environ.get('DISPLAY')
            logger.info(f"✅ Using existing DISPLAY: {self.current_display}")
            console.print(f"[green]✅ Using display: {self.current_display}[/green]")
            
            # Get VNC info if available
            vnc_sessions = self._get_vnc_sessions()
            for session in vnc_sessions:
                if session['display'] == self.current_display:
                    self.vnc_port = session['port']
                    self.vnc_pid = session['pid']
                    console.print(f"[green]📺 VNC available: vnc://127.0.0.1:{self.vnc_port} (password: {self.config.vnc_password})[/green]")
                    break
            
            return self.current_display, self.vnc_port
        
        # Try to find a VNC session
        vnc_sessions = self._get_vnc_sessions()
        if vnc_sessions:
            # Use the first VNC session
            session = vnc_sessions[0]
            display = session['display']
            self.current_display = display
            self.vnc_port = session['port']
            self.vnc_pid = session['pid']
            
            # Set DISPLAY environment
            os.environ['DISPLAY'] = display
            
            logger.info(f"✅ Using VNC display: {display}")
            console.print(f"[green]✅ Using VNC display: {display} (port {self.vnc_port})[/green]")
            console.print(f"[green]📺 VNC available: vnc://127.0.0.1:{self.vnc_port} (password: {self.config.vnc_password})[/green]")
            return display, self.vnc_port
        
        # No display found - use headless
        logger.warning("No display available - using headless mode")
        console.print("[yellow]⚠️ No display available - running in headless mode[/yellow]")
        return None, None

# ============================================================================
# Chrome DevTools
# ============================================================================

class ChromeDevTools:
    def __init__(self, host='127.0.0.1', port=9222):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.session = requests.Session()
        self.session.timeout = 5
        self._last_check = 0
        self._cached_result = False

    def _ensure_connection(self) -> bool:
        """Check if DevTools is accessible with caching"""
        now = time.time()
        if now - self._last_check < 5:  # Cache for 5 seconds
            return self._cached_result
        
        try:
            response = self.session.get(f"{self.base_url}/json/version", timeout=5)
            self._cached_result = response.status_code == 200
            self._last_check = now
            return self._cached_result
        except:
            self._cached_result = False
            self._last_check = now
            return False

    def wait_for_connection(self, timeout: int = 60) -> bool:
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._ensure_connection():
                return True
            time.sleep(2)
        return False

    def get_tabs(self) -> List[Dict]:
        try:
            response = self.session.get(f"{self.base_url}/json", timeout=5)
            if response.status_code == 200:
                tabs = response.json()
                return [t for t in tabs if t.get('type') == 'page']
            return []
        except Exception as e:
            logger.debug(f"Failed to get tabs: {e}")
            return []

    def get_ws_urls(self) -> List[Dict[str, str]]:
        tabs = self.get_tabs()
        result = []
        for tab in tabs:
            ws_url = tab.get('webSocketDebuggerUrl')
            if ws_url:
                ws_url = ws_url.strip()
                ws_url = re.sub(r',.*$', '', ws_url)
                if ws_url.startswith('http://'):
                    ws_url = ws_url.replace('http://', 'ws://')
                elif ws_url.startswith('https://'):
                    ws_url = ws_url.replace('https://', 'wss://')
                result.append({
                    'tab_id': tab.get('id'),
                    'title': tab.get('title', 'Untitled'),
                    'url': tab.get('url', ''),
                    'ws_url': ws_url
                })
        return result

# ============================================================================
# Chrome Launcher
# ============================================================================

class ChromeLauncher:
    def __init__(self, config: Config, chrome_path: str, display_manager: DisplayManager):
        self.config = config
        self.chrome_path = chrome_path
        self.display_manager = display_manager

    def build_command(self, session: Dict, use_display: bool) -> List[str]:
        profile_dir = session['profile_dir']

        cmd = [
            self.chrome_path,
            f"--remote-debugging-port={session['port']}",
            "--remote-allow-origins=*",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--disable-extensions",
            "--disable-gpu",
            "--window-size=1366,768",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-in-process-stack-traces",
            "--disable-logging",
            "--log-level=3",
            "--disable-breakpad",
            "--disable-crash-reporter",
            "--disable-component-update",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-default-apps",
            "--disable-translate",
            "--disable-dbus",
            "--disable-notifications",
            "--disable-prompt-on-repost",
            "--disable-hang-monitor",
            "--disable-client-side-phishing-detection",
            "--disable-component-extensions-with-background-pages",
            "--disable-field-trial-config",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--disable-features=BackForwardCache",
        ]

        features = [
            "IsolateOrigins", "site-per-process",
            "BlockInsecurePrivateNetworkRequests", "TranslateUI",
            "AudioServiceOutOfProcess", "PasswordImport",
            "PrivacySandboxSettings4", "PrivacySandboxAdsAPIsOverride",
            "EnableMsrPpqTesting", "EnableMsrPpqTrial", "EnableMsrPpq",
            "VizDisplayCompositor",
        ]
        cmd.append(f"--disable-features={','.join(features)}")

        if use_display:
            # Start with a blank page first, then navigate to the URL
            cmd.append("about:blank")
        else:
            cmd.extend([
                "--headless",
                "--disable-software-rasterizer",
                f"--window-size=1366,768",
            ])
            cmd.append(session['url'])

        return cmd

    def _verify_pid_is_chrome(self, pid: int) -> bool:
        try:
            proc = psutil.Process(pid)
            name = proc.name().lower()
            return 'chrome' in name or 'chromium' in name
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def launch_with_retry(self, session: Dict) -> Tuple[bool, Optional[int], str]:
        max_retries = self.config.max_launch_retries

        for attempt in range(max_retries):
            logger.info(f"Launch attempt {attempt + 1}/{max_retries}")

            success, pid, error = self._launch_once(session)
            if success and pid and self._verify_pid_is_chrome(pid):
                return True, pid, ""

            logger.warning(f"Attempt {attempt + 1} failed: {error}")

            if attempt < max_retries - 1:
                time.sleep(self.config.launch_retry_delay * (attempt + 1))

        return False, None, f"Failed after {max_retries} attempts"

    def _launch_once(self, session: Dict) -> Tuple[bool, Optional[int], str]:
        # Check if we have a display
        use_display = False
        display = self.display_manager.current_display

        if display:
            use_display = True
            logger.info(f"✅ Using display: {display}")
            console.print(f"[green]🖥️ Using display: {display}[/green]")

        # Build command
        cmd = self.build_command(session, use_display)
        logger.info(f"Command: {' '.join(cmd[:10])} ... (truncated)")

        # Prepare environment - Set DISPLAY for Chrome
        env = os.environ.copy()
        if use_display and display:
            env['DISPLAY'] = display
            logger.info(f"Setting DISPLAY={display} for Chrome")
        env['CHROME_LOG_FILE'] = '/dev/null'
        env['G_MESSAGES_DEBUG'] = ''
        env['DBUS_SESSION_BUS_ADDRESS'] = '/dev/null'
        env['GTK_MODULES'] = ''

        # Log file
        log_file = self.config.log_dir / f"chrome_{session['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        try:
            # Start Chrome with stderr captured to log file
            with open(log_file, 'w') as log_f:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=log_f,
                    start_new_session=True,
                    env=env,
                    text=True
                )

            # Wait for Chrome to start
            time.sleep(5)

            # Check if process died
            if process.poll() is not None:
                error_msg = ""
                if log_file.exists():
                    with open(log_file, 'r') as f:
                        error_msg = f.read(500)
                        if "cannot open display" in error_msg.lower():
                            console.print("[red]❌ Chrome cannot open display. Check VNC setup.[/red]")
                            console.print("[yellow]💡 Make sure VNC is running: vncserver :1[/yellow]")
                return False, None, f"Process died: {error_msg[:200]}"

            # Wait for DevTools - give it plenty of time
            devtools = ChromeDevTools(port=session['port'])
            if not devtools.wait_for_connection(timeout=self.config.devtools_connect_timeout):
                # Try to get error from log
                error_msg = ""
                if log_file.exists():
                    with open(log_file, 'r') as f:
                        error_msg = f.read(500)
                return False, None, f"DevTools connection timeout: {error_msg[:200]}"

            logger.info(f"✅ Chrome launched (PID: {process.pid})")

            # Now navigate to the URL if using display
            if use_display and session['url'] != "about:blank":
                try:
                    # Give Chrome a moment to fully load
                    time.sleep(3)
                    
                    tabs = devtools.get_tabs()
                    if tabs:
                        # Navigate using JavaScript
                        import websocket as ws_module
                        tab_id = tabs[0]['id']
                        ws_url = devtools.get_ws_urls()[0]['ws_url'] if devtools.get_ws_urls() else None
                        
                        if ws_url:
                            ws = ws_module.create_connection(ws_url, timeout=10)
                            try:
                                # Enable Runtime
                                ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
                                ws.recv()
                                
                                # Navigate
                                nav_script = f"window.location.href = '{session['url']}'"
                                msg_id = int(time.time() * 1000)
                                ws.send(json.dumps({
                                    "id": msg_id,
                                    "method": "Runtime.evaluate",
                                    "params": {
                                        "expression": nav_script,
                                        "returnByValue": True
                                    }
                                }))
                                ws.recv()
                                logger.info(f"Navigated to {session['url']}")
                            finally:
                                ws.close()
                except Exception as e:
                    logger.warning(f"Navigation failed: {e}")

            # Show success message with VNC info if available
            if self.display_manager.vnc_port:
                console.print(f"[green]📺 VNC available: vnc://127.0.0.1:{self.display_manager.vnc_port} (password: {self.config.vnc_password})[/green]")

            return True, process.pid, ""

        except Exception as e:
            return False, None, str(e)

# ============================================================================
# Session Lock Manager
# ============================================================================

class SessionLockManager:
    def __init__(self):
        self._locks: Dict[int, threading.RLock] = {}
        self._lock = threading.RLock()

    def acquire(self, session_id: int, timeout: float = 5.0) -> bool:
        with self._lock:
            if session_id not in self._locks:
                self._locks[session_id] = threading.RLock()
            lock = self._locks[session_id]
        return lock.acquire(timeout=timeout)

    def release(self, session_id: int):
        with self._lock:
            if session_id in self._locks:
                try:
                    self._locks[session_id].release()
                except RuntimeError:
                    pass

# ============================================================================
# Main Session Manager
# ============================================================================

class ChromeSessionManager:
    def __init__(self):
        self.config = Config()
        self.db = SessionDB()
        self._session_locks = SessionLockManager()
        self._devtools_lock = threading.RLock()
        self._cleanup_called = False
        self._session_start_times: Dict[int, float] = {}  # Track when sessions started

        # Initialize display
        self.display_manager = DisplayManager(self.config)
        self.display, self.vnc_port = self.display_manager.get_display()

        # Find Chrome
        self.chrome_path = self._find_chrome()
        self.launcher = ChromeLauncher(self.config, self.chrome_path, self.display_manager)
        self.devtools: Dict[int, ChromeDevTools] = {}
        self.js_manager = JavaScriptManager()

        # Cleanup stale sessions
        self._startup_cleanup()

        # Signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        atexit.register(self._cleanup)

        # Health monitor - now with longer intervals
        self._running = True
        self._health_thread = threading.Thread(target=self._health_loop, daemon=True)
        self._health_thread.start()

        # Show status
        if self.display:
            logger.info(f"✅ Using display: {self.display}")
            if self.vnc_port:
                console.print(f"[green]📺 VNC available: vnc://127.0.0.1:{self.vnc_port} (password: {self.config.vnc_password})[/green]")
            else:
                console.print(f"[green]✅ Using display: {self.display}")
        else:
            logger.info("⚠️ Running in headless mode")

    def _find_chrome(self):
        paths = [
            "chromium-browser", "chromium", "google-chrome",
            "google-chrome-stable", "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ]
        for path in paths:
            if shutil.which(path):
                return path
        raise RuntimeError("Chrome not found")

    def _startup_cleanup(self):
        sessions = self.db.list_sessions()
        cleaned = 0

        for session in sessions:
            if session['status'] == 'running':
                if session['pid']:
                    try:
                        os.kill(session['pid'], 0)
                        if not self.launcher._verify_pid_is_chrome(session['pid']):
                            self.db.stop_session(session['id'])
                            self.db.release_port(session['port'])
                            cleaned += 1
                    except OSError:
                        self.db.stop_session(session['id'])
                        self.db.release_port(session['port'])
                        cleaned += 1

        if cleaned:
            logger.info(f"Cleaned up {cleaned} stale sessions")

    def _signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        self._running = False
        self._cleanup()
        sys.exit(0)

    def _cleanup(self):
        if self._cleanup_called:
            return
        self._cleanup_called = True

        logger.info("Cleaning up resources...")

        sessions = self.db.list_sessions()
        for session in sessions:
            if session['status'] == 'running':
                self._stop_session_internal(session['id'])

        with self._devtools_lock:
            self.devtools.clear()

        logger.info("Cleanup complete")

    def _health_loop(self):
        """Health monitoring loop with generous timing"""
        while self._running:
            try:
                self._check_health()
                time.sleep(self.config.health_check_interval)
            except Exception as e:
                logger.error(f"Health check error: {e}", exc_info=True)

    def _check_health(self):
        """Check health of all running sessions"""
        sessions = self.db.list_sessions()
        for session in sessions:
            if session['status'] == 'running':
                self._check_session_health(session['id'])

    def _check_session_health(self, session_id: int):
        """Check health of a single session - VERY TOLERANT"""
        if not self._session_locks.acquire(session_id, timeout=2.0):
            return

        try:
            session = self.db.get_session(session_id)
            if not session or session['status'] != 'running':
                return

            # Check if session is still stabilizing
            if session_id in self._session_start_times:
                age = time.time() - self._session_start_times[session_id]
                if age < self.config.session_stabilization_time:
                    logger.debug(f"Session {session_id} is stabilizing ({age:.0f}s), skipping health check")
                    return

            # Check PID
            if session['pid']:
                try:
                    os.kill(session['pid'], 0)
                except OSError:
                    logger.warning(f"Session {session_id} PID {session['pid']} dead")
                    self._recover_session(session_id)
                    return

            # Check DevTools - with retries
            devtools = self._get_devtools(session['port'])
            
            # Try multiple times before marking unhealthy
            for attempt in range(3):
                if devtools._ensure_connection():
                    # Connection is healthy
                    return
                time.sleep(2)
            
            # If we get here, DevTools is not responding
            logger.warning(f"Session {session_id} DevTools not responding after 3 attempts")
            
            # Check if Chrome process is still there
            if session['pid']:
                try:
                    # Check if process is still running
                    proc = psutil.Process(session['pid'])
                    if proc.is_running():
                        # Process is running but DevTools not responding - might be loading
                        logger.info(f"Session {session_id} Chrome is running but DevTools not responding yet")
                        return
                except:
                    pass
            
            # Only recover if we're sure it's dead
            self._recover_session(session_id)

        except Exception as e:
            logger.error(f"Health check error for session {session_id}: {e}")
        finally:
            self._session_locks.release(session_id)

    def _recover_session(self, session_id: int):
        """Recover a session with backoff"""
        session = self.db.get_session(session_id)
        if not session:
            return

        restart_count = self.db.get_session_restart_count(session_id)
        if restart_count >= self.config.max_session_restarts:
            logger.error(f"Session {session_id} exceeded max restarts ({restart_count})")
            self._stop_session_internal(session_id)
            return

        backoff = self.config.restart_backoff_base ** (restart_count + 1)
        logger.info(f"Recovering session {session_id} after {backoff}s backoff (restart {restart_count + 1})")

        self._session_locks.release(session_id)
        try:
            time.sleep(backoff)
        finally:
            if not self._session_locks.acquire(session_id, timeout=self.config.session_lock_timeout):
                return

        self.db.increment_session_restart_count(session_id)
        self._stop_session_internal(session_id)
        time.sleep(2)
        self._start_session_internal(session_id)

    def _get_devtools(self, port: int) -> ChromeDevTools:
        with self._devtools_lock:
            if port not in self.devtools:
                self.devtools[port] = ChromeDevTools(port=port)
            return self.devtools[port]

    def start_session(self, session_id: int):
        if not self._session_locks.acquire(session_id, timeout=self.config.session_lock_timeout):
            logger.error(f"Could not acquire lock for session {session_id}")
            return

        try:
            self._start_session_internal(session_id)
        finally:
            self._session_locks.release(session_id)

    def _start_session_internal(self, session_id: int):
        session = self.db.get_session(session_id)
        if not session:
            logger.error(f"Session {session_id} not found")
            return

        if self._is_port_in_use(session['port']):
            new_port = self._get_next_port()
            logger.info(f"Port {session['port']} in use, using {new_port}")
            self.db.update_session_port(session_id, new_port)
            session['port'] = new_port

        logger.info(f"Starting session '{session['name']}'...")
        console.print(f"[blue]🚀 Starting session '{session['name']}' on port {session['port']}...[/blue]")

        profile_dir = session['profile_dir']
        os.makedirs(profile_dir, exist_ok=True)

        success, pid, error = self.launcher.launch_with_retry(session)

        if success:
            self.db.start_session(session_id, pid)
            self.db.reset_session_restart_count(session_id)
            
            # Record start time for stabilization
            self._session_start_times[session_id] = time.time()
            
            logger.info(f"Session {session_id} started (PID: {pid})")
            console.print(f"[green]✅ Session '{session['name']}' started![/green]")

            # Show connection info
            self._show_connection_info(session_id)
            
            # Give Chrome time to stabilize
            console.print(f"[dim]⏳ Chrome is starting up... Please wait {self.config.session_stabilization_time}s before interacting.[/dim]")
        else:
            logger.error(f"Failed to start session: {error}")
            console.print(f"[red]❌ Failed to start session: {error}[/red]")

    def _is_port_in_use(self, port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                return sock.connect_ex(('127.0.0.1', port)) == 0
        except:
            return False

    def _get_next_port(self) -> int:
        used_ports = set(self.db.get_all_ports())
        for port in range(self.config.debug_port_start, self.config.debug_port_end + 1):
            if port in used_ports:
                continue
            if self._is_port_in_use(port):
                continue
            return port
        raise RuntimeError("No available ports")

    def stop_session(self, session_id: int):
        if not self._session_locks.acquire(session_id, timeout=self.config.session_lock_timeout):
            logger.error(f"Could not acquire lock for session {session_id}")
            return

        try:
            self._stop_session_internal(session_id)
        finally:
            self._session_locks.release(session_id)

    def _stop_session_internal(self, session_id: int):
        session = self.db.get_session(session_id)
        if not session or session['status'] != 'running':
            return

        console.print(f"[yellow]⏹️ Stopping session '{session['name']}'...[/yellow]")

        if session['pid'] and self.launcher._verify_pid_is_chrome(session['pid']):
            try:
                os.kill(session['pid'], signal.SIGTERM)
                time.sleep(2)
                try:
                    os.kill(session['pid'], 0)
                    os.kill(session['pid'], signal.SIGKILL)
                except OSError:
                    pass
            except Exception as e:
                logger.error(f"Failed to kill process: {e}")

        self.db.stop_session(session_id)
        self.db.release_port(session['port'])

        with self._devtools_lock:
            if session['port'] in self.devtools:
                del self.devtools[session['port']]
        
        # Remove from start times
        if session_id in self._session_start_times:
            del self._session_start_times[session_id]

        logger.info(f"Session {session_id} stopped")
        console.print(f"[green]✅ Session '{session['name']}' stopped[/green]")

    def _show_connection_info(self, session_id: int):
        session = self.db.get_session(session_id)
        if not session:
            return

        console.print()
        console.print(Panel(f"[bold cyan]🔗 Connection Info - {session['name']}[/bold cyan]", border_style="green"))
        console.print(f"[bold]Port:[/bold] {session['port']}")
        console.print(f"[bold]Debug URL:[/bold] http://127.0.0.1:{session['port']}")

        if self.vnc_port:
            console.print(f"[bold]VNC:[/bold] vnc://127.0.0.1:{self.vnc_port} (password: {self.config.vnc_password})")
            console.print(f"[dim]   Use any VNC client to view Chrome GUI[/dim]")

        devtools = self._get_devtools(session['port'])
        ws_urls = devtools.get_ws_urls()

        if ws_urls:
            console.print()
            console.print("[bold cyan]WebSocket URLs:[/bold cyan]")
            for i, ws in enumerate(ws_urls, 1):
                console.print(f"  [{i}] {ws['title'][:50] or 'Untitled'}...")
                console.print(f"      [dim]{ws['ws_url']}[/dim]")
                console.print(f"      [dim]wscat --connect {ws['ws_url']}[/dim]")
        else:
            console.print()
            console.print("[yellow]No WebSocket URLs available[/yellow]")

    def list_sessions(self):
        sessions = self.db.list_sessions()
        if not sessions:
            console.print("[yellow]No sessions found[/yellow]")
            return

        # Fix stale sessions
        for session in sessions:
            if session['status'] == 'running' and session['pid']:
                if not self.launcher._verify_pid_is_chrome(session['pid']):
                    if self._session_locks.acquire(session['id'], timeout=1.0):
                        try:
                            self._stop_session_internal(session['id'])
                        finally:
                            self._session_locks.release(session['id'])

        sessions = self.db.list_sessions()

        table = Table(title="📋 Chrome Sessions", box=box.ROUNDED)
        table.add_column("ID", style="cyan", width=4)
        table.add_column("Name", style="green")
        table.add_column("URL", style="blue")
        table.add_column("Port", style="yellow", width=6)
        table.add_column("Status", style="magenta", width=10)
        table.add_column("PID", style="red", width=8)
        table.add_column("Connections", style="bright_blue", width=35)

        vnc_info = f"VNC:{self.vnc_port}" if self.vnc_port else ""

        for session in sessions:
            status_color = "green" if session['status'] == 'running' else "dim"

            conn_info = ""
            if session['status'] == 'running':
                conn_info = f"[bold cyan]ws://127.0.0.1:{session['port']}[/bold cyan]"
                if vnc_info:
                    conn_info += f"\n[dim]{vnc_info}[/dim]"

            table.add_row(
                str(session['id']),
                session['name'],
                session['url'][:30] + "..." if len(session['url']) > 30 else session['url'],
                str(session['port']),
                f"[{status_color}]{session['status']}[/{status_color}]",
                str(session['pid']) if session['pid'] else "-",
                conn_info or "[dim]N/A[/dim]"
            )

        console.print(table)

    def create_session(self):
        console.print()
        console.print(Panel("🆕 Create New Chrome Session", style="bold green"))

        while True:
            name = Prompt.ask("📝 Session name")
            if not name:
                console.print("[red]Name cannot be empty[/red]")
                continue
            if self.db.get_session_by_name(name):
                console.print(f"[red]Session '{name}' already exists[/red]")
                continue
            break

        url = Prompt.ask("🌐 Website URL", default="https://web.whatsapp.com")
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        port = self._get_next_port()
        console.print(f"[green]Auto-assigned port: {port}[/green]")

        profile_dir = os.path.join(self.config.base_profile_dir, name)
        os.makedirs(profile_dir, exist_ok=True)

        try:
            session_id = self.db.create_session(name, url, port, profile_dir)
        except Exception as e:
            console.print(f"[red]Error creating session: {e}[/red]")
            if "UNIQUE constraint failed" in str(e):
                new_port = self._get_next_port()
                console.print(f"[green]Using port: {new_port}[/green]")
                session_id = self.db.create_session(name, url, new_port, profile_dir)
                port = new_port

        console.print()
        console.print(f"[green]✅ Session created! ID: {session_id}[/green]")
        console.print(f"   Name: {name}")
        console.print(f"   URL: {url}")
        console.print(f"   Port: {port}")
        console.print(f"   Profile: {profile_dir}")

        if Confirm.ask("🚀 Start this session now?"):
            self.start_session(session_id)

    def delete_session(self, session_id: int):
        session = self.db.get_session(session_id)
        if not session:
            console.print(f"[red]Session not found[/red]")
            return

        if session['status'] == 'running':
            console.print(f"[yellow]Session is running. Stop it first.[/yellow]")
            if Confirm.ask("Stop and delete?"):
                self.stop_session(session_id)
                time.sleep(1)
            else:
                return

        if Confirm.ask(f"Delete session '{session['name']}'?"):
            if os.path.exists(session['profile_dir']):
                try:
                    shutil.rmtree(session['profile_dir'], ignore_errors=True)
                except:
                    pass
            self.db.delete_session(session_id)
            console.print(f"[green]✅ Session deleted[/green]")

    def show_session_details(self, session_id: int):
        session = self.db.get_session(session_id)
        if not session:
            console.print(f"[red]Session not found[/red]")
            return

        content = f"""
[bold cyan]Session Details[/bold cyan]

[bold]ID:[/bold] {session['id']}
[bold]Name:[/bold] {session['name']}
[bold]URL:[/bold] {session['url']}
[bold]Port:[/bold] {session['port']}
[bold]Status:[/bold] {session['status']}
[bold]PID:[/bold] {session['pid'] if session['pid'] else 'N/A'}
[bold]Restart Count:[/bold] {session.get('restart_count', 0)}
[bold]Profile Directory:[/bold] {session['profile_dir']}
[bold]Created:[/bold] {session['created_at']}
[bold]Last Used:[/bold] {session['last_used'] if session['last_used'] else 'Never'}
"""
        console.print(Panel(content, title="📊 Session Details", border_style="blue"))

    def show_dashboard(self):
        sessions = self.db.list_sessions()
        running = [s for s in sessions if s['status'] == 'running']
        stopped = [s for s in sessions if s['status'] == 'stopped']

        display_status = "❌ None"
        if self.display:
            display_status = f"✅ {self.display}"
            if self.vnc_port:
                display_status += f"\n   VNC: vnc://127.0.0.1:{self.vnc_port}"

        content = f"""
[bold green]📊 Chrome Session Dashboard[/bold green]

[bold]Overview:[/bold]
  Total Sessions: {len(sessions)}
  🟢 Running: {len(running)}
  ⚪ Stopped: {len(stopped)}
  🔌 Available Ports: {len(self.db.get_available_ports())}
  📜 Saved Scripts: {len(self.js_manager.list_scripts())}

[bold]Display:[/bold]
  🖥️ Display: {display_status}
  📺 VNC Password: {self.config.vnc_password}

[bold]Storage:[/bold]
  📁 Base Directory: {self.config.base_profile_dir}
  🔧 Chrome: {self.chrome_path}
  📁 Log Directory: {self.config.log_dir}
"""
        console.print(Panel(content, title="Dashboard", border_style="cyan"))

    def show_connection_info(self, session_id: int):
        self._show_connection_info(session_id)

    def manage_tabs(self, session_id: int):
        session = self.db.get_session(session_id)
        if not session:
            console.print("[red]Session not found[/red]")
            return

        if session['status'] != 'running':
            console.print("[red]Session not running[/red]")
            return

        devtools = self._get_devtools(session['port'])

        if not devtools._ensure_connection():
            console.print(f"[red]Cannot connect to Chrome on port {session['port']}[/red]")
            return

        console.clear()
        console.print(Panel(f"📑 Tab Manager - {session['name']} (Port: {session['port']})", style="cyan"))

        tabs = devtools.get_tabs()
        if tabs:
            table = Table(title=f"Open Tabs ({len(tabs)})", box=box.ROUNDED)
            table.add_column("#", style="cyan", width=4)
            table.add_column("Title", style="green")
            table.add_column("URL", style="blue")

            for i, tab in enumerate(tabs, 1):
                table.add_row(
                    str(i),
                    tab.get('title', 'Untitled')[:60],
                    tab.get('url', '')[:70]
                )
            console.print(table)
        else:
            console.print("[yellow]No tabs open[/yellow]")

        console.print()
        Prompt.ask("Press Enter to continue...")

    def interactive_menu(self):
        while True:
            console.clear()
            console.print()

            header = """
╔══════════════════════════════════════════════════════════════╗
║           🌐 Chrome Session Manager - Production v14       ║
║        Stable | Tolerant Health Checks                    ║
╚══════════════════════════════════════════════════════════════╝
            """
            console.print(Panel(header, border_style="cyan"))

            self.list_sessions()

            console.print()
            menu = Table(show_header=False, box=box.MINIMAL_HEAVY_HEAD)
            menu.add_column("Option", style="cyan", width=8)
            menu.add_column("Action", style="white")
            menu.add_column("Description", style="dim")

            menu.add_row("1", "[green]Create Session[/green]", "Create a new Chrome session")
            menu.add_row("2", "[blue]Start Session[/blue]", "Start an existing session")
            menu.add_row("3", "[yellow]Stop Session[/yellow]", "Stop a running session")
            menu.add_row("4", "[magenta]List Sessions[/magenta]", "Show all sessions")
            menu.add_row("5", "[cyan]Session Details[/cyan]", "Show detailed session info")
            menu.add_row("6", "[red]Delete Session[/red]", "Delete a session")
            menu.add_row("7", "[white]Dashboard[/white]", "Show comprehensive dashboard")
            menu.add_row("8", "[bold]Manage Tabs[/bold]", "Advanced tab control")
            menu.add_row("C", "[bold]Connection Info[/bold]", "Show connection info")
            menu.add_row("0", "[red]Exit[/red]", "Exit the manager")

            console.print(menu)
            console.print()

            choice = Prompt.ask("Select option", choices=["0", "1", "2", "3", "4", "5", "6", "7", "8", "C"])

            if choice == "0":
                console.print("[green]Goodbye! 👋[/green]")
                break

            elif choice == "1":
                self.create_session()

            elif choice == "2":
                try:
                    session_id = int(Prompt.ask("Enter session ID to start"))
                    self.start_session(session_id)
                except ValueError:
                    console.print("[red]Invalid ID[/red]")

            elif choice == "3":
                try:
                    session_id = int(Prompt.ask("Enter session ID to stop"))
                    self.stop_session(session_id)
                except ValueError:
                    console.print("[red]Invalid ID[/red]")

            elif choice == "4":
                self.list_sessions()

            elif choice == "5":
                try:
                    session_id = int(Prompt.ask("Enter session ID"))
                    self.show_session_details(session_id)
                except ValueError:
                    console.print("[red]Invalid ID[/red]")

            elif choice == "6":
                try:
                    session_id = int(Prompt.ask("Enter session ID to delete"))
                    self.delete_session(session_id)
                except ValueError:
                    console.print("[red]Invalid ID[/red]")

            elif choice == "7":
                self.show_dashboard()

            elif choice == "8":
                try:
                    session_id = int(Prompt.ask("Enter session ID for tab management"))
                    self.manage_tabs(session_id)
                except ValueError:
                    console.print("[red]Invalid ID[/red]")

            elif choice == "C":
                try:
                    session_id = int(Prompt.ask("Enter session ID for connection info"))
                    self.show_connection_info(session_id)
                except ValueError:
                    console.print("[red]Invalid ID[/red]")

            if choice != "0":
                console.print()
                Prompt.ask("Press Enter to continue...")

# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    try:
        manager = ChromeSessionManager()
        manager.interactive_menu()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Fatal error")
        sys.exit(1)

if __name__ == "__main__":
    main()
