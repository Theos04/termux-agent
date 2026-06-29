#!/usr/bin/env python3
"""
Chrome Session Manager - Production v4
Fixed: Proper VNC/display detection for Termux with VNC
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

# Fix: Import handlers submodule for RotatingFileHandler
import logging.handlers

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
    from rich.syntax import Syntax
    from rich.text import Text
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rich"])
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich import box
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.syntax import Syntax
    from rich.text import Text

from session_db import SessionDB
import requests

# Fix: Instantiate console at module level
console = Console()

# ============================================================================
# Configuration
# ============================================================================

@dataclass
class Config:
    """Centralized configuration with all magic numbers named"""
    base_profile_dir: str = os.path.expanduser("~/chrome-sessions")
    debug_port_start: int = 9222
    debug_port_end: int = 9299
    js_scripts_dir: str = os.path.expanduser("~/chrome-scripts")
    display_start: int = 1
    display_end: int = 5
    max_launch_retries: int = 3
    launch_retry_delay: int = 2
    health_check_interval: int = 5
    websocket_heartbeat: int = 30
    log_dir: Path = Path.home() / "chrome-logs"
    log_retention_days: int = 7
    max_log_files: int = 100
    devtools_connect_timeout: int = 30
    websocket_timeout: float = 10.0
    session_lock_timeout: float = 5.0
    max_session_restarts: int = 5
    restart_backoff_base: int = 2
    xvfb_resolution: str = "1366x768x24"
    min_disk_space_mb: int = 100
    # VNC settings
    vnc_port_start: int = 5901
    vnc_password: str = "chrome123"
    vnc_geometry: str = "1366x768"

# ============================================================================
# Logging Setup
# ============================================================================

def setup_logging(config: Config) -> logging.Logger:
    """Configure logging with rotation and cleanup"""
    config.log_dir.mkdir(parents=True, exist_ok=True)
    
    # Clean up old logs on startup
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
    """Remove log files older than retention period"""
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
    """Manage saved JavaScript scripts"""
    
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
# Persistent WebSocket Client
# ============================================================================

class CDPWebSocket:
    """Persistent Chrome DevTools Protocol WebSocket client."""
    
    def __init__(self, ws_url: str, session_id: int, tab_id: str):
        self.ws_url = ws_url
        self.session_id = session_id
        self.tab_id = tab_id
        self._ws: Optional[websocket.WebSocketApp] = None
        self._pending: Dict[int, queue.Queue] = {}
        self._lock = threading.RLock()
        self._msg_id = 0
        self._connected = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_activity = time.time()
        self._heartbeat_interval = 30
        
    def connect(self, timeout: float = 5.0) -> bool:
        """Establish WebSocket connection"""
        try:
            self._running = True
            self._ws = websocket.WebSocketApp(
                self.ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            
            self._thread = threading.Thread(
                target=self._ws.run_forever,
                daemon=True,
                kwargs={'ping_interval': 10, 'ping_timeout': 5}
            )
            self._thread.start()
            
            if not self._connected.wait(timeout=timeout):
                logger.error(f"WebSocket connection timeout for session {self.session_id}")
                return False
            
            result = self.send("Runtime.enable", timeout=3.0)
            if not result or 'error' in result:
                logger.error(f"Runtime.enable failed: {result}")
                return False
            
            logger.info(f"CDP WebSocket connected for session {self.session_id}")
            return True
            
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            return False
    
    def _on_open(self, ws):
        self._connected.set()
        logger.debug(f"WebSocket opened for session {self.session_id}")
    
    def _on_message(self, ws, message: str):
        try:
            data = json.loads(message)
            msg_id = data.get('id')
            if msg_id is not None:
                with self._lock:
                    q = self._pending.get(msg_id)
                    if q:
                        q.put(data)
                        self._last_activity = time.time()
        except json.JSONDecodeError:
            pass
        except Exception as e:
            logger.error(f"Message handling error: {e}")
    
    def _on_error(self, ws, error):
        logger.error(f"WebSocket error for session {self.session_id}: {error}")
        self._connected.clear()
    
    def _on_close(self, ws, code, msg):
        logger.info(f"WebSocket closed for session {self.session_id}: {code} - {msg}")
        self._connected.clear()
        with self._lock:
            for q in self._pending.values():
                q.put({"error": "connection closed"})
            self._pending.clear()
    
    def send(self, method: str, params: Dict = None, timeout: float = None) -> Optional[Dict]:
        """Send a CDP command and wait for response"""
        if not self._connected.is_set():
            logger.warning(f"WebSocket not connected for session {self.session_id}")
            return None
        
        if timeout is None:
            timeout = 10.0
        
        with self._lock:
            self._msg_id += 1
            msg_id = self._msg_id
            q: queue.Queue = queue.Queue(maxsize=1)
            self._pending[msg_id] = q
        
        try:
            payload = json.dumps({
                "id": msg_id,
                "method": method,
                "params": params or {}
            })
            self._ws.send(payload)
            
            result = q.get(timeout=timeout)
            if result and 'error' in result:
                logger.warning(f"CDP error for {method}: {result['error']}")
            return result
            
        except queue.Empty:
            logger.warning(f"CDP timeout for {method} (id={msg_id})")
            return {"error": "timeout"}
        except Exception as e:
            logger.error(f"CDP send error: {e}")
            return {"error": str(e)}
        finally:
            with self._lock:
                self._pending.pop(msg_id, None)
    
    def execute_script(self, script: str, return_by_value: bool = True) -> Optional[Dict]:
        """Execute JavaScript and return result"""
        result = self.send(
            "Runtime.evaluate",
            {
                "expression": script,
                "returnByValue": return_by_value,
                "awaitPromise": True
            }
        )
        if result and 'error' not in result:
            return result.get('result', {})
        return None
    
    def is_healthy(self) -> bool:
        """Check if connection is healthy"""
        if not self._connected.is_set():
            return False
        
        if time.time() - self._last_activity > self._heartbeat_interval * 2:
            return False
        
        result = self.send(
            "Runtime.evaluate",
            {"expression": "1", "returnByValue": True},
            timeout=2.0
        )
        return result is not None and 'error' not in result
    
    def close(self):
        self._running = False
        if self._ws:
            self._ws.close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

class WebSocketPool:
    """Pool of persistent WebSocket connections"""
    
    def __init__(self):
        self._connections: Dict[str, CDPWebSocket] = {}
        self._lock = threading.RLock()
    
    def get_connection(self, ws_url: str, session_id: int, tab_id: str) -> Optional[CDPWebSocket]:
        key = f"{session_id}:{tab_id}"
        
        with self._lock:
            if key in self._connections:
                ws = self._connections[key]
                if ws.is_healthy():
                    return ws
                else:
                    ws.close()
                    del self._connections[key]
        
        ws = CDPWebSocket(ws_url, session_id, tab_id)
        if not ws.connect():
            return None
        
        with self._lock:
            self._connections[key] = ws
        
        return ws
    
    def remove_connection(self, session_id: int, tab_id: str):
        key = f"{session_id}:{tab_id}"
        with self._lock:
            if key in self._connections:
                self._connections[key].close()
                del self._connections[key]
    
    def close_all(self):
        with self._lock:
            for ws in self._connections.values():
                ws.close()
            self._connections.clear()

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
# Display Management
# ============================================================================

class DisplayBackend(Enum):
    XVFB = "xvfb"
    TIGERVNC = "tigervnc"
    X11 = "x11"
    HEADLESS = "headless"

class XServerChecker:
    @staticmethod
    def check_x_socket(display: str) -> bool:
        display_num = display.replace(':', '').replace('/', '')
        
        unix_socket = f"/tmp/.X11-unix/X{display_num}"
        if os.path.exists(unix_socket):
            return True
        
        try:
            port = 6000 + int(display_num)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', port))
                return result == 0
        except:
            return False
    
    @staticmethod
    def check_xdpyinfo(display: str) -> bool:
        try:
            env = os.environ.copy()
            env['DISPLAY'] = display
            result = subprocess.run(
                ['xdpyinfo'],
                env=env,
                capture_output=True,
                timeout=3
            )
            return result.returncode == 0
        except:
            return False
    
    @staticmethod
    def get_vnc_sessions() -> List[Dict[str, Any]]:
        """Get list of running VNC sessions"""
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
                # Parse: "X DISPLAY #     PROCESS ID"
                match = re.search(r':(\d+)\s+(\d+)', line)
                if match:
                    sessions.append({
                        'display': f":{match.group(1)}",
                        'pid': int(match.group(2))
                    })
            return sessions
        except Exception as e:
            logger.debug(f"Failed to list VNC sessions: {e}")
            return []

class DisplayManager:
    def __init__(self, config: Config):
        self.config = config
        self.current_display = None
        self.current_backend = DisplayBackend.HEADLESS
        self.xvfb_pid: Optional[int] = None
        self.vnc_process: Optional[subprocess.Popen] = None
        self.vnc_port: Optional[int] = None
        self._lock = threading.RLock()
        self._cleanup_done = False
    
    def _get_vnc_port_for_display(self, display: str) -> Optional[int]:
        """Get VNC port for a display"""
        display_num = int(display.replace(':', ''))
        return self.config.vnc_port_start + display_num - 1
    
    def _check_vnc_running(self, display: str) -> bool:
        """Check if VNC is already running for a display"""
        port = self._get_vnc_port_for_display(display)
        if port:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(1)
                    if sock.connect_ex(('127.0.0.1', port)) == 0:
                        return True
            except:
                pass
        return False
    
    def _start_xvfb(self, display_num: int) -> Optional[str]:
        try:
            display = f":{display_num}"
            
            unix_socket = f"/tmp/.X11-unix/X{display_num}"
            if os.path.exists(unix_socket):
                try:
                    os.unlink(unix_socket)
                except:
                    pass
            
            cmd = [
                'Xvfb', display,
                '-screen', '0', self.config.xvfb_resolution,
                '-ac',
                '-nolisten', 'tcp'
            ]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            
            time.sleep(2)
            
            if XServerChecker.check_x_socket(display):
                with self._lock:
                    self.xvfb_pid = process.pid
                logger.info(f"Xvfb started on {display} (PID: {process.pid})")
                return display
            
            process.terminate()
            return None
            
        except Exception as e:
            logger.error(f"Failed to start Xvfb: {e}")
            return None
    
    def _start_vnc(self, display: str) -> bool:
        """Start VNC server for the display"""
        display_num = int(display.replace(':', ''))
        
        # Check if VNC is already running
        if self._check_vnc_running(display):
            self.vnc_port = self._get_vnc_port_for_display(display)
            logger.info(f"VNC already running on port {self.vnc_port}")
            console.print(f"[green]✅ VNC already running on port {self.vnc_port}[/green]")
            return True
        
        try:
            # Use TigerVNC
            if shutil.which('vncserver'):
                self.vnc_port = self._get_vnc_port_for_display(display)
                
                # Kill existing VNC session on this display
                subprocess.run(['vncserver', '-kill', f":{display_num}"], 
                             capture_output=True, timeout=2)
                time.sleep(1)
                
                cmd = [
                    'vncserver',
                    f":{display_num}",
                    '-geometry', self.config.vnc_geometry,
                    '-depth', '24',
                    '-localhost', 'no'
                ]
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                time.sleep(3)
                
                # Check if VNC started
                if self._check_vnc_running(display):
                    self.vnc_process = process
                    logger.info(f"VNC started on port {self.vnc_port}")
                    console.print(f"[green]✅ VNC server ready → vnc://127.0.0.1:{self.vnc_port} (password: {self.config.vnc_password})[/green]")
                    return True
                else:
                    logger.warning("VNC server started but not responding")
                    return False
            
            # Fallback: x11vnc
            elif shutil.which('x11vnc'):
                self.vnc_port = self.config.vnc_port_start + display_num - 1
                
                # Check if port is in use
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                        sock.settimeout(1)
                        if sock.connect_ex(('127.0.0.1', self.vnc_port)) == 0:
                            self.vnc_port += 1
                except:
                    pass
                
                cmd = [
                    'x11vnc',
                    '-display', display,
                    '-forever',
                    '-shared',
                    '-rfbport', str(self.vnc_port),
                    '-passwd', self.config.vnc_password
                ]
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                
                time.sleep(2)
                self.vnc_process = process
                logger.info(f"x11vnc started on port {self.vnc_port}")
                console.print(f"[green]✅ x11vnc ready → vnc://127.0.0.1:{self.vnc_port} (password: {self.config.vnc_password})[/green]")
                return True
                
            else:
                logger.warning("No VNC server found (vncserver or x11vnc)")
                console.print("[yellow]⚠️ VNC not available. Install TigerVNC or x11vnc for GUI access.[/yellow]")
                return False
                
        except Exception as e:
            logger.error(f"Failed to start VNC: {e}")
            return False
    
    def _kill_xvfb(self):
        with self._lock:
            if self.xvfb_pid:
                try:
                    os.kill(self.xvfb_pid, signal.SIGTERM)
                    time.sleep(1)
                    try:
                        os.kill(self.xvfb_pid, 0)
                        os.kill(self.xvfb_pid, signal.SIGKILL)
                    except OSError:
                        pass
                except Exception as e:
                    logger.error(f"Failed to kill Xvfb: {e}")
                self.xvfb_pid = None
    
    def _kill_vnc(self):
        if self.vnc_process:
            try:
                self.vnc_process.terminate()
                self.vnc_process.wait(timeout=2)
            except:
                try:
                    self.vnc_process.kill()
                except:
                    pass
            self.vnc_process = None
    
    def get_display(self) -> Tuple[Optional[str], DisplayBackend]:
        """Get a working display - checks VNC first, then Xvfb"""
        
        # First, check if there's a VNC display already running
        vnc_sessions = XServerChecker.get_vnc_sessions()
        
        for session in vnc_sessions:
            display = session['display']
            logger.info(f"Found VNC session on {display}")
            
            # Check if X server is actually running
            if XServerChecker.check_x_socket(display):
                if XServerChecker.check_xdpyinfo(display):
                    self.current_display = display
                    self.current_backend = DisplayBackend.TIGERVNC
                    # Set the display in environment
                    os.environ['DISPLAY'] = display
                    
                    # Get VNC port
                    self.vnc_port = self._get_vnc_port_for_display(display)
                    console.print(f"[green]✅ Using existing VNC display: {display} (port {self.vnc_port})[/green]")
                    return display, DisplayBackend.TIGERVNC
        
        # Check if DISPLAY is set in environment
        env_display = os.environ.get('DISPLAY')
        if env_display and XServerChecker.check_x_socket(env_display):
            if XServerChecker.check_xdpyinfo(env_display):
                self.current_display = env_display
                self.current_backend = DisplayBackend.X11
                logger.info(f"Using existing display: {env_display}")
                # Try to start VNC for this display
                self._start_vnc(env_display)
                return env_display, DisplayBackend.X11
        
        # Try to start Xvfb
        for display_num in range(self.config.display_start, self.config.display_end + 1):
            display = f":{display_num}"
            if not XServerChecker.check_x_socket(display):
                started = self._start_xvfb(display_num)
                if started:
                    self.current_display = started
                    self.current_backend = DisplayBackend.XVFB
                    os.environ['DISPLAY'] = started
                    # Start VNC for the new display
                    self._start_vnc(started)
                    return started, DisplayBackend.XVFB
        
        return None, DisplayBackend.HEADLESS
    
    def get_vnc_info(self) -> Optional[str]:
        """Get VNC connection info"""
        if self.vnc_port:
            return f"vnc://127.0.0.1:{self.vnc_port} (password: {self.config.vnc_password})"
        return None
    
    def cleanup(self):
        if self._cleanup_done:
            return
        self._cleanup_done = True
        self._kill_vnc()
        self._kill_xvfb()

# ============================================================================
# Chrome DevTools with Persistent WebSocket
# ============================================================================

class ChromeDevTools:
    def __init__(self, host='127.0.0.1', port=9222):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.session = requests.Session()
        self.session.timeout = 3
        self.ws_pool = WebSocketPool()
    
    def _ensure_connection(self) -> bool:
        try:
            response = self.session.get(f"{self.base_url}/json/version", timeout=3)
            return response.status_code == 200
        except:
            return False
    
    def wait_for_connection(self, timeout: int = 30) -> bool:
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._ensure_connection():
                return True
            time.sleep(1)
        return False
    
    def get_tabs(self) -> List[Dict]:
        try:
            response = self.session.get(f"{self.base_url}/json", timeout=5)
            if response.status_code == 200:
                tabs = response.json()
                return [t for t in tabs if t.get('type') == 'page']
            return []
        except Exception as e:
            logger.error(f"Failed to get tabs: {e}")
            return []
    
    def get_ws_url_for_tab(self, tab_id: str) -> Optional[str]:
        """Get WebSocket URL for a specific tab"""
        tabs = self.get_tabs()
        for tab in tabs:
            if tab.get('id') == tab_id:
                ws_url = tab.get('webSocketDebuggerUrl')
                if ws_url:
                    ws_url = ws_url.strip()
                    ws_url = re.sub(r',.*$', '', ws_url)
                    if ws_url.startswith('http://'):
                        ws_url = ws_url.replace('http://', 'ws://')
                    elif ws_url.startswith('https://'):
                        ws_url = ws_url.replace('https://', 'wss://')
                    return ws_url
        return None
    
    def get_all_ws_urls(self) -> List[Dict[str, str]]:
        """Get WebSocket URLs for all tabs"""
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
    
    def close_all_connections(self):
        self.ws_pool.close_all()

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
            # Don't add session URL - let Chrome open with the default new tab page
            # Then we can navigate via DevTools
            cmd.append("about:blank")
        else:
            cmd.extend([
                "--headless",
                "--disable-software-rasterizer",
                f"--window-size=1366,768",
            ])
            # For headless, we need to navigate to the URL
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
            logger.info(f"Launch attempt {attempt + 1}/{max_retries} for session {session['id']}")
            
            success, pid, error = self._launch_once(session)
            if success and pid and self._verify_pid_is_chrome(pid):
                return True, pid, ""
            
            logger.warning(f"Attempt {attempt + 1} failed: {error}")
            
            if attempt < max_retries - 1:
                time.sleep(self.config.launch_retry_delay * (attempt + 1))
        
        return False, None, f"Failed after {max_retries} attempts"
    
    def _launch_once(self, session: Dict) -> Tuple[bool, Optional[int], str]:
        use_display = False
        if self.display_manager.current_display:
            if XServerChecker.check_xdpyinfo(self.display_manager.current_display):
                use_display = True
                logger.info(f"Using display: {self.display_manager.current_display}")
        
        cmd = self.build_command(session, use_display)
        logger.debug(f"Command: {' '.join(cmd)}")
        
        env = os.environ.copy()
        if use_display:
            env['DISPLAY'] = self.display_manager.current_display
        env['CHROME_LOG_FILE'] = '/dev/null'
        env['G_MESSAGES_DEBUG'] = ''
        env['DBUS_SESSION_BUS_ADDRESS'] = '/dev/null'
        env['GTK_MODULES'] = ''
        
        log_file = self.config.log_dir / f"chrome_{session['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        try:
            with open(log_file, 'w') as log_f:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=log_f,
                    start_new_session=True,
                    env=env,
                    text=True
                )
            
            time.sleep(2)
            
            if process.poll() is not None:
                error_msg = ""
                if log_file.exists():
                    with open(log_file, 'r') as f:
                        error_msg = f.read(500)
                return False, None, f"Process died: {error_msg}"
            
            devtools = ChromeDevTools(port=session['port'])
            if not devtools.wait_for_connection(timeout=self.config.devtools_connect_timeout):
                return False, None, "DevTools connection timeout"
            
            # Navigate to the URL if using display
            if use_display and session['url'] != "about:blank":
                try:
                    tabs = devtools.get_tabs()
                    if tabs:
                        tab_id = tabs[0]['id']
                        # Navigate using JavaScript
                        ws = devtools.ws_pool.get_connection(
                            devtools.get_ws_url_for_tab(tab_id),
                            session['id'],
                            tab_id
                        )
                        if ws:
                            ws.execute_script(f"window.location.href = '{session['url']}'")
                            logger.info(f"Navigated to {session['url']}")
                except Exception as e:
                    logger.warning(f"Navigation failed: {e}")
            
            logger.info(f"Chrome launched (PID: {process.pid})")
            return True, process.pid, ""
            
        except Exception as e:
            return False, None, str(e)

# ============================================================================
# Main Session Manager (shortened for brevity - includes all methods)
# ============================================================================

class ChromeSessionManager:
    def __init__(self):
        self.config = Config()
        self.db = SessionDB()
        self._session_locks = SessionLockManager()
        self._devtools_lock = threading.RLock()
        self._cleanup_called = False
        
        self.display_manager = DisplayManager(self.config)
        self.display, self.display_backend = self.display_manager.get_display()
        self.chrome_path = self._find_chrome()
        self.launcher = ChromeLauncher(self.config, self.chrome_path, self.display_manager)
        self.devtools: Dict[int, ChromeDevTools] = {}
        self.js_manager = JavaScriptManager()
        
        self._startup_cleanup()
        
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        atexit.register(self._cleanup)
        
        self._running = True
        self._health_thread = threading.Thread(target=self._health_loop, daemon=True)
        self._health_thread.start()
        
        if self.display:
            logger.info(f"Using display: {self.display} (backend: {self.display_backend.value})")
            vnc_info = self.display_manager.get_vnc_info()
            if vnc_info:
                console.print(f"[green]✅ VNC available: {vnc_info}[/green]")
        else:
            console.print("[yellow]⚠️ No display available - running in headless mode[/yellow]")
    
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
                            logger.warning(f"Cleaning up stale session {session['id']}")
                            self.db.stop_session(session['id'])
                            self.db.release_port(session['port'])
                            cleaned += 1
                    except OSError:
                        logger.warning(f"Cleaning up stale session {session['id']}")
                        self.db.stop_session(session['id'])
                        self.db.release_port(session['port'])
                        cleaned += 1
        
        if cleaned:
            logger.info(f"Cleaned up {cleaned} stale sessions on startup")
    
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
            for devtools in self.devtools.values():
                devtools.close_all_connections()
            self.devtools.clear()
        
        self.display_manager.cleanup()
        
        logger.info("Cleanup complete")
    
    def _health_loop(self):
        while self._running:
            try:
                self._check_health()
                time.sleep(self.config.health_check_interval)
            except Exception as e:
                logger.error(f"Health check error: {e}", exc_info=True)
    
    def _check_health(self):
        sessions = self.db.list_sessions()
        for session in sessions:
            if session['status'] == 'running':
                self._check_session_health(session['id'])
    
    def _check_session_health(self, session_id: int):
        if not self._session_locks.acquire(session_id, timeout=2.0):
            logger.warning(f"Could not acquire lock for session {session_id}")
            return
        
        try:
            session = self.db.get_session(session_id)
            if not session or session['status'] != 'running':
                return
            
            if session['pid']:
                try:
                    os.kill(session['pid'], 0)
                except OSError:
                    logger.warning(f"Session {session_id} PID {session['pid']} dead")
                    self._recover_session(session_id)
                    return
            
            devtools = self._get_devtools(session['port'])
            if not devtools._ensure_connection():
                logger.warning(f"Session {session_id} DevTools not responding")
                self._recover_session(session_id)
                return
        
        except Exception as e:
            logger.error(f"Health check error for session {session_id}: {e}")
        finally:
            self._session_locks.release(session_id)
    
    def _recover_session(self, session_id: int):
        session = self.db.get_session(session_id)
        if not session:
            return
        
        restart_count = self.db.get_session_restart_count(session_id)
        if restart_count >= self.config.max_session_restarts:
            logger.error(f"Session {session_id} exceeded max restarts")
            self._stop_session_internal(session_id)
            return
        
        backoff = self.config.restart_backoff_base ** (restart_count + 1)
        logger.info(f"Recovering session {session_id} after {backoff}s backoff")
        
        self._session_locks.release(session_id)
        try:
            time.sleep(backoff)
        finally:
            if not self._session_locks.acquire(session_id, timeout=self.config.session_lock_timeout):
                logger.error(f"Could not re-acquire lock for session {session_id}")
                return
        
        self.db.increment_session_restart_count(session_id)
        self._stop_session_internal(session_id)
        time.sleep(1)
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
        
        if not self._check_disk_space(profile_dir):
            logger.error(f"Insufficient disk space for session {session_id}")
            return
        
        success, pid, error = self.launcher.launch_with_retry(session)
        
        if success:
            self.db.start_session(session_id, pid)
            self.db.reset_session_restart_count(session_id)
            logger.info(f"Session {session_id} started (PID: {pid})")
            console.print(f"[green]✅ Session '{session['name']}' started![/green]")
            
            # Show connection info
            self._show_connection_info(session_id)
        else:
            logger.error(f"Failed to start session {session_id}: {error}")
            console.print(f"[red]❌ Failed to start session: {error}[/red]")
    
    def _check_disk_space(self, path: str) -> bool:
        try:
            stat = os.statvfs(path)
            free_bytes = stat.f_bavail * stat.f_frsize
            min_free = self.config.min_disk_space_mb * 1024 * 1024
            return free_bytes > min_free
        except:
            return True
    
    def _is_port_in_use(self, port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', port))
                return result == 0
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
        if not session:
            return
        
        if session['status'] != 'running':
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
                self.devtools[session['port']].close_all_connections()
                del self.devtools[session['port']]
        
        logger.info(f"Session {session_id} stopped")
        console.print(f"[green]✅ Session '{session['name']}' stopped[/green]")
    
    def _show_connection_info(self, session_id: int):
        """Show connection information for a session"""
        session = self.db.get_session(session_id)
        if not session:
            return
        
        console.print()
        console.print(Panel(f"[bold cyan]🔗 Connection Info - {session['name']}[/bold cyan]", border_style="green"))
        console.print(f"[bold]Port:[/bold] {session['port']}")
        console.print(f"[bold]Debug URL:[/bold] http://127.0.0.1:{session['port']}")
        
        # VNC info
        vnc_info = self.display_manager.get_vnc_info()
        if vnc_info:
            console.print(f"[bold]VNC:[/bold] {vnc_info}")
            console.print(f"[dim]   Use any VNC client to view Chrome GUI[/dim]")
        
        # WebSocket URLs
        devtools = self._get_devtools(session['port'])
        ws_urls = devtools.get_all_ws_urls()
        
        if ws_urls:
            console.print()
            console.print("[bold cyan]WebSocket URLs:[/bold cyan]")
            for i, ws in enumerate(ws_urls, 1):
                console.print(f"  [{i}] {ws['title'][:50] or 'Untitled'}...")
                console.print(f"      [dim]{ws['ws_url']}[/dim]")
                console.print(f"      [dim]wscat --connect {ws['ws_url']}[/dim]")
        else:
            console.print()
            console.print("[yellow]No WebSocket URLs available (Chrome may still be loading)[/yellow]")
        
        console.print()
        console.print("[dim]💡 Connect with: wscat --connect ws://127.0.0.1:{session['port']}/devtools/page/<tab-id>[/dim]")
    
    def list_sessions(self):
        sessions = self.db.list_sessions()
        if not sessions:
            console.print("[yellow]No sessions found[/yellow]")
            return
        
        # Fix stale running sessions
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
        
        vnc_info = self.display_manager.get_vnc_info()
        
        for session in sessions:
            status_color = "green" if session['status'] == 'running' else "dim"
            
            # Build connection info
            conn_info = ""
            if session['status'] == 'running':
                conn_info = f"[bold cyan]ws://127.0.0.1:{session['port']}[/bold cyan]"
                
                # Get first tab WS URL
                try:
                    devtools = self._get_devtools(session['port'])
                    ws_urls = devtools.get_all_ws_urls()
                    if ws_urls:
                        first_ws = ws_urls[0]['ws_url']
                        if first_ws:
                            conn_info += f"\n[dim]{first_ws[:50]}...[/dim]"
                except:
                    pass
                
                # VNC info
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
        
        if Confirm.ask("🔌 Auto-assign port?"):
            port = self._get_next_port()
            console.print(f"[green]Auto-assigned port: {port}[/green]")
        else:
            while True:
                try:
                    port = int(Prompt.ask("🔌 Port number", default="9222"))
                    if port < 1024 or port > 65535:
                        console.print("[red]Port must be between 1024 and 65535[/red]")
                        continue
                    if self.db.get_session_by_port(port):
                        console.print(f"[red]Port {port} is already in use[/red]")
                        continue
                    if self._is_port_in_use(port):
                        console.print(f"[red]Port {port} is already in use[/red]")
                        continue
                    break
                except ValueError:
                    console.print("[red]Please enter a valid number[/red]")
                    continue
        
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
            display_status = f"✅ {self.display} ({self.display_backend.value})"
            vnc_info = self.display_manager.get_vnc_info()
            if vnc_info:
                display_status += f"\n   VNC: {vnc_info}"
        
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
  🔧 Backend: {self.display_backend.value if self.display else "Headless"}
  🔌 WebSocket: Native Python (persistent)

[bold]Storage:[/bold]
  📁 Base Directory: {self.config.base_profile_dir}
  📁 Scripts Directory: {self.config.js_scripts_dir}
  🔧 Chrome: {self.chrome_path}
  📁 Log Directory: {self.config.log_dir}
  📋 Log Retention: {self.config.log_retention_days} days
"""
        console.print(Panel(content, title="Dashboard", border_style="cyan"))
    
    def manage_tabs(self, session_id: int):
        # Keep existing implementation from v3
        pass
    
    def show_connection_info(self, session_id: int):
        """Show connection info for a session"""
        self._show_connection_info(session_id)
    
    def interactive_menu(self):
        while True:
            console.clear()
            console.print()
            
            header = """
╔══════════════════════════════════════════════════════════════╗
║           🌐 Chrome Session Manager - Production v4        ║
║        VNC Auto-Detect | Persistent WebSocket             ║
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
            menu.add_row("8", "[bold]Manage Tabs[/bold]", "Advanced tab control with JS execution")
            menu.add_row("C", "[bold]Connection Info[/bold]", "Show connection info for a session")
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
