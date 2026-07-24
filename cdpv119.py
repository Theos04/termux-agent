#!/usr/bin/env python3
"""
Chrome Session Manager - Production v18
Fixed: X11 display check using xdpyinfo/vncserver-list instead of TCP port
Added: Session info JSON tracking with WebSocket IDs
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
    health_check_interval: int = 30
    health_check_timeout: int = 60
    session_stabilization_time: int = 45
    log_dir: Path = Path.home() / "chrome-logs"
    log_retention_days: int = 7
    max_log_files: int = 100
    devtools_connect_timeout: int = 60
    session_lock_timeout: float = 5.0
    max_session_restarts: int = 3
    restart_backoff_base: int = 3
    min_disk_space_mb: int = 100
    vnc_password: str = "chrome123"
    vnc_geometry: str = "1366x768"
    vnc_display: int = 1
    vnc_start_retries: int = 2
    vnc_retry_delay: int = 2
    x11_wait_timeout: int = 15
    session_info_file: str = os.path.expanduser("~/chrome-sessions/session_info.json")

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
# Session Info Tracker - Enhanced with WebSocket IDs
# ============================================================================

class SessionInfoTracker:
    """Tracks session start, end, and error events in a JSON file with WebSocket IDs"""
    
    def __init__(self, config: Config):
        self.config = config
        self.info_file = Path(config.session_info_file)
        self._lock = threading.RLock()
        self._ensure_file_exists()
        
    def _ensure_file_exists(self):
        """Create the info file if it doesn't exist"""
        self.info_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.info_file.exists():
            initial_data = {
                "sessions": {},
                "events": [],
                "statistics": {
                    "total_starts": 0,
                    "total_errors": 0,
                    "total_ends": 0,
                    "active_sessions": 0
                },
                "last_updated": datetime.now().isoformat()
            }
            with open(self.info_file, 'w') as f:
                json.dump(initial_data, f, indent=2)
    
    def _load_data(self) -> Dict:
        """Load the current session info data"""
        try:
            with open(self.info_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "sessions": {},
                "events": [],
                "statistics": {
                    "total_starts": 0,
                    "total_errors": 0,
                    "total_ends": 0,
                    "active_sessions": 0
                },
                "last_updated": datetime.now().isoformat()
            }
    
    def _save_data(self, data: Dict):
        """Save the session info data"""
        data["last_updated"] = datetime.now().isoformat()
        with open(self.info_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def log_session_start(self, session_id: int, session_data: Dict, ws_data: Optional[List[Dict]] = None):
        """
        Log a session start event with WebSocket data.
        Old WebSocket IDs are automatically cleaned up - only current ones are kept.
        """
        with self._lock:
            data = self._load_data()
            
            # Update session info
            if str(session_id) not in data["sessions"]:
                data["sessions"][str(session_id)] = {
                    "name": session_data.get("name", ""),
                    "url": session_data.get("url", ""),
                    "port": session_data.get("port", 0),
                    "profile_dir": session_data.get("profile_dir", ""),
                    "starts": 0,
                    "errors": 0,
                    "last_start": None,
                    "last_end": None,
                    "last_error": None,
                    "status": "stopped",
                    "websocket_ids": [],  # Store current WebSocket IDs
                    "current_ws_id": None  # Primary WebSocket ID
                }
            
            session_info = data["sessions"][str(session_id)]
            session_info["starts"] += 1
            session_info["last_start"] = datetime.now().isoformat()
            session_info["status"] = "running"
            session_info["pid"] = session_data.get("pid")
            session_info["port"] = session_data.get("port", 0)
            
            # Update WebSocket IDs - clean up old ones, keep only current
            if ws_data:
                # Extract WebSocket IDs from the current tabs
                current_ws_ids = [ws.get('tab_id') for ws in ws_data if ws.get('tab_id')]
                
                # If there are multiple tabs, use the first one as primary
                if current_ws_ids:
                    session_info["current_ws_id"] = current_ws_ids[0]
                    session_info["websocket_ids"] = current_ws_ids
                    session_info["websocket_details"] = ws_data  # Store full details
                else:
                    session_info["current_ws_id"] = None
                    session_info["websocket_ids"] = []
                    session_info["websocket_details"] = []
            else:
                session_info["current_ws_id"] = None
                session_info["websocket_ids"] = []
                session_info["websocket_details"] = []
            
            # Add event
            event = {
                "type": "start",
                "session_id": session_id,
                "session_name": session_data.get("name", ""),
                "timestamp": datetime.now().isoformat(),
                "port": session_data.get("port", 0),
                "pid": session_data.get("pid"),
                "url": session_data.get("url", ""),
                "websocket_id": session_info.get("current_ws_id"),
                "websocket_ids": session_info.get("websocket_ids", [])
            }
            data["events"].append(event)
            
            # Update statistics
            data["statistics"]["total_starts"] += 1
            data["statistics"]["active_sessions"] = len([
                s for s in data["sessions"].values() 
                if s.get("status") == "running"
            ])
            
            self._save_data(data)
            logger.info(f"📝 Session start logged for {session_id} with WS ID: {session_info.get('current_ws_id')}")
    
    def update_websocket_ids(self, session_id: int, ws_data: List[Dict]):
        """
        Update WebSocket IDs for a running session.
        Old IDs are automatically cleaned up - only current ones are kept.
        """
        with self._lock:
            data = self._load_data()
            
            if str(session_id) not in data["sessions"]:
                return
            
            session_info = data["sessions"][str(session_id)]
            
            # Extract WebSocket IDs from the current tabs
            current_ws_ids = [ws.get('tab_id') for ws in ws_data if ws.get('tab_id')]
            
            if current_ws_ids:
                session_info["current_ws_id"] = current_ws_ids[0]
                session_info["websocket_ids"] = current_ws_ids
                session_info["websocket_details"] = ws_data
            else:
                session_info["current_ws_id"] = None
                session_info["websocket_ids"] = []
                session_info["websocket_details"] = []
            
            self._save_data(data)
            logger.info(f"📝 WebSocket IDs updated for session {session_id}: {current_ws_ids}")
    
    def log_session_end(self, session_id: int, session_name: str = ""):
        """Log a session end event and clear WebSocket data"""
        with self._lock:
            data = self._load_data()
            
            # Update session info
            if str(session_id) in data["sessions"]:
                session_info = data["sessions"][str(session_id)]
                session_info["last_end"] = datetime.now().isoformat()
                session_info["status"] = "stopped"
                session_info["current_ws_id"] = None
                session_info["websocket_ids"] = []
                session_info["websocket_details"] = []
                if "pid" in session_info:
                    del session_info["pid"]
            
            # Add event
            event = {
                "type": "end",
                "session_id": session_id,
                "session_name": session_name,
                "timestamp": datetime.now().isoformat()
            }
            data["events"].append(event)
            
            # Update statistics
            data["statistics"]["total_ends"] += 1
            data["statistics"]["active_sessions"] = len([
                s for s in data["sessions"].values() 
                if s.get("status") == "running"
            ])
            
            self._save_data(data)
            logger.info(f"📝 Session end logged for {session_id}")
    
    def log_session_error(self, session_id: int, error: str, session_name: str = ""):
        """Log a session error event"""
        with self._lock:
            data = self._load_data()
            
            # Update session info
            if str(session_id) in data["sessions"]:
                session_info = data["sessions"][str(session_id)]
                session_info["errors"] += 1
                session_info["last_error"] = {
                    "message": error,
                    "timestamp": datetime.now().isoformat()
                }
                session_info["status"] = "error"
            
            # Add event
            event = {
                "type": "error",
                "session_id": session_id,
                "session_name": session_name,
                "error": error,
                "timestamp": datetime.now().isoformat()
            }
            data["events"].append(event)
            
            # Update statistics
            data["statistics"]["total_errors"] += 1
            
            self._save_data(data)
            logger.info(f"📝 Session error logged for {session_id}: {error}")
    
    def get_session_info(self, session_id: int) -> Optional[Dict]:
        """Get info for a specific session"""
        with self._lock:
            data = self._load_data()
            return data["sessions"].get(str(session_id))
    
    def get_all_sessions_info(self) -> Dict:
        """Get info for all sessions"""
        with self._lock:
            data = self._load_data()
            return data["sessions"]
    
    def get_recent_events(self, limit: int = 50) -> List[Dict]:
        """Get recent events"""
        with self._lock:
            data = self._load_data()
            return data["events"][-limit:]
    
    def get_statistics(self) -> Dict:
        """Get statistics"""
        with self._lock:
            data = self._load_data()
            return data["statistics"]
    
    def get_current_ws_id(self, session_id: int) -> Optional[str]:
        """Get the current WebSocket ID for a session"""
        with self._lock:
            data = self._load_data()
            session_info = data["sessions"].get(str(session_id))
            return session_info.get("current_ws_id") if session_info else None

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
# Display Manager - FIXED: Proper X11 display check
# ============================================================================

class DisplayManager:
    def __init__(self, config: Config):
        self.config = config
        self.current_display = None
        self.vnc_port = None
        self.vnc_pid = None
        self._lock = threading.RLock()
        self._setup_vnc_password()

    def _setup_vnc_password(self):
        """Ensure VNC password file exists non-interactively"""
        vnc_dir = Path.home() / ".vnc"
        vnc_dir.mkdir(mode=0o700, exist_ok=True)

        passwd_file = vnc_dir / "passwd"

        if not passwd_file.exists():
            try:
                cmd = f'echo "{self.config.vnc_password}" | vncpasswd -f > {passwd_file}'
                result = subprocess.run(cmd, shell=True, capture_output=True, timeout=10)
                if result.returncode == 0:
                    passwd_file.chmod(0o600)
                    logger.info("✅ VNC password file created")
                else:
                    logger.warning(f"vncpasswd failed: {result.stderr}")
                    # Fallback
                    try:
                        import crypt
                        encrypted = crypt.crypt(self.config.vnc_password, "aa")
                        with open(passwd_file, 'wb') as f:
                            f.write(encrypted.encode('utf-8')[:8])
                        passwd_file.chmod(0o600)
                        logger.info("✅ VNC password file created (fallback)")
                    except Exception as e2:
                        logger.error(f"Fallback also failed: {e2}")
            except Exception as e:
                logger.error(f"Failed to create VNC password file: {e}")

    def _check_x11_display(self, display_num: int) -> bool:
        """
        Check if X11 display is available.
        Uses xdpyinfo (direct X server query) or falls back to vncserver -list.
        Does NOT use TCP port 6000+n because modern X servers have TCP disabled by default.
        """
        # Try xdpyinfo first (most reliable)
        try:
            result = subprocess.run(
                ['xdpyinfo', '-display', f':{display_num}'],
                capture_output=True,
                timeout=5,
                env={**os.environ, 'DISPLAY': f':{display_num}'}
            )
            if result.returncode == 0:
                logger.debug(f"✅ xdpyinfo confirms display :{display_num}")
                return True
        except FileNotFoundError:
            logger.debug("xdpyinfo not installed - using vncserver -list fallback")
        except Exception as e:
            logger.debug(f"xdpyinfo failed: {e}")

        # Fallback: check vncserver -list
        try:
            result = subprocess.run(
                ['vncserver', '-list'],
                capture_output=True,
                text=True,
                timeout=5
            )

            # Parse output looking for display: with PID
            for line in result.stdout.split('\n'):
                if f":{display_num}" in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            pid = int(parts[1])
                            # Verify the PID is actually running
                            os.kill(pid, 0)
                            logger.debug(f"✅ vncserver -list confirms display :{display_num} (PID {pid})")
                            return True
                        except (ValueError, OSError):
                            # PID not running - stale entry
                            logger.debug(f"Display :{display_num} in vncserver -list but PID not running")
                            return False
        except Exception as e:
            logger.debug(f"vncserver -list fallback failed: {e}")

        return False

    def _clean_stale_vnc_files(self, display_num: int):
        """Remove stale VNC lock and socket files"""
        # Remove X11 lock files
        lock_file = Path(f"/tmp/.X{display_num}-lock")
        if lock_file.exists():
            try:
                lock_file.unlink()
                logger.debug(f"Removed stale lock file: {lock_file}")
            except:
                pass

        # Remove X11 socket
        socket_file = Path(f"/tmp/.X11-unix/X{display_num}")
        if socket_file.exists():
            try:
                socket_file.unlink()
                logger.debug(f"Removed stale socket: {socket_file}")
            except:
                pass

        # Remove VNC log and pid files
        vnc_dir = Path.home() / ".vnc"
        for pattern in [f":{display_num}.log", f":{display_num}.pid"]:
            for f in vnc_dir.glob(pattern):
                try:
                    f.unlink()
                    logger.debug(f"Removed stale VNC file: {f}")
                except:
                    pass

    def _start_vnc_with_retry(self, display_num: int) -> bool:
        """Start VNC server with retries"""
        display_str = f":{display_num}"

        # Clean stale files first
        self._clean_stale_vnc_files(display_num)

        # Kill any existing VNC on this display
        try:
            subprocess.run(
                ['vncserver', '-kill', display_str],
                capture_output=True,
                timeout=5
            )
            time.sleep(1)
        except:
            pass

        for attempt in range(self.config.vnc_start_retries):
            logger.info(f"Starting VNC {display_str} (attempt {attempt + 1}/{self.config.vnc_start_retries})")

            try:
                cmd = [
                    'vncserver',
                    display_str,
                    '-geometry', self.config.vnc_geometry,
                    '-depth', '24',
                    '-localhost', 'no',
                    '-alwaysshared',
                    '-SecurityTypes', 'VncAuth',
                    '-PasswordFile', str(Path.home() / '.vnc' / 'passwd')
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.stdout:
                    logger.info(f"VNC stdout: {result.stdout[:500]}")
                if result.stderr:
                    logger.info(f"VNC stderr: {result.stderr[:500]}")

                if result.returncode != 0:
                    logger.warning(f"VNC returned {result.returncode}: {result.stderr[:200]}")
                    if attempt < self.config.vnc_start_retries - 1:
                        time.sleep(self.config.vnc_retry_delay)
                    continue

                # Wait for X11 display to be ready
                start_time = time.time()
                while time.time() - start_time < self.config.x11_wait_timeout:
                    if self._check_x11_display(display_num):
                        logger.info(f"✅ VNC started on {display_str}")
                        return True
                    time.sleep(0.5)

                logger.warning(f"VNC started but X11 display not ready after {self.config.x11_wait_timeout}s")

                # Check if we can get more info
                try:
                    list_result = subprocess.run(['vncserver', '-list'], capture_output=True, text=True, timeout=5)
                    logger.info(f"vncserver -list: {list_result.stdout}")
                except:
                    pass

                # Try cleaning up for next attempt
                try:
                    subprocess.run(['vncserver', '-kill', display_str], capture_output=True, timeout=5)
                    time.sleep(1)
                except:
                    pass

                if attempt < self.config.vnc_start_retries - 1:
                    time.sleep(self.config.vnc_retry_delay)

            except Exception as e:
                logger.warning(f"VNC start attempt {attempt + 1} failed: {e}")
                if attempt < self.config.vnc_start_retries - 1:
                    time.sleep(self.config.vnc_retry_delay)

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
            for line in result.stdout.strip().split('\n'):
                match = re.search(r':(\d+)\s+(\d+)', line)
                if match:
                    display_num = int(match.group(1))
                    # Verify the display is actually working
                    if self._check_x11_display(display_num):
                        sessions.append({
                            'display': f":{display_num}",
                            'pid': int(match.group(2)),
                            'vnc_port': 5900 + display_num,
                        })
                    else:
                        logger.debug(f"Found stale VNC session :{display_num}, cleaning up")
                        try:
                            subprocess.run(['vncserver', '-kill', f":{display_num}"], capture_output=True, timeout=5)
                            self._clean_stale_vnc_files(display_num)
                        except:
                            pass
            return sessions
        except Exception as e:
            logger.debug(f"Failed to list VNC sessions: {e}")
            return []

    def _ensure_vnc_running(self) -> Tuple[Optional[str], Optional[int]]:
        """Ensure VNC is running, start if needed"""
        # First, check if we already have a working display
        if self.current_display:
            display_num = int(self.current_display.replace(':', ''))
            if self._check_x11_display(display_num):
                return self.current_display, self.vnc_port

        # Look for existing VNC sessions
        sessions = self._get_vnc_sessions()
        if sessions:
            session = sessions[0]
            display = session['display']
            self.current_display = display
            self.vnc_port = session['vnc_port']
            self.vnc_pid = session['pid']
            os.environ['DISPLAY'] = display
            logger.info(f"✅ Using existing VNC display: {display}")
            return display, self.vnc_port

        # Try to start VNC on each display
        for display_num in range(self.config.display_start, self.config.display_end + 1):
            display = f":{display_num}"

            if self._check_x11_display(display_num):
                logger.info(f"Display {display} already has X11 running")
                self.current_display = display
                self.vnc_port = 5900 + display_num
                os.environ['DISPLAY'] = display
                return display, self.vnc_port

            if self._start_vnc_with_retry(display_num):
                self.current_display = display
                self.vnc_port = 5900 + display_num
                os.environ['DISPLAY'] = display
                logger.info(f"✅ Started VNC on {display}")
                return display, self.vnc_port

        return None, None

    def get_display(self) -> Tuple[Optional[str], Optional[int]]:
        """Get a working display"""
        # Check if DISPLAY is already set and working
        if os.environ.get('DISPLAY'):
            display = os.environ.get('DISPLAY')
            display_num = int(display.replace(':', ''))
            if self._check_x11_display(display_num):
                self.current_display = display
                # Get VNC port if available
                sessions = self._get_vnc_sessions()
                for session in sessions:
                    if session['display'] == display:
                        self.vnc_port = session['vnc_port']
                        self.vnc_pid = session['pid']
                        break
                logger.info(f"✅ Using existing DISPLAY: {display}")
                console.print(f"[green]✅ Using display: {display}[/green]")
                if self.vnc_port:
                    console.print(f"[green]📺 VNC available: vnc://127.0.0.1:{self.vnc_port} (password: {self.config.vnc_password})[/green]")
                return display, self.vnc_port

        # Try to get VNC running
        display, vnc_port = self._ensure_vnc_running()

        if display:
            console.print(f"[green]✅ Using VNC display: {display}[/green]")
            if vnc_port:
                console.print(f"[green]📺 VNC available: vnc://127.0.0.1:{vnc_port} (password: {self.config.vnc_password})[/green]")
            return display, vnc_port

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
        now = time.time()
        if now - self._last_check < 5:
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
            "--disable-ipc-flooding-protection",
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
            cmd.append(session['url'])
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

    def _wait_for_url_load(self, devtools: ChromeDevTools, target_url: str, timeout: int = 30) -> bool:
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                tabs = devtools.get_tabs()
                for tab in tabs:
                    if tab.get('type') == 'page':
                        current_url = tab.get('url', '')
                        if current_url == target_url or current_url.startswith(target_url):
                            logger.info(f"✅ Page loaded: {current_url}")
                            return True
                        elif current_url in ['about:blank', '', 'chrome://newtab/']:
                            time.sleep(1)
                            continue
                        else:
                            logger.info(f"Page loaded: {current_url}")
                            return True
                time.sleep(1)
            except Exception as e:
                logger.debug(f"Error checking URL: {e}")
                time.sleep(1)
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
        use_display = False
        display = self.display_manager.current_display

        if display:
            use_display = True
            logger.info(f"✅ Using display: {display}")

        cmd = self.build_command(session, use_display)
        logger.info(f"Command: {' '.join(cmd[:10])} ... (truncated)")

        env = os.environ.copy()
        if use_display and display:
            env['DISPLAY'] = display
            logger.info(f"Setting DISPLAY={display} for Chrome")
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

            time.sleep(5)

            if process.poll() is not None:
                error_msg = ""
                if log_file.exists():
                    with open(log_file, 'r') as f:
                        error_msg = f.read(500)
                        if "cannot open display" in error_msg.lower():
                            console.print("[red]❌ Chrome cannot open display.[/red]")
                return False, None, f"Process died: {error_msg[:200]}"

            devtools = ChromeDevTools(port=session['port'])
            if not devtools.wait_for_connection(timeout=self.config.devtools_connect_timeout):
                error_msg = ""
                if log_file.exists():
                    with open(log_file, 'r') as f:
                        error_msg = f.read(500)
                return False, None, f"DevTools connection timeout: {error_msg[:200]}"

            logger.info(f"✅ Chrome launched (PID: {process.pid})")

            if use_display:
                console.print("[dim]⏳ Waiting for page to load...[/dim]")
                if self._wait_for_url_load(devtools, session['url'], timeout=30):
                    console.print(f"[green]🌐 Page loaded: {session['url']}[/green]")

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
        self._session_start_times: Dict[int, float] = {}
        
        # Initialize session info tracker
        self.session_tracker = SessionInfoTracker(self.config)

        self.display_manager = DisplayManager(self.config)
        self.display, self.vnc_port = self.display_manager.get_display()

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
            return

        try:
            session = self.db.get_session(session_id)
            if not session or session['status'] != 'running':
                return

            if session_id in self._session_start_times:
                age = time.time() - self._session_start_times[session_id]
                if age < self.config.session_stabilization_time:
                    return

            if session['pid']:
                try:
                    os.kill(session['pid'], 0)
                except OSError:
                    logger.warning(f"Session {session_id} PID {session['pid']} dead")
                    error_msg = f"Process {session['pid']} died unexpectedly"
                    self.session_tracker.log_session_error(session_id, error_msg, session.get('name', ''))
                    self._recover_session(session_id)
                    return

            devtools = self._get_devtools(session['port'])

            for attempt in range(3):
                if devtools._ensure_connection():
                    return
                time.sleep(2)

            logger.warning(f"Session {session_id} DevTools not responding")
            error_msg = "DevTools not responding"
            self.session_tracker.log_session_error(session_id, error_msg, session.get('name', ''))

            if session['pid']:
                try:
                    proc = psutil.Process(session['pid'])
                    if proc.is_running():
                        return
                except:
                    pass

            self._recover_session(session_id)

        except Exception as e:
            logger.error(f"Health check error for session {session_id}: {e}")
            self.session_tracker.log_session_error(session_id, str(e), session.get('name', ''))
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
            # Get WebSocket URLs after launch
            devtools = self._get_devtools(session['port'])
            ws_data = devtools.get_ws_urls()
            
            session_data = {
                "name": session['name'],
                "url": session['url'],
                "port": session['port'],
                "profile_dir": session['profile_dir'],
                "pid": pid
            }
            self.session_tracker.log_session_start(session_id, session_data, ws_data)
            
            self.db.start_session(session_id, pid)
            self.db.reset_session_restart_count(session_id)

            self._session_start_times[session_id] = time.time()

            logger.info(f"Session {session_id} started (PID: {pid})")
            console.print(f"[green]✅ Session '{session['name']}' started![/green]")

            self._show_connection_info(session_id)

            console.print(f"[dim]⏳ Chrome is starting up... Please wait {self.config.session_stabilization_time}s before interacting.[/dim]")
        else:
            error_msg = f"Failed to start session: {error}"
            logger.error(error_msg)
            console.print(f"[red]❌ {error_msg}[/red]")
            self.session_tracker.log_session_error(session_id, error, session.get('name', ''))

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
        
        # Log session end - this will clear WebSocket data
        self.session_tracker.log_session_end(session_id, session.get('name', ''))

        with self._devtools_lock:
            if session['port'] in self.devtools:
                del self.devtools[session['port']]

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
        
        # Update session tracker with current WebSocket IDs
        if ws_urls:
            self.session_tracker.update_websocket_ids(session_id, ws_urls)

        if ws_urls:
            console.print()
            console.print("[bold cyan]WebSocket URLs:[/bold cyan]")
            for i, ws in enumerate(ws_urls, 1):
                console.print(f"  [{i}] {ws['title'][:50] or 'Untitled'}...")
                console.print(f"      [bold green]WS ID:[/bold green] {ws['tab_id']}")
                console.print(f"      [dim]{ws['ws_url']}[/dim]")
                console.print(f"      [dim]wscat --connect {ws['ws_url']}[/dim]")
            
            # Show stored WS ID from tracker
            stored_ws_id = self.session_tracker.get_current_ws_id(session_id)
            if stored_ws_id:
                console.print()
                console.print(f"[bold green]📌 Current WebSocket ID (stored):[/bold green] {stored_ws_id}")
        else:
            console.print()
            console.print("[yellow]No WebSocket URLs available[/yellow]")

    def list_sessions(self):
        sessions = self.db.list_sessions()
        if not sessions:
            console.print("[yellow]No sessions found[/yellow]")
            return

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
        table.add_column("WS ID", style="bright_blue", width=35)
        table.add_column("Errors", style="red", width=8)

        vnc_info = f"VNC:{self.vnc_port}" if self.vnc_port else ""

        for session in sessions:
            status_color = "green" if session['status'] == 'running' else "dim"
            error_count = ""
            ws_id = ""
            session_info = self.session_tracker.get_session_info(session['id'])
            if session_info:
                error_count = str(session_info.get('errors', 0))
                ws_id = session_info.get('current_ws_id', '')
                if ws_id:
                    ws_id = ws_id[:30] + "..." if len(ws_id) > 30 else ws_id

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
                ws_id or "[dim]N/A[/dim]",
                error_count or "0"
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

        session_info = self.session_tracker.get_session_info(session_id)
        
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

[bold cyan]Tracked Info:[/bold cyan]
[bold]Total Starts:[/bold] {session_info.get('starts', 0) if session_info else 'N/A'}
[bold]Total Errors:[/bold] {session_info.get('errors', 0) if session_info else 'N/A'}
[bold]Last Start:[/bold] {session_info.get('last_start', 'Never') if session_info else 'N/A'}
[bold]Last End:[/bold] {session_info.get('last_end', 'Never') if session_info else 'N/A'}
[bold]Current WebSocket ID:[/bold] {session_info.get('current_ws_id', 'None') if session_info else 'N/A'}
[bold]All WebSocket IDs:[/bold] {', '.join(session_info.get('websocket_ids', [])) if session_info else 'N/A'}
[bold]Last Error:[/bold] {session_info.get('last_error', {}).get('message', 'None') if session_info else 'N/A'}
"""
        console.print(Panel(content, title="📊 Session Details", border_style="blue"))

    def show_dashboard(self):
        sessions = self.db.list_sessions()
        running = [s for s in sessions if s['status'] == 'running']
        stopped = [s for s in sessions if s['status'] == 'stopped']
        
        stats = self.session_tracker.get_statistics()
        recent_events = self.session_tracker.get_recent_events(limit=10)

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

[bold]Session Statistics:[/bold]
  📈 Total Starts: {stats.get('total_starts', 0)}
  🛑 Total Ends: {stats.get('total_ends', 0)}
  ❌ Total Errors: {stats.get('total_errors', 0)}
  🎯 Active Sessions: {stats.get('active_sessions', 0)}

[bold]Active WebSocket IDs:[/bold]
"""
        # Show current WebSocket IDs for running sessions
        for session in running:
            session_info = self.session_tracker.get_session_info(session['id'])
            if session_info:
                ws_id = session_info.get('current_ws_id', 'None')
                content += f"  🟢 Session {session['id']} ({session['name']}): {ws_id}\n"
        if not running:
            content += "  No active sessions\n"

        content += f"""
[bold]Display:[/bold]
  🖥️ Display: {display_status}
  📺 VNC Password: {self.config.vnc_password}

[bold]Storage:[/bold]
  📁 Base Directory: {self.config.base_profile_dir}
  🔧 Chrome: {self.chrome_path}
  📁 Log Directory: {self.config.log_dir}
  📄 Session Info: {self.config.session_info_file}

[bold]Recent Events:[/bold]
"""
        if recent_events:
            for event in recent_events[-5:]:
                event_type = event.get('type', 'unknown')
                icon = "🚀" if event_type == 'start' else "🛑" if event_type == 'end' else "❌"
                ws_info = f" [WS: {event.get('websocket_id', 'N/A')}]" if event.get('websocket_id') else ""
                content += f"  {icon} [{event_type}] Session {event.get('session_id')}: {event.get('session_name', '')}{ws_info}\n"
        else:
            content += "  No recent events\n"

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
            table.add_column("Tab ID", style="magenta")

            for i, tab in enumerate(tabs, 1):
                table.add_row(
                    str(i),
                    tab.get('title', 'Untitled')[:60],
                    tab.get('url', '')[:70],
                    tab.get('id', '')[:30]
                )
            console.print(table)
            
            # Update WebSocket IDs in tracker
            ws_data = devtools.get_ws_urls()
            if ws_data:
                self.session_tracker.update_websocket_ids(session_id, ws_data)
                console.print()
                console.print("[green]✅ WebSocket IDs updated in session_info.json[/green]")
        else:
            console.print("[yellow]No tabs open[/yellow]")

        console.print()
        Prompt.ask("Press Enter to continue...")

    def show_session_info_file(self):
        """Display the contents of the session info file"""
        info_file = Path(self.config.session_info_file)
        if not info_file.exists():
            console.print("[red]Session info file not found[/red]")
            return
            
        try:
            with open(info_file, 'r') as f:
                data = json.load(f)
                
            console.print()
            console.print(Panel("[bold cyan]Session Info File Contents[/bold cyan]", border_style="green"))
            
            # Show statistics
            stats = data.get('statistics', {})
            console.print("\n[bold]Statistics:[/bold]")
            console.print(f"  Total Starts: {stats.get('total_starts', 0)}")
            console.print(f"  Total Ends: {stats.get('total_ends', 0)}")
            console.print(f"  Total Errors: {stats.get('total_errors', 0)}")
            console.print(f"  Active Sessions: {stats.get('active_sessions', 0)}")
            
            # Show recent events
            events = data.get('events', [])
            if events:
                console.print("\n[bold]Recent Events:[/bold]")
                for event in events[-10:]:
                    event_type = event.get('type', 'unknown')
                    icon = "🚀" if event_type == 'start' else "🛑" if event_type == 'end' else "❌"
                    ws_info = f" [WS: {event.get('websocket_id', 'N/A')}]" if event.get('websocket_id') else ""
                    console.print(f"  {icon} {event.get('timestamp', '')} - Session {event.get('session_id')}: {event.get('session_name', '')}{ws_info}")
                    if event.get('error'):
                        console.print(f"     Error: {event.get('error')}")
            
            # Show session info
            sessions = data.get('sessions', {})
            if sessions:
                console.print("\n[bold]Session Info:[/bold]")
                for sid, sinfo in sessions.items():
                    status = sinfo.get('status', 'unknown')
                    status_icon = "🟢" if status == 'running' else "🟡" if status == 'error' else "⚪"
                    ws_id = sinfo.get('current_ws_id', 'None')
                    console.print(f"  {status_icon} Session {sid}: {sinfo.get('name', '')}")
                    console.print(f"     Starts: {sinfo.get('starts', 0)}, Errors: {sinfo.get('errors', 0)}")
                    console.print(f"     Current WS ID: {ws_id}")
                    if sinfo.get('websocket_ids'):
                        console.print(f"     All WS IDs: {', '.join(sinfo.get('websocket_ids', []))}")
                    console.print(f"     Last Start: {sinfo.get('last_start', 'Never')}")
                    if sinfo.get('last_error'):
                        console.print(f"     Last Error: {sinfo.get('last_error', {}).get('message', '')}")
            
            console.print()
            console.print(f"[dim]File location: {info_file}[/dim]")
            
        except Exception as e:
            console.print(f"[red]Error reading session info file: {e}[/red]")

    def interactive_menu(self):
        while True:
            console.clear()
            console.print()

            header = """
╔══════════════════════════════════════════════════════════════╗
║           🌐 Chrome Session Manager - Production v18       ║
║        Fixed X11 Display Check | No False Negatives        ║
║           + Session Info JSON with WebSocket IDs           ║
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
            menu.add_row("9", "[yellow]View Session Info File[/yellow]", "View session_info.json contents")
            menu.add_row("C", "[bold]Connection Info[/bold]", "Show connection info")
            menu.add_row("0", "[red]Exit[/red]", "Exit the manager")

            console.print(menu)
            console.print()

            choice = Prompt.ask("Select option", choices=["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "C"])

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

            elif choice == "9":
                self.show_session_info_file()

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
