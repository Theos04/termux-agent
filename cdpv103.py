#!/usr/bin/env python3
"""
Chrome Session Manager - Production Grade
Self-healing Chrome orchestrator with proper display management
"""

import os
import time
import subprocess
import shutil
import signal
import sys
import json
import re
from typing import Optional, Dict, List, Any, Tuple, Callable
from datetime import datetime
import socket
import hashlib
import tempfile
import threading
import queue
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

try:
    import psutil
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
    import psutil

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich import box
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.live import Live
    from rich.layout import Layout
    from rich.text import Text
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rich"])
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich import box
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.live import Live
    from rich.layout import Layout
    from rich.text import Text

from session_db import SessionDB
import requests

# Setup logging
LOG_DIR = Path.home() / "chrome-logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "chrome_manager.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

console = Console()

# Configuration
BASE_PROFILE_DIR = os.path.expanduser("~/chrome-sessions")
DEBUG_PORT_START = 9222
DEBUG_PORT_END = 9299
JS_SCRIPTS_DIR = os.path.expanduser("~/chrome-scripts")
os.makedirs(JS_SCRIPTS_DIR, exist_ok=True)

# Configuration dataclass
@dataclass
class Config:
    base_profile_dir: str = BASE_PROFILE_DIR
    debug_port_start: int = DEBUG_PORT_START
    debug_port_end: int = DEBUG_PORT_END
    js_scripts_dir: str = JS_SCRIPTS_DIR
    display_start: int = 1
    display_end: int = 5
    max_retries: int = 3
    retry_delay: int = 2
    health_check_interval: int = 5
    websocket_heartbeat: int = 30
    log_dir: Path = LOG_DIR

class DisplayBackend(Enum):
    """Supported display backends"""
    XVFB = "xvfb"
    TIGERVNC = "tigervnc"
    X11 = "x11"
    WAYLAND = "wayland"
    HEADLESS = "headless"

class DisplayHealth:
    """Display health check results"""
    def __init__(self):
        self.x_socket_ok = False
        self.xdpyinfo_ok = False
        self.xprop_ok = False
        self.xset_ok = False
        self.window_manager_ok = False
        self.details = {}
        self.checked_at = 0
        self.cache_duration = 2  # seconds

class XServerChecker:
    """Pure X server verification - no VNC assumptions"""
    
    @staticmethod
    def check_x_socket(display: str) -> bool:
        """Check if X socket exists (Unix socket or TCP)"""
        display_num = display.replace(':', '').replace('/', '')
        
        # Check Unix socket first (modern X servers)
        unix_socket = f"/tmp/.X11-unix/X{display_num}"
        if os.path.exists(unix_socket):
            logger.debug(f"Unix socket found: {unix_socket}")
            return True
        
        # Check TCP socket (legacy X servers)
        try:
            port = 6000 + int(display_num)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            if result == 0:
                logger.debug(f"TCP socket found: port {port}")
                return True
        except:
            pass
        
        return False
    
    @staticmethod
    def check_xdpyinfo(display: str) -> Tuple[bool, str]:
        """Run xdpyinfo to verify X server"""
        try:
            env = os.environ.copy()
            env['DISPLAY'] = display
            result = subprocess.run(
                ['xdpyinfo'],
                env=env,
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode == 0:
                # Parse version info
                for line in result.stdout.split('\n'):
                    if 'version' in line.lower():
                        return True, line.strip()
                return True, "X server responding"
            return False, result.stderr[:200]
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def check_xprop(display: str) -> Tuple[bool, str]:
        """Check X properties (window manager presence)"""
        try:
            env = os.environ.copy()
            env['DISPLAY'] = display
            result = subprocess.run(
                ['xprop', '-root'],
                env=env,
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode == 0:
                # Look for window manager
                if '_NET_WM_NAME' in result.stdout:
                    return True, "Window manager running"
                return True, "X server responding (no WM)"
            return False, result.stderr[:200]
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def check_xset(display: str) -> Tuple[bool, str]:
        """Check X server settings"""
        try:
            env = os.environ.copy()
            env['DISPLAY'] = display
            result = subprocess.run(
                ['xset', 'q'],
                env=env,
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode == 0:
                return True, "X server responding"
            return False, result.stderr[:200]
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def comprehensive_check(display: str) -> DisplayHealth:
        """Run all checks and return comprehensive health"""
        health = DisplayHealth()
        health.checked_at = time.time()
        
        # Check 1: X socket
        health.x_socket_ok = XServerChecker.check_x_socket(display)
        if not health.x_socket_ok:
            logger.warning(f"X socket not found for {display}")
            return health
        
        # Check 2: xdpyinfo
        health.xdpyinfo_ok, details = XServerChecker.check_xdpyinfo(display)
        health.details['xdpyinfo'] = details
        if not health.xdpyinfo_ok:
            logger.warning(f"xdpyinfo failed: {details}")
            return health
        
        # Check 3: xprop (window manager)
        health.xprop_ok, details = XServerChecker.check_xprop(display)
        health.details['xprop'] = details
        
        # Check 4: xset
        health.xset_ok, details = XServerChecker.check_xset(display)
        health.details['xset'] = details
        
        # Overall health - xdpyinfo is the most critical
        health.window_manager_ok = health.xprop_ok
        health.details['overall'] = "Healthy" if health.xdpyinfo_ok else "Unhealthy"
        
        return health

class DisplayManager:
    """Display manager with support for multiple backends"""
    
    def __init__(self, config: Config):
        self.config = config
        self.current_display = None
        self.current_backend = DisplayBackend.HEADLESS
        self.health = DisplayHealth()
        self.cached_health = None
        self.cache_time = 0
        self.is_termux = 'TERMUX_VERSION' in os.environ or 'com.termux' in os.environ.get('PREFIX', '')
        self.x_checker = XServerChecker()
        
    def _get_available_backends(self) -> List[Tuple[DisplayBackend, str]]:
        """Get available display backends with their start commands"""
        backends = []
        
        # Check for Xvfb
        if shutil.which('Xvfb'):
            backends.append((DisplayBackend.XVFB, 'Xvfb'))
        
        # Check for TigerVNC
        if shutil.which('vncserver'):
            backends.append((DisplayBackend.TIGERVNC, 'vncserver'))
        
        # Check for X11
        if 'DISPLAY' in os.environ:
            backends.append((DisplayBackend.X11, os.environ['DISPLAY']))
        
        return backends
    
    def _start_xvfb(self, display_num: int) -> Optional[str]:
        """Start Xvfb virtual framebuffer"""
        try:
            display = f":{display_num}"
            logger.info(f"Starting Xvfb on {display}")
            
            cmd = [
                'Xvfb', display,
                '-screen', '0', '1366x768x24',
                '-ac',
                '-nolisten', 'tcp'
            ]
            
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            
            time.sleep(2)  # Wait for Xvfb to start
            
            if self.x_checker.check_x_socket(display):
                logger.info(f"Xvfb started on {display}")
                return display
            return None
        except Exception as e:
            logger.error(f"Failed to start Xvfb: {e}")
            return None
    
    def _start_vnc(self, display_num: int) -> Optional[str]:
        """Start VNC server"""
        try:
            display = f":{display_num}"
            logger.info(f"Starting VNC on {display}")
            
            result = subprocess.run(
                ['vncserver', display],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                time.sleep(2)  # Wait for VNC to start
                if self.x_checker.check_x_socket(display):
                    logger.info(f"VNC started on {display}")
                    return display
            return None
        except Exception as e:
            logger.error(f"Failed to start VNC: {e}")
            return None
    
    def _kill_vnc_sessions(self):
        """Kill existing VNC sessions"""
        try:
            result = subprocess.run(
                ['vncserver', '-list'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            lines = result.stdout.strip().split('\n')
            for line in lines:
                match = re.search(r':(\d+)\s+(\d+)', line)
                if match:
                    display_num = int(match.group(1))
                    pid = int(match.group(2))
                    try:
                        logger.info(f"Killing VNC session :{display_num} (PID: {pid})")
                        os.kill(pid, signal.SIGTERM)
                        time.sleep(1)
                    except:
                        pass
        except Exception as e:
            logger.debug(f"Error killing VNC: {e}")
    
    def _verify_display(self, display: str) -> DisplayHealth:
        """Comprehensive display verification"""
        if self.cached_health and (time.time() - self.cache_time) < self.cache_time:
            return self.cached_health
        
        health = self.x_checker.comprehensive_check(display)
        self.cached_health = health
        self.cache_time = time.time()
        
        return health
    
    def get_display(self) -> Tuple[Optional[str], DisplayBackend]:
        """Get a working display"""
        # In Termux, always use headless
        if self.is_termux:
            logger.info("Running in Termux - using headless mode")
            return None, DisplayBackend.HEADLESS
        
        # Check existing DISPLAY environment
        env_display = os.environ.get('DISPLAY')
        if env_display:
            health = self._verify_display(env_display)
            if health.xdpyinfo_ok:
                self.current_display = env_display
                self.current_backend = DisplayBackend.X11
                self.health = health
                logger.info(f"Using existing display: {env_display}")
                return env_display, DisplayBackend.X11
            else:
                logger.warning(f"DISPLAY {env_display} invalid: {health.details}")
        
        # Try to start Xvfb first (most reliable)
        for display_num in range(self.config.display_start, self.config.display_end + 1):
            display = f":{display_num}"
            if not self.x_checker.check_x_socket(display):
                logger.info(f"Attempting to start Xvfb on {display}")
                started = self._start_xvfb(display_num)
                if started:
                    health = self._verify_display(started)
                    if health.xdpyinfo_ok:
                        self.current_display = started
                        self.current_backend = DisplayBackend.XVFB
                        self.health = health
                        os.environ['DISPLAY'] = started
                        logger.info(f"Started Xvfb on {started}")
                        return started, DisplayBackend.XVFB
        
        # Try VNC as fallback
        self._kill_vnc_sessions()
        for display_num in range(self.config.display_start, self.config.display_end + 1):
            display = f":{display_num}"
            if not self.x_checker.check_x_socket(display):
                logger.info(f"Attempting to start VNC on {display}")
                started = self._start_vnc(display_num)
                if started:
                    health = self._verify_display(started)
                    if health.xdpyinfo_ok:
                        self.current_display = started
                        self.current_backend = DisplayBackend.TIGERVNC
                        self.health = health
                        os.environ['DISPLAY'] = started
                        logger.info(f"Started VNC on {started}")
                        return started, DisplayBackend.TIGERVNC
        
        logger.warning("No display available - using headless mode")
        return None, DisplayBackend.HEADLESS
    
    def verify_and_recover(self) -> bool:
        """Verify current display and attempt recovery if needed"""
        if not self.current_display:
            return False
        
        health = self._verify_display(self.current_display)
        if health.xdpyinfo_ok:
            self.health = health
            return True
        
        logger.warning(f"Display {self.current_display} unhealthy - attempting recovery")
        
        # Try to restart the backend
        if self.current_backend == DisplayBackend.XVFB:
            display_num = int(self.current_display.replace(':', ''))
            new_display = self._start_xvfb(display_num)
            if new_display:
                self.current_display = new_display
                os.environ['DISPLAY'] = new_display
                return True
        
        elif self.current_backend == DisplayBackend.TIGERVNC:
            self._kill_vnc_sessions()
            display_num = int(self.current_display.replace(':', ''))
            new_display = self._start_vnc(display_num)
            if new_display:
                self.current_display = new_display
                os.environ['DISPLAY'] = new_display
                return True
        
        return False

class HealthMonitor:
    """Monitor health of Chrome sessions"""
    
    def __init__(self, manager):
        self.manager = manager
        self.running = False
        self.monitor_thread = None
        self.callbacks = []
    
    def start(self):
        """Start health monitoring thread"""
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Health monitor started")
    
    def stop(self):
        """Stop health monitoring"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        logger.info("Health monitor stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                self._check_health()
                time.sleep(self.manager.config.health_check_interval)
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
    
    def _check_health(self):
        """Check health of all running sessions"""
        sessions = self.manager.db.list_sessions()
        for session in sessions:
            if session['status'] == 'running':
                self._check_session_health(session)
    
    def _check_session_health(self, session: Dict):
        """Check health of a single session"""
        # Check PID
        if session['pid']:
            try:
                os.kill(session['pid'], 0)
            except OSError:
                logger.warning(f"Session {session['id']} PID {session['pid']} dead")
                self._handle_unhealthy_session(session)
                return
        
        # Check DevTools
        devtools = self.manager._get_devtools(session['port'])
        if not devtools._ensure_connection():
            logger.warning(f"Session {session['id']} DevTools not responding")
            self._handle_unhealthy_session(session)
            return
        
        # Check WebSocket
        tabs = devtools.get_tabs()
        if not tabs:
            logger.warning(f"Session {session['id']} has no tabs")
            return
        
        # Check if tab is responsive
        try:
            tab = tabs[0]
            devtools.get_page_title(tab['id'])
        except:
            logger.warning(f"Session {session['id']} tab not responding")
            self._handle_unhealthy_session(session)
    
    def _handle_unhealthy_session(self, session: Dict):
        """Handle unhealthy session - attempt recovery"""
        logger.info(f"Attempting to recover session {session['id']}")
        
        # Stop the session
        self.manager.stop_session(session['id'])
        
        # Wait a moment
        time.sleep(2)
        
        # Try to restart
        self.manager.start_session(session['id'])

class ChromeLauncher:
    """Chrome launcher with retry and recovery"""
    
    def __init__(self, manager):
        self.manager = manager
        self.config = manager.config
    
    def build_command(self, session: Dict, use_display: bool) -> List[str]:
        """Build Chrome command with proper flags"""
        profile_dir = session['profile_dir']
        
        # Base command
        cmd = [
            self.manager.chrome_path,
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
        
        # Combine all features into a single flag
        features = [
            "IsolateOrigins",
            "site-per-process",
            "BlockInsecurePrivateNetworkRequests",
            "TranslateUI",
            "AudioServiceOutOfProcess",
            "PasswordImport",
            "PrivacySandboxSettings4",
            "PrivacySandboxAdsAPIsOverride",
            "EnableMsrPpqTesting",
            "EnableMsrPpqTrial",
            "EnableMsrPpq",
            "VizDisplayCompositor",
        ]
        cmd.append(f"--disable-features={','.join(features)}")
        
        # Disable security for automation
        cmd.append("--disable-web-security")
        
        # Display or headless
        if use_display:
            cmd.append(session['url'])
        else:
            cmd.extend([
                "--headless",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--no-sandbox",
                f"--window-size=1366,768",
                session['url']
            ])
        
        return cmd
    
    def launch_with_retry(self, session: Dict, max_retries: int = 3) -> Tuple[bool, Optional[int], str]:
        """Launch Chrome with retry logic"""
        for attempt in range(max_retries):
            logger.info(f"Launch attempt {attempt + 1}/{max_retries} for session {session['id']}")
            
            success, pid, error = self._launch_once(session)
            if success:
                return True, pid, ""
            
            logger.warning(f"Attempt {attempt + 1} failed: {error}")
            
            if attempt < max_retries - 1:
                time.sleep(self.config.retry_delay)
                
                # Try to recover display
                if "display" in error.lower() or "DISPLAY" in error:
                    self.manager.display_manager.verify_and_recover()
        
        return False, None, f"Failed after {max_retries} attempts"
    
    def _launch_once(self, session: Dict) -> Tuple[bool, Optional[int], str]:
        """Single launch attempt"""
        # Check and update display
        use_display = False
        if self.manager.display:
            if self.manager.display_manager.verify_and_recover():
                use_display = True
                logger.info(f"Using display: {self.manager.display}")
        
        # Build command
        cmd = self.build_command(session, use_display)
        logger.debug(f"Command: {' '.join(cmd)}")
        
        # Prepare environment
        env = os.environ.copy()
        if use_display:
            env['DISPLAY'] = self.manager.display
        
        env['CHROME_LOG_FILE'] = '/dev/null'
        env['G_MESSAGES_DEBUG'] = ''
        env['DBUS_SESSION_BUS_ADDRESS'] = '/dev/null'
        env['GTK_MODULES'] = ''
        
        # Log file for stderr
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
            
            # Wait a moment and check if process died
            time.sleep(2)
            
            if process.poll() is not None:
                # Read the log file for error details
                error_msg = ""
                if log_file.exists():
                    with open(log_file, 'r') as f:
                        error_msg = f.read(500)
                return False, None, f"Process died: {error_msg}"
            
            # Wait for DevTools
            devtools = self.manager._get_devtools(session['port'])
            connected = False
            
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                task = progress.add_task("Connecting to DevTools...", total=None)
                for i in range(30):
                    if process.poll() is not None:
                        error_msg = ""
                        if log_file.exists():
                            with open(log_file, 'r') as f:
                                error_msg = f.read(500)
                        return False, None, f"Process died: {error_msg}"
                    
                    if devtools.wait_for_connection(timeout=2):
                        connected = True
                        break
                    
                    progress.update(task, description=f"Waiting... ({i+1}/30)")
                    time.sleep(2)
            
            if not connected:
                return False, None, "DevTools connection timeout"
            
            logger.info(f"Chrome launched successfully (PID: {process.pid})")
            return True, process.pid, ""
            
        except Exception as e:
            return False, None, str(e)

class SessionSupervisor:
    """Supervise Chrome sessions with health monitoring"""
    
    def __init__(self, manager):
        self.manager = manager
        self.config = manager.config
        self.sessions = {}  # session_id -> session data
        self.running = False
        self.supervisor_thread = None
    
    def start(self):
        """Start supervisor"""
        self.running = True
        self.supervisor_thread = threading.Thread(target=self._supervisor_loop, daemon=True)
        self.supervisor_thread.start()
        logger.info("Session supervisor started")
    
    def stop(self):
        """Stop supervisor"""
        self.running = False
        if self.supervisor_thread:
            self.supervisor_thread.join(timeout=2)
        logger.info("Session supervisor stopped")
    
    def _supervisor_loop(self):
        """Main supervisor loop"""
        while self.running:
            try:
                self._supervise_sessions()
                time.sleep(10)
            except Exception as e:
                logger.error(f"Supervisor error: {e}")
    
    def _supervise_sessions(self):
        """Supervise all sessions"""
        sessions = self.manager.db.list_sessions()
        for session in sessions:
            if session['status'] == 'running':
                self._supervise_session(session)
    
    def _supervise_session(self, session: Dict):
        """Supervise a single session"""
        # Check if session is still in our tracking
        if session['id'] not in self.sessions:
            self.sessions[session['id']] = {
                'started': time.time(),
                'restarts': 0,
                'last_restart': 0
            }
        
        info = self.sessions[session['id']]
        
        # Check if session needs restart
        if self._needs_restart(session):
            info['restarts'] += 1
            info['last_restart'] = time.time()
            
            if info['restarts'] > 5:
                logger.error(f"Session {session['id']} restarted too many times - stopping")
                self.manager.stop_session(session['id'])
                return
            
            logger.info(f"Restarting session {session['id']} (attempt {info['restarts']})")
            self.manager.stop_session(session['id'])
            time.sleep(2)
            self.manager.start_session(session['id'])
    
    def _needs_restart(self, session: Dict) -> bool:
        """Check if session needs restart"""
        # Check PID
        if session['pid']:
            try:
                os.kill(session['pid'], 0)
            except OSError:
                return True
        
        # Check DevTools
        devtools = self.manager._get_devtools(session['port'])
        if not devtools._ensure_connection():
            return True
        
        return False

class ChromeSessionManager:
    """Main session manager - Chrome orchestrator"""
    
    def __init__(self):
        self.config = Config()
        self.db = SessionDB()
        os.makedirs(self.config.base_profile_dir, exist_ok=True)
        
        self.chrome_path = self._find_chrome()
        self.devtools = {}
        
        # Initialize display manager
        self.display_manager = DisplayManager(self.config)
        self.display, self.display_backend = self.display_manager.get_display()
        
        # Initialize other components
        self.js_manager = JavaScriptManager()
        self.is_root = os.geteuid() == 0
        self.wscat_manager = WSCatManager()
        
        # Launcher and supervisor
        self.launcher = ChromeLauncher(self)
        self.supervisor = SessionSupervisor(self)
        self.health_monitor = HealthMonitor(self)
        
        # Display info
        if self.display:
            console.print(f"[green]✅ Using display: {self.display} (backend: {self.display_backend.value})[/green]")
        else:
            console.print("[yellow]⚠️ No display available - using headless mode[/yellow]")
        
        # Start supervisor and health monitor
        self.supervisor.start()
        self.health_monitor.start()
    
    def __del__(self):
        """Cleanup on destruction"""
        self.supervisor.stop()
        self.health_monitor.stop()
    
    def _find_chrome(self):
        """Find Chrome binary with configurable paths"""
        paths = [
            "chromium-browser", "chromium", "google-chrome",
            "google-chrome-stable", "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ]
        for path in paths:
            if shutil.which(path):
                return path
        raise RuntimeError("Chrome not found")
    
    def _get_profile_dir(self, name: str) -> str:
        safe_name = "".join(c for c in name if c.isalnum() or c in " -_").strip()
        return os.path.join(self.config.base_profile_dir, safe_name)
    
    def _get_next_port(self) -> int:
        used_ports = self.db.get_all_ports()
        for port in range(self.config.debug_port_start, self.config.debug_port_end + 1):
            if port in used_ports:
                continue
            if self._is_port_in_use(port):
                continue
            return port
        raise RuntimeError(f"No available ports")
    
    def _get_devtools(self, port: int) -> ChromeDevTools:
        if port not in self.devtools:
            self.devtools[port] = ChromeDevTools(port=port)
        return self.devtools[port]
    
    def _is_port_in_use(self, port: int) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result == 0
    
    def start_session(self, session_id: int):
        """Start a session with retry logic"""
        session = self.db.get_session(session_id)
        if not session:
            console.print(f"[red]Session not found[/red]")
            return
        
        if self._is_port_in_use(session['port']):
            new_port = self._get_next_port()
            console.print(f"[blue]Using port {new_port} instead[/blue]")
            self.db.update_session_port(session_id, new_port)
            session['port'] = new_port
        
        console.print(f"[blue]🚀 Starting session '{session['name']}'...[/blue]")
        
        profile_dir = session['profile_dir']
        os.makedirs(profile_dir, exist_ok=True)
        
        # Launch with retry
        success, pid, error = self.launcher.launch_with_retry(session)
        
        if success:
            self.db.start_session(session_id, pid)
            console.print(f"[green]✅ Session started (PID: {pid})[/green]")
            console.print(f"   Debug: http://127.0.0.1:{session['port']}")
            console.print(f"   URL: {session['url']}")
            console.print(f"   Display: {self.display if self.display else 'Headless'}")
            console.print("[dim]   Chrome is ready for WebSocket connections[/dim]")
        else:
            console.print(f"[red]❌ Failed to start session: {error}[/red]")
            logger.error(f"Session start failed: {error}")
    
    def stop_session(self, session_id: int):
        """Stop a session"""
        session = self.db.get_session(session_id)
        if not session:
            console.print(f"[red]Session not found[/red]")
            return
        
        if session['status'] != 'running':
            console.print(f"[yellow]Session not running[/yellow]")
            return
        
        try:
            if session['pid']:
                os.kill(session['pid'], signal.SIGTERM)
                time.sleep(2)
                try:
                    os.kill(session['pid'], 0)
                    os.kill(session['pid'], signal.SIGKILL)
                except OSError:
                    pass
            
            self.db.stop_session(session_id)
            self.db.release_port(session['port'])
            if session['port'] in self.devtools:
                del self.devtools[session['port']]
            console.print(f"[green]✅ Session stopped[/green]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
    
    def list_sessions(self):
        """List all sessions"""
        sessions = self.db.list_sessions()
        if not sessions:
            console.print("[yellow]No sessions found[/yellow]")
            return
        
        table = Table(title="📋 Chrome Sessions", box=box.ROUNDED)
        table.add_column("ID", style="cyan", width=4)
        table.add_column("Name", style="green")
        table.add_column("URL", style="blue")
        table.add_column("Port", style="yellow", width=6)
        table.add_column("Status", style="magenta", width=10)
        table.add_column("PID", style="red", width=8)
        table.add_column("Profile", style="dim")
        
        for session in sessions:
            status_color = "green" if session['status'] == 'running' else "dim"
            profile_short = os.path.basename(session['profile_dir'])
            table.add_row(
                str(session['id']),
                session['name'],
                session['url'][:30] + "..." if len(session['url']) > 30 else session['url'],
                str(session['port']),
                f"[{status_color}]{session['status']}[/{status_color}]",
                str(session['pid']) if session['pid'] else "-",
                profile_short[:15]
            )
        
        console.print(table)
    
    def show_dashboard(self):
        """Show comprehensive dashboard"""
        sessions = self.db.list_sessions()
        running = [s for s in sessions if s['status'] == 'running']
        stopped = [s for s in sessions if s['status'] == 'stopped']
        total_size = sum(self._get_dir_size_bytes(s['profile_dir']) for s in sessions)
        
        # Display health
        display_status = "❌ None"
        if self.display:
            health = self.display_manager.health
            display_status = f"✅ {self.display} ({self.display_backend.value})"
            if not health.xdpyinfo_ok:
                display_status = f"⚠️ {self.display} (unhealthy)"
        
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
  🔌 wscat: {"✅" if shutil.which('wscat') else "❌"}

[bold]Storage:[/bold]
  📁 Base Directory: {self.config.base_profile_dir}
  📁 Scripts Directory: {self.config.js_scripts_dir}
  🔧 Chrome: {self.chrome_path}
  📁 Log Directory: {self.config.log_dir}
"""
        console.print(Panel(content, title="Dashboard", border_style="cyan"))
    
    def _get_dir_size_bytes(self, path: str) -> int:
        if not os.path.exists(path):
            return 0
        try:
            total = 0
            for root, dirs, files in os.walk(path):
                for f in files:
                    fp = os.path.join(root, f)
                    if os.path.exists(fp):
                        total += os.path.getsize(fp)
            return total
        except:
            return 0
    
    def interactive_menu(self):
        """Main interactive menu"""
        while True:
            console.clear()
            console.print()
            
            header = """
╔══════════════════════════════════════════════════════════════╗
║           🌐 Chrome Session Manager - Production Grade     ║
║           Self-Healing Chrome Orchestrator               ║
╚══════════════════════════════════════════════════════════════╝
            """
            console.print(Panel(header, border_style="cyan"))
            
            sessions = self.db.list_sessions()
            running = len([s for s in sessions if s['status'] == 'running'])
            total = len(sessions)
            available = len(self.db.get_available_ports())
            
            display_status = f"🖥️ Display: {self.display if self.display else '❌ Headless'}"
            backend_status = f"Backend: {self.display_backend.value if self.display else 'None'}"
            status_line = f"📊 {total} sessions | 🟢 {running} running | 🔌 {available} ports | {display_status} | {backend_status}"
            console.print(Panel(status_line, style="dim"))
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
            menu.add_row("D", "[bold]Display Info[/bold]", "Show display information")
            menu.add_row("0", "[red]Exit[/red]", "Exit the manager")
            
            console.print(menu)
            console.print()
            
            choice = Prompt.ask("Select option", choices=["0", "1", "2", "3", "4", "5", "6", "7", "8", "D"])
            
            if choice == "0":
                console.print("[green]Goodbye! 👋[/green]")
                break
            
            elif choice == "1":
                self.create_session()
            
            elif choice == "2":
                self.list_sessions()
                try:
                    session_id = int(Prompt.ask("Enter session ID to start"))
                    self.start_session(session_id)
                except ValueError:
                    console.print("[red]Invalid ID[/red]")
            
            elif choice == "3":
                self.list_sessions()
                try:
                    session_id = int(Prompt.ask("Enter session ID to stop"))
                    self.stop_session(session_id)
                except ValueError:
                    console.print("[red]Invalid ID[/red]")
            
            elif choice == "4":
                self.list_sessions()
            
            elif choice == "5":
                self.list_sessions()
                try:
                    session_id = int(Prompt.ask("Enter session ID"))
                    self.show_session_details(session_id)
                except ValueError:
                    console.print("[red]Invalid ID[/red]")
            
            elif choice == "6":
                self.list_sessions()
                try:
                    session_id = int(Prompt.ask("Enter session ID to delete"))
                    self.delete_session(session_id)
                except ValueError:
                    console.print("[red]Invalid ID[/red]")
            
            elif choice == "7":
                self.show_dashboard()
            
            elif choice == "8":
                self.list_sessions()
                try:
                    session_id = int(Prompt.ask("Enter session ID for tab management"))
                    self.manage_tabs_enhanced(session_id)
                except ValueError:
                    console.print("[red]Invalid ID[/red]")
            
            elif choice == "D":
                self.show_display_info()
            
            if choice != "0":
                console.print()
                Prompt.ask("Press Enter to continue...")
    
    def show_display_info(self):
        """Show detailed display information"""
        console.print(Panel("🖥️ Display Information", style="bold cyan"))
        
        if not self.display:
            console.print("[yellow]No display available - running in headless mode[/yellow]")
            return
        
        health = self.display_manager.health
        content = f"""
[bold]Display:[/bold] {self.display}
[bold]Backend:[/bold] {self.display_backend.value}
[bold]X Socket:[/bold] {"✅" if health.x_socket_ok else "❌"}
[bold]xdpyinfo:[/bold] {"✅" if health.xdpyinfo_ok else "❌"}
[bold]Window Manager:[/bold] {"✅" if health.window_manager_ok else "⚠️"}
[bold]xset:[/bold] {"✅" if health.xset_ok else "❌"}

[bold]Details:[/bold]
"""
        for key, value in health.details.items():
            content += f"  {key}: {value}\n"
        
        console.print(Panel(content, title="Display Details", border_style="green"))
    
    def create_session(self):
        """Create a new session"""
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
        
        profile_dir = self._get_profile_dir(name)
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
        """Delete a session"""
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
        """Show session details"""
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
[bold]Profile Directory:[/bold] {session['profile_dir']}
[bold]Created:[/bold] {session['created_at']}
[bold]Last Used:[/bold] {session['last_used'] if session['last_used'] else 'Never'}
"""
        console.print(Panel(content, title="📊 Session Details", border_style="blue"))

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
