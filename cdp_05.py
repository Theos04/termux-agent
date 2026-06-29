#!/usr/bin/env python3
"""
Enhanced Chrome Session Manager - Root Device Optimized
With VNC persistence and JavaScript management
"""

import os
import time
import subprocess
import shutil
import signal
import sys
import json
import re
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime
import urllib.parse
import socket
import threading
import collections
import hashlib

try:
    import psutil
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
    import psutil

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, IntPrompt, Confirm
    from rich import box
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.text import Text
    from rich.syntax import Syntax
    from rich.layout import Layout
    from rich.live import Live
    from rich.markdown import Markdown
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rich"])
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, IntPrompt, Confirm
    from rich import box
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.text import Text
    from rich.syntax import Syntax

from session_db import SessionDB
import requests
import websocket

console = Console()

# Configuration
BASE_PROFILE_DIR = os.path.expanduser("~/chrome-sessions")
DEBUG_PORT_START = 9222
DEBUG_PORT_END = 9299

# Resource monitoring thresholds
RESOURCE_MONITOR_CONFIG = {
    'cpu_threshold': 50.0,
    'memory_threshold': 512,
    'network_threshold': 1024,
    'check_interval': 5,
    'auto_kill': True,
    'notify_high_usage': True,
    'max_consecutive_violations': 3,
}

# JavaScript storage
JS_SCRIPTS_DIR = os.path.expanduser("~/chrome-scripts")
os.makedirs(JS_SCRIPTS_DIR, exist_ok=True)

class JavaScriptManager:
    """Manage JavaScript scripts for tabs with persistence"""
    
    def __init__(self):
        self.scripts = {}
        self.load_scripts()
    
    def load_scripts(self):
        """Load saved scripts from disk"""
        if os.path.exists(JS_SCRIPTS_DIR):
            for filename in os.listdir(JS_SCRIPTS_DIR):
                if filename.endswith('.json'):
                    try:
                        path = os.path.join(JS_SCRIPTS_DIR, filename)
                        with open(path, 'r') as f:
                            script_data = json.load(f)
                            script_id = filename.replace('.json', '')
                            self.scripts[script_id] = script_data
                    except Exception as e:
                        console.print(f"[dim]Error loading script {filename}: {e}[/dim]")
    
    def save_script(self, script_data: Dict) -> str:
        """Save a script to disk"""
        script_id = hashlib.md5(
            f"{script_data.get('name', '')}_{script_data.get('url', '')}_{time.time()}".encode()
        ).hexdigest()[:8]
        
        script_data['id'] = script_id
        script_data['created'] = datetime.now().isoformat()
        script_data['updated'] = datetime.now().isoformat()
        
        filename = f"{script_id}.json"
        path = os.path.join(JS_SCRIPTS_DIR, filename)
        
        with open(path, 'w') as f:
            json.dump(script_data, f, indent=2)
        
        self.scripts[script_id] = script_data
        return script_id
    
    def update_script(self, script_id: str, script_data: Dict) -> bool:
        """Update an existing script"""
        if script_id not in self.scripts:
            return False
        
        script_data['id'] = script_id
        script_data['updated'] = datetime.now().isoformat()
        if 'created' not in script_data:
            script_data['created'] = self.scripts[script_id].get('created', datetime.now().isoformat())
        
        filename = f"{script_id}.json"
        path = os.path.join(JS_SCRIPTS_DIR, filename)
        
        with open(path, 'w') as f:
            json.dump(script_data, f, indent=2)
        
        self.scripts[script_id] = script_data
        return True
    
    def delete_script(self, script_id: str) -> bool:
        """Delete a script"""
        if script_id not in self.scripts:
            return False
        
        filename = f"{script_id}.json"
        path = os.path.join(JS_SCRIPTS_DIR, filename)
        
        try:
            os.remove(path)
            del self.scripts[script_id]
            return True
        except:
            return False
    
    def get_script(self, script_id: str) -> Optional[Dict]:
        """Get a script by ID"""
        return self.scripts.get(script_id)
    
    def list_scripts(self) -> List[Dict]:
        """List all scripts"""
        return list(self.scripts.values())
    
    def get_scripts_for_url(self, url: str) -> List[Dict]:
        """Get scripts that match a URL pattern"""
        matching = []
        for script in self.scripts.values():
            script_url = script.get('url', '')
            if script_url and (script_url in url or url in script_url):
                matching.append(script)
        return matching

class ChromeDevTools:
    """Chrome DevTools Protocol interface with enhanced features"""

    def __init__(self, host='127.0.0.1', port=9222):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.session = requests.Session()
        self.session.timeout = 3
        self.ws_connection = None

    def _ensure_connection(self) -> bool:
        """Check if Chrome DevTools is accessible"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((self.host, self.port))
            sock.close()
            if result == 0:
                try:
                    response = self.session.get(f"{self.base_url}/json/version", timeout=2)
                    return response.status_code == 200
                except:
                    return True
            return False
        except:
            return False

    def wait_for_connection(self, timeout: int = 30) -> bool:
        """Wait for Chrome to be ready"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._ensure_connection():
                return True
            time.sleep(1)
        return False

    def get_tabs(self) -> List[Dict]:
        try:
            response = self.session.get(f"{self.base_url}/json", timeout=3)
            if response.status_code == 200:
                tabs = response.json()
                return [t for t in tabs if t.get('type') == 'page']
            return []
        except:
            return []

    def create_tab(self, url: str = "about:blank") -> Optional[str]:
        try:
            response = self.session.post(f"{self.base_url}/json/new",
                                       params={'url': url}, timeout=5)
            if response.status_code == 200:
                return response.json().get('id')
            return None
        except:
            return None

    def close_tab(self, tab_id: str) -> bool:
        try:
            response = self.session.post(f"{self.base_url}/json/close/{tab_id}", timeout=5)
            return response.status_code == 200
        except:
            return False

    def _get_websocket_connection(self, tab_id: str):
        """Get WebSocket connection to a tab with origin fix"""
        tab = self.get_tab_by_id(tab_id)
        if not tab:
            return None

        ws_url = tab.get('webSocketDebuggerUrl')
        if not ws_url:
            return None

        try:
            # Add origin header to fix 403 Forbidden
            ws = websocket.create_connection(
                ws_url,
                timeout=5,
                header={
                    'Origin': f'http://{self.host}:{self.port}'
                }
            )
            return ws
        except Exception as e:
            console.print(f"[dim]WebSocket connection error: {e}[/dim]")
            return None

    def execute_script(self, tab_id: str, script: str, return_by_value: bool = True) -> Optional[Dict]:
        """Execute JavaScript in a tab and return the result"""
        try:
            ws = self._get_websocket_connection(tab_id)
            if not ws:
                return None

            msg_id = int(time.time() * 1000)
            command = {
                "id": msg_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": script,
                    "returnByValue": return_by_value,
                    "awaitPromise": True
                }
            }

            ws.send(json.dumps(command))
            response = ws.recv()
            ws.close()

            result = json.loads(response)
            
            # Check for error
            if 'error' in result:
                console.print(f"[red]Script error: {result['error']}[/red]")
                return None
                
            return result.get('result')
        except Exception as e:
            console.print(f"[dim]Error executing script: {e}[/dim]")
            return None

    def execute_script_async(self, tab_id: str, script: str) -> Optional[Dict]:
        """Execute JavaScript asynchronously (fire and forget)"""
        try:
            ws = self._get_websocket_connection(tab_id)
            if not ws:
                return None

            msg_id = int(time.time() * 1000)
            command = {
                "id": msg_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": script,
                    "returnByValue": False,
                    "awaitPromise": False
                }
            }

            ws.send(json.dumps(command))
            return {"status": "executed"}
        except Exception as e:
            console.print(f"[dim]Error executing async script: {e}[/dim]")
            return None

    def get_tab_by_id(self, tab_id: str) -> Optional[Dict]:
        tabs = self.get_tabs()
        for tab in tabs:
            if tab.get('id') == tab_id:
                return tab
        return None

    def get_page_content(self, tab_id: str) -> Optional[str]:
        script = "document.documentElement.outerHTML"
        result = self.execute_script(tab_id, script)
        return result.get('value') if result else None

    def get_page_title(self, tab_id: str) -> Optional[str]:
        script = "document.title"
        result = self.execute_script(tab_id, script)
        return result.get('value') if result else None

    def get_page_text(self, tab_id: str) -> Optional[str]:
        """Get all text content from the page"""
        script = "document.body.innerText"
        result = self.execute_script(tab_id, script)
        return result.get('value') if result else None

    def get_page_json(self, tab_id: str) -> Optional[Dict]:
        """Try to parse page content as JSON"""
        script = """
        (function() {
            try {
                return JSON.parse(document.body.innerText);
            } catch(e) {
                return null;
            }
        })()
        """
        result = self.execute_script(tab_id, script)
        return result.get('value') if result else None

    def get_cookies(self, tab_id: str) -> Optional[List[Dict]]:
        """Get all cookies for the current page"""
        script = """
        (function() {
            return document.cookie.split(';').map(c => {
                const [name, value] = c.trim().split('=');
                return {name, value};
            });
        })()
        """
        result = self.execute_script(tab_id, script)
        return result.get('value') if result else None

    def get_local_storage(self, tab_id: str) -> Optional[Dict]:
        """Get all localStorage items"""
        script = """
        (function() {
            const items = {};
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                items[key] = localStorage.getItem(key);
            }
            return items;
        })()
        """
        result = self.execute_script(tab_id, script)
        return result.get('value') if result else None

    def get_session_storage(self, tab_id: str) -> Optional[Dict]:
        """Get all sessionStorage items"""
        script = """
        (function() {
            const items = {};
            for (let i = 0; i < sessionStorage.length; i++) {
                const key = sessionStorage.key(i);
                items[key] = sessionStorage.getItem(key);
            }
            return items;
        })()
        """
        result = self.execute_script(tab_id, script)
        return result.get('value') if result else None

    def click_element(self, tab_id: str, selector: str) -> bool:
        """Click an element by CSS selector"""
        script = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (el) {{
                el.click();
                return true;
            }}
            return false;
        }})()
        """
        result = self.execute_script(tab_id, script)
        return result.get('value') if result else False

    def fill_input(self, tab_id: str, selector: str, value: str) -> bool:
        """Fill an input field by CSS selector"""
        script = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (el) {{
                el.value = '{value}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }}
            return false;
        }})()
        """
        result = self.execute_script(tab_id, script)
        return result.get('value') if result else False

    def scroll_to_element(self, tab_id: str, selector: str) -> bool:
        """Scroll to an element by CSS selector"""
        script = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (el) {{
                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                return true;
            }}
            return false;
        }})()
        """
        result = self.execute_script(tab_id, script)
        return result.get('value') if result else False

    def get_element_text(self, tab_id: str, selector: str) -> Optional[str]:
        """Get text content of an element by CSS selector"""
        script = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            return el ? el.textContent : null;
        }})()
        """
        result = self.execute_script(tab_id, script)
        return result.get('value') if result else None

    def get_element_attribute(self, tab_id: str, selector: str, attribute: str) -> Optional[str]:
        """Get attribute of an element by CSS selector"""
        script = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            return el ? el.getAttribute('{attribute}') : null;
        }})()
        """
        result = self.execute_script(tab_id, script)
        return result.get('value') if result else None

    def get_all_links(self, tab_id: str) -> List[str]:
        """Get all links from the page"""
        script = """
        (function() {
            return Array.from(document.querySelectorAll('a'))
                .map(a => a.href)
                .filter(href => href && href.startsWith('http'));
        })()
        """
        result = self.execute_script(tab_id, script)
        return result.get('value') if result else []

    def get_all_images(self, tab_id: str) -> List[str]:
        """Get all image URLs from the page"""
        script = """
        (function() {
            return Array.from(document.querySelectorAll('img'))
                .map(img => img.src)
                .filter(src => src && src.startsWith('http'));
        })()
        """
        result = self.execute_script(tab_id, script)
        return result.get('value') if result else []

    def get_all_scripts(self, tab_id: str) -> List[str]:
        """Get all script tags from the page"""
        script = """
        (function() {
            return Array.from(document.querySelectorAll('script'))
                .map(script => script.src || script.textContent)
                .filter(content => content && content.length > 0);
        })()
        """
        result = self.execute_script(tab_id, script)
        return result.get('value') if result else []

    def get_all_styles(self, tab_id: str) -> List[str]:
        """Get all styles from the page"""
        script = """
        (function() {
            return Array.from(document.querySelectorAll('style, link[rel="stylesheet"]'))
                .map(el => el.textContent || el.href)
                .filter(content => content && content.length > 0);
        })()
        """
        result = self.execute_script(tab_id, script)
        return result.get('value') if result else []

    def get_page_metadata(self, tab_id: str) -> Dict:
        """Get comprehensive page metadata"""
        script = """
        (function() {
            const meta = {
                title: document.title,
                url: window.location.href,
                domain: window.location.hostname,
                description: '',
                keywords: '',
                author: '',
                viewport: '',
                charset: document.characterSet,
                language: document.documentElement.lang,
                contentLength: document.documentElement.outerHTML.length
            };

            // Parse meta tags
            document.querySelectorAll('meta').forEach(el => {
                const name = el.getAttribute('name') || el.getAttribute('property');
                const content = el.getAttribute('content');
                if (name && content) {
                    if (name.includes('description')) meta.description = content;
                    if (name.includes('keywords')) meta.keywords = content;
                    if (name.includes('author')) meta.author = content;
                    if (name.includes('viewport')) meta.viewport = content;
                }
            });

            return meta;
        })()
        """
        result = self.execute_script(tab_id, script)
        return result.get('value') if result else {}

    def navigate_to(self, tab_id: str, url: str) -> bool:
        script = f"window.location.href = '{url}'"
        result = self.execute_script(tab_id, script)
        return result is not None

    def get_version_info(self) -> Optional[Dict]:
        try:
            response = self.session.get(f"{self.base_url}/json/version", timeout=3)
            if response.status_code == 200:
                return response.json()
            return None
        except:
            return None

    def save_page_content(self, tab_id: str, filename: str) -> bool:
        """Save page content to a file with proper formatting"""
        try:
            content = self.get_page_content(tab_id)
            if content:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)
                return True
            return False
        except:
            return False

class VNCManager:
    """Manage VNC server instances with persistence"""
    
    def __init__(self):
        self.vnc_display = None
        self.vnc_pid = None
        self.lock_files = []
        self._detect_vnc()
    
    def _detect_vnc(self):
        """Detect existing VNC server"""
        try:
            result = subprocess.run(['vncserver', '-list'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    match = re.search(r':(\d+)\s+(\d+)', line)
                    if match:
                        display_num = int(match.group(1))
                        pid = int(match.group(2))
                        self.vnc_display = f":{display_num}"
                        self.vnc_pid = pid
                        console.print(f"[green]✅ Found existing VNC on display {self.vnc_display} (PID: {pid})[/green]")
                        return True
        except:
            pass
        return False
    
    def ensure_vnc(self) -> Optional[str]:
        """Ensure VNC is running, start if needed"""
        if self.vnc_display and self.vnc_pid:
            # Verify it's still running
            try:
                os.kill(self.vnc_pid, 0)
                return self.vnc_display
            except OSError:
                self.vnc_display = None
                self.vnc_pid = None
        
        # Try to find an available display
        for display_num in range(1, 10):
            display = f":{display_num}"
            try:
                # Check if display is in use
                result = subprocess.run(['vncserver', '-list'], 
                                      capture_output=True, text=True, timeout=5)
                if display in result.stdout:
                    continue
                
                # Try to start VNC on this display
                result = subprocess.run(['vncserver', display], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    self.vnc_display = display
                    # Get PID
                    result = subprocess.run(['vncserver', '-list'], 
                                          capture_output=True, text=True, timeout=5)
                    for line in result.stdout.split('\n'):
                        if display in line:
                            match = re.search(r':\d+\s+(\d+)', line)
                            if match:
                                self.vnc_pid = int(match.group(1))
                    console.print(f"[green]✅ Started VNC on display {display}[/green]")
                    return display
            except Exception as e:
                console.print(f"[dim]Could not start VNC on {display}: {e}[/dim]")
                continue
        
        console.print("[red]❌ Could not start VNC server[/red]")
        return None
    
    def cleanup(self):
        """Clean up VNC lock files if they exist"""
        if self.vnc_display:
            display_num = self.vnc_display.replace(':', '')
            lock_file = f"/data/data/com.termux/files/usr/tmp/.X{display_num}-lock"
            socket_dir = f"/data/data/com.termux/files/usr/tmp/.X11-unix/X{display_num}"
            
            try:
                # Check if the lock file exists but the process is dead
                if os.path.exists(lock_file):
                    try:
                        with open(lock_file, 'r') as f:
                            pid = int(f.read().strip())
                        # Check if process is running
                        os.kill(pid, 0)
                        # Process is running, don't clean
                    except (OSError, ValueError):
                        # Process is dead or invalid, clean up
                        os.remove(lock_file)
                        console.print(f"[dim]Cleaned up lock file: {lock_file}[/dim]")
                
                if os.path.exists(socket_dir):
                    os.remove(socket_dir)
                    console.print(f"[dim]Cleaned up socket: {socket_dir}[/dim]")
            except Exception as e:
                console.print(f"[dim]Could not clean up VNC files: {e}[/dim]")

class ResourceMonitor:
    """Monitor and manage high-resource-consuming tabs with root capabilities"""
    
    def __init__(self, session_manager):
        self.session_manager = session_manager
        self.monitoring = False
        self.monitor_thread = None
        self.tab_metrics = {}
        self.violation_counts = {}
        self.alert_callbacks = []
        self.lock = threading.Lock()
        self.root_available = os.geteuid() == 0
        
    def add_alert_callback(self, callback):
        """Add a callback for resource alerts"""
        self.alert_callbacks.append(callback)
    
    def get_tab_process_info(self, tab_id: str, session_port: int) -> Optional[Dict]:
        """Get detailed process info for a tab using root access if available"""
        try:
            chrome_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cpu_percent', 'memory_info', 'connections']):
                try:
                    name = proc.info['name'].lower()
                    if 'chrome' in name or 'chromium' in name:
                        chrome_processes.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            port_str = f"--remote-debugging-port={session_port}"
            target_processes = []
            for proc in chrome_processes:
                try:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if port_str in cmdline:
                        target_processes.append(proc)
                except:
                    continue
            
            if not target_processes:
                return None
            
            if self.root_available:
                try:
                    for proc in target_processes:
                        children = proc.children(recursive=True)
                        for child in children:
                            try:
                                cmdline = ' '.join(child.cmdline())
                                if '--type=renderer' in cmdline:
                                    return self._get_detailed_process_info(child)
                            except:
                                continue
                except:
                    pass
            
            if target_processes:
                return self._get_detailed_process_info(target_processes[0])
                
            return None
        except Exception as e:
            console.print(f"[dim]Error getting process info: {e}[/dim]")
            return None
    
    def _get_detailed_process_info(self, process: psutil.Process) -> Dict:
        """Get detailed process information with root enhancements"""
        try:
            info = {
                'pid': process.pid,
                'cpu_percent': process.cpu_percent(interval=0.5),
                'memory_mb': process.memory_info().rss / (1024 * 1024),
                'connections': len(process.connections()),
                'threads': process.num_threads(),
                'create_time': process.create_time(),
            }
            
            if self.root_available:
                try:
                    io_counters = process.io_counters()
                    info['io_read'] = io_counters.read_bytes
                    info['io_write'] = io_counters.write_bytes
                    
                    mem_full = process.memory_full_info()
                    info['uss'] = mem_full.uss / (1024 * 1024) if hasattr(mem_full, 'uss') else 0
                    info['pss'] = mem_full.pss / (1024 * 1024) if hasattr(mem_full, 'pss') else 0
                    
                    info['nice'] = process.nice()
                except:
                    pass
            
            return info
        except:
            return None
    
    def get_tab_resource_usage(self, session_id: int) -> Dict[int, Dict]:
        """Get resource usage for all tabs in a session"""
        session = self.session_manager.db.get_session(session_id)
        if not session:
            return {}
        
        if session['status'] != 'running':
            return {}
        
        devtools = self.session_manager._get_devtools(session['port'])
        if not devtools._ensure_connection():
            return {}
        
        try:
            tabs = devtools.get_tabs()
            results = {}
            
            for i, tab in enumerate(tabs):
                tab_id = tab.get('id')
                if not tab_id:
                    continue
                
                proc_info = self.get_tab_process_info(tab_id, session['port'])
                js_metrics = self._get_tab_js_metrics(devtools, tab_id)
                
                metrics = {
                    'tab_id': tab_id,
                    'tab_index': i + 1,
                    'title': tab.get('title', 'Unknown'),
                    'url': tab.get('url', ''),
                    'timestamp': time.time(),
                }
                
                if proc_info:
                    metrics.update(proc_info)
                
                if js_metrics:
                    metrics.update(js_metrics)
                
                results[i + 1] = metrics
            
            return results
        except Exception as e:
            console.print(f"[dim]Error getting tab resources: {e}[/dim]")
            return {}
    
    def _get_tab_js_metrics(self, devtools, tab_id: str) -> Dict:
        """Get JavaScript-level metrics from the tab"""
        script = """
        (function() {
            const metrics = {};
            
            if (window.performance && window.performance.memory) {
                metrics.js_heap = {
                    used: window.performance.memory.usedJSHeapSize / (1024 * 1024),
                    total: window.performance.memory.totalJSHeapSize / (1024 * 1024),
                    limit: window.performance.memory.jsHeapSizeLimit / (1024 * 1024)
                };
            }
            
            metrics.dom = {
                elements: document.getElementsByTagName('*').length,
                images: document.images.length,
                scripts: document.scripts.length,
                styles: document.styleSheets.length,
                iframes: document.getElementsByTagName('iframe').length
            };
            
            if (window.performance && window.performance.timing) {
                const timing = window.performance.timing;
                metrics.performance = {
                    loadTime: timing.loadEventEnd - timing.navigationStart,
                    domReady: timing.domContentLoadedEventEnd - timing.navigationStart,
                    responseTime: timing.responseEnd - timing.requestStart
                };
            }
            
            metrics.websockets = 0;
            metrics.event_listeners = 0;
            
            return metrics;
        })()
        """
        
        try:
            result = devtools.execute_script(tab_id, script)
            return result.get('value', {}) if result else {}
        except:
            return {}
    
    def check_resource_violations(self, session_id: int) -> List[Dict]:
        """Check for resource violations and return tabs exceeding thresholds"""
        violations = []
        metrics = self.get_tab_resource_usage(session_id)
        
        for tab_index, tab_metrics in metrics.items():
            violation = self._check_single_tab(tab_index, tab_metrics)
            if violation:
                violations.append(violation)
        
        return violations
    
    def _check_single_tab(self, tab_index: int, metrics: Dict) -> Optional[Dict]:
        """Check if a single tab exceeds resource thresholds"""
        violations = []
        
        cpu = metrics.get('cpu_percent', 0)
        if cpu > RESOURCE_MONITOR_CONFIG['cpu_threshold']:
            violations.append(f"CPU: {cpu:.1f}% (threshold: {RESOURCE_MONITOR_CONFIG['cpu_threshold']}%)")
        
        memory = metrics.get('memory_mb', 0)
        if memory > RESOURCE_MONITOR_CONFIG['memory_threshold']:
            violations.append(f"Memory: {memory:.1f} MB (threshold: {RESOURCE_MONITOR_CONFIG['memory_threshold']} MB)")
        
        dom_elements = metrics.get('dom', {}).get('elements', 0)
        if dom_elements > 5000:
            violations.append(f"DOM Elements: {dom_elements} (excessive)")
        
        js_heap = metrics.get('js_heap', {}).get('used', 0)
        if js_heap > 200:
            violations.append(f"JS Heap: {js_heap:.1f} MB (excessive)")
        
        if violations:
            return {
                'tab_index': tab_index,
                'tab_title': metrics.get('title', 'Unknown'),
                'tab_url': metrics.get('url', ''),
                'metrics': metrics,
                'violations': violations,
                'timestamp': time.time()
            }
        
        return None
    
    def monitor_session(self, session_id: int, callback=None):
        """Continuously monitor a session for resource issues"""
        session = self.session_manager.db.get_session(session_id)
        if not session:
            console.print(f"[red]Session {session_id} not found[/red]")
            return
        
        console.print(f"[blue]🔍 Monitoring session '{session['name']}' for resource issues...[/blue]")
        console.print(f"[dim]CPU threshold: {RESOURCE_MONITOR_CONFIG['cpu_threshold']}%[/dim]")
        console.print(f"[dim]Memory threshold: {RESOURCE_MONITOR_CONFIG['memory_threshold']} MB[/dim]")
        console.print(f"[dim]Check interval: {RESOURCE_MONITOR_CONFIG['check_interval']}s[/dim]")
        
        self.monitoring = True
        
        try:
            violation_count = 0
            while self.monitoring and session['status'] == 'running':
                violations = self.check_resource_violations(session_id)
                
                if violations:
                    for violation in violations:
                        violation_count += 1
                        self._handle_violation(session, violation, violation_count)
                        
                        tab_key = f"{session_id}_{violation['tab_index']}"
                        self.violation_counts[tab_key] = self.violation_counts.get(tab_key, 0) + 1
                        
                        if (RESOURCE_MONITOR_CONFIG['auto_kill'] and 
                            self.violation_counts[tab_key] >= RESOURCE_MONITOR_CONFIG['max_consecutive_violations']):
                            self._auto_kill_tab(session, violation)
                            self.violation_counts[tab_key] = 0
                else:
                    for key in list(self.violation_counts.keys()):
                        if key.startswith(f"{session_id}_"):
                            self.violation_counts[key] = max(0, self.violation_counts[key] - 1)
                
                if callback:
                    callback(violations)
                
                time.sleep(RESOURCE_MONITOR_CONFIG['check_interval'])
                session = self.session_manager.db.get_session(session_id)
                
        except KeyboardInterrupt:
            console.print("\n[yellow]Monitoring stopped[/yellow]")
        finally:
            self.monitoring = False
    
    def _handle_violation(self, session, violation: Dict, count: int):
        """Handle a resource violation"""
        tab_info = f"Tab {violation['tab_index']}: {violation['tab_title'][:30]}"
        
        if RESOURCE_MONITOR_CONFIG['notify_high_usage']:
            console.print(f"[yellow]⚠️ HIGH RESOURCE USAGE - {tab_info}[/yellow]")
            for v in violation['violations']:
                console.print(f"[dim]  • {v}[/dim]")
            console.print(f"[dim]  Violation count: {count}[/dim]")
        
        for callback in self.alert_callbacks:
            try:
                callback(session, violation)
            except Exception as e:
                console.print(f"[red]Alert callback error: {e}[/red]")
    
    def _auto_kill_tab(self, session, violation: Dict):
        """Automatically kill a high-resource tab"""
        tab_index = violation['tab_index']
        tab_title = violation['tab_title']
        
        console.print(f"[red]🔪 AUTO-KILLING tab {tab_index}: {tab_title}[/red]")
        
        devtools = self.session_manager._get_devtools(session['port'])
        if devtools._ensure_connection():
            tabs = devtools.get_tabs()
            if tabs and tab_index <= len(tabs):
                tab_id = tabs[tab_index - 1]['id']
                if devtools.close_tab(tab_id):
                    console.print(f"[green]✅ Tab killed successfully[/green]")
                    
                    self.session_manager.db.add_history(
                        session['id'],
                        f"Auto-killed high-resource tab {tab_index}",
                        f"Title: {tab_title}, Violations: {', '.join(violation['violations'])}"
                    )
                else:
                    console.print(f"[red]❌ Failed to kill tab[/red]")
    
    def start_monitoring(self, session_id: int):
        """Start monitoring in a background thread"""
        if self.monitor_thread and self.monitor_thread.is_alive():
            console.print("[yellow]Monitoring already running[/yellow]")
            return
        
        def monitor_wrapper():
            self.monitor_session(session_id)
        
        self.monitor_thread = threading.Thread(target=monitor_wrapper, daemon=True)
        self.monitor_thread.start()
        console.print(f"[green]✅ Monitoring started for session {session_id}[/green]")
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        console.print("[green]✅ Monitoring stopped[/green]")

class ChromeSessionManager:
    def __init__(self):
        self.db = SessionDB()
        os.makedirs(BASE_PROFILE_DIR, exist_ok=True)
        self.chrome_path = self._find_chrome()
        self.devtools = {}
        self.vnc_manager = VNCManager()
        self.display = self.vnc_manager.ensure_vnc()
        self.script_history = []
        self.resource_monitor = ResourceMonitor(self)
        self.js_manager = JavaScriptManager()
        self.is_root = os.geteuid() == 0
        
        if self.display:
            os.environ['DISPLAY'] = self.display
            console.print(f"[green]✅ Using display: {self.display}[/green]")
        else:
            console.print("[yellow]⚠️ No display available. Running in headless mode.[/yellow]")
        
        if self.is_root:
            console.print("[green]✅ Running as root - enhanced capabilities available[/green]")
        else:
            console.print("[yellow]⚠️ Not running as root - some monitoring features limited[/yellow]")

    def _find_chrome(self):
        paths = [
            "chromium-browser", "chromium", "google-chrome",
            "google-chrome-stable", "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/data/data/com.termux/files/usr/bin/chromium-browser",
        ]
        for path in paths:
            if shutil.which(path):
                return path
        raise RuntimeError("Chrome not found. Install chromium-browser")

    def _get_profile_dir(self, name: str) -> str:
        safe_name = "".join(c for c in name if c.isalnum() or c in " -_").strip()
        return os.path.join(BASE_PROFILE_DIR, safe_name)

    def _get_next_port(self) -> int:
        used_ports = self.db.get_all_ports()
        for port in range(DEBUG_PORT_START, DEBUG_PORT_END + 1):
            if port in used_ports:
                continue
            if self._is_port_in_use(port):
                continue
            return port
        raise RuntimeError(f"No available ports in range {DEBUG_PORT_START}-{DEBUG_PORT_END}")

    def _get_devtools(self, port: int) -> ChromeDevTools:
        if port not in self.devtools:
            self.devtools[port] = ChromeDevTools(port=port)
        return self.devtools[port]

    def _cleanup_zombie_sessions(self):
        sessions = self.db.list_sessions()
        cleaned = 0

        for session in sessions:
            if session['status'] == 'running' and session['pid']:
                try:
                    os.kill(session['pid'], 0)
                    try:
                        proc = psutil.Process(session['pid'])
                        if 'chromium' not in proc.name().lower() and 'chrome' not in proc.name().lower():
                            self.db.stop_session(session['id'])
                            self.db.release_port(session['port'])
                            cleaned += 1
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        self.db.stop_session(session['id'])
                        self.db.release_port(session['port'])
                        cleaned += 1
                except OSError:
                    self.db.stop_session(session['id'])
                    self.db.release_port(session['port'])
                    cleaned += 1

        return cleaned

    def _get_dir_size(self, path: str) -> str:
        if not os.path.exists(path):
            return "N/A"
        try:
            total = 0
            for root, dirs, files in os.walk(path):
                for f in files:
                    fp = os.path.join(root, f)
                    if os.path.exists(fp):
                        total += os.path.getsize(fp)

            for unit in ['B', 'KB', 'MB', 'GB']:
                if total < 1024.0:
                    return f"{total:.1f} {unit}"
                total /= 1024.0
            return f"{total:.1f} TB"
        except:
            return "Unknown"

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

    def _format_size(self, size_bytes: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    def _is_port_in_use(self, port: int) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result == 0

    def _ensure_vnc_running(self):
        """Ensure VNC is running, restart if needed"""
        if not self.display:
            self.display = self.vnc_manager.ensure_vnc()
            if self.display:
                os.environ['DISPLAY'] = self.display
                console.print(f"[green]✅ Restored display: {self.display}[/green]")
            else:
                console.print("[red]❌ Could not restore VNC display[/red]")
        return self.display is not None

    def create_session(self):
        console.print()
        console.print(Panel("🆕 Create New Chrome Session", style="bold green"))

        self._cleanup_zombie_sessions()
        self._ensure_vnc_running()

        while True:
            name = Prompt.ask("📝 Session name (e.g., whatsapp)")
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
                        console.print(f"[red]Port {port} is already in use by another session[/red]")
                        continue
                    if self._is_port_in_use(port):
                        console.print(f"[red]Port {port} is already in use by another process[/red]")
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
                console.print("[yellow]Port conflict detected. Trying another port...[/yellow]")
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

        if Confirm.ask("🔍 Enable resource monitoring for this session?"):
            self._configure_monitoring()
            if Confirm.ask("🚀 Start this session with monitoring?"):
                self.start_session(session_id)
                time.sleep(3)
                self.resource_monitor.start_monitoring(session_id)
        else:
            if Confirm.ask("🚀 Start this session now?"):
                self.start_session(session_id)

    def _configure_monitoring(self):
        """Configure resource monitoring thresholds"""
        console.print("\n[bold cyan]📊 Resource Monitor Configuration[/bold cyan]")
        
        console.print("\n[bold]Current settings:[/bold]")
        console.print(f"  CPU threshold: {RESOURCE_MONITOR_CONFIG['cpu_threshold']}%")
        console.print(f"  Memory threshold: {RESOURCE_MONITOR_CONFIG['memory_threshold']} MB")
        console.print(f"  Check interval: {RESOURCE_MONITOR_CONFIG['check_interval']}s")
        console.print(f"  Auto-kill: {'Enabled' if RESOURCE_MONITOR_CONFIG['auto_kill'] else 'Disabled'}")
        console.print(f"  Max violations: {RESOURCE_MONITOR_CONFIG['max_consecutive_violations']}")
        
        if Confirm.ask("\nAdjust settings?"):
            try:
                cpu = float(Prompt.ask("CPU threshold (%)", default=str(RESOURCE_MONITOR_CONFIG['cpu_threshold'])))
                RESOURCE_MONITOR_CONFIG['cpu_threshold'] = cpu
                
                memory = float(Prompt.ask("Memory threshold (MB)", default=str(RESOURCE_MONITOR_CONFIG['memory_threshold'])))
                RESOURCE_MONITOR_CONFIG['memory_threshold'] = memory
                
                interval = int(Prompt.ask("Check interval (seconds)", default=str(RESOURCE_MONITOR_CONFIG['check_interval'])))
                RESOURCE_MONITOR_CONFIG['check_interval'] = interval
                
                auto_kill = Confirm.ask("Enable auto-kill for high-resource tabs?")
                RESOURCE_MONITOR_CONFIG['auto_kill'] = auto_kill
                
                max_violations = int(Prompt.ask("Max consecutive violations before killing", 
                                               default=str(RESOURCE_MONITOR_CONFIG['max_consecutive_violations'])))
                RESOURCE_MONITOR_CONFIG['max_consecutive_violations'] = max_violations
                
                console.print("[green]✅ Monitoring settings updated[/green]")
            except ValueError:
                console.print("[red]Invalid input. Keeping current settings.[/red]")

    def start_session(self, session_id: int):
        if not self._ensure_vnc_running():
            console.print("[yellow]⚠️ No VNC display available. Running headless.[/yellow]")
        
        session = self.db.get_session(session_id)
        if not session:
            console.print(f"[red]Session {session_id} not found[/red]")
            return

        if session['status'] == 'running' and session['pid']:
            try:
                os.kill(session['pid'], 0)
                console.print(f"[yellow]Session '{session['name']}' is already running (PID: {session['pid']})[/yellow]")
                if Confirm.ask("Restart it?"):
                    self.stop_session(session_id)
                    time.sleep(2)
                else:
                    return
            except OSError:
                console.print(f"[yellow]Cleaning up dead PID {session['pid']}[/yellow]")
                self.db.stop_session(session_id)
                self.db.release_port(session['port'])

        if self._is_port_in_use(session['port']):
            console.print(f"[yellow]Port {session['port']} is already in use. Trying next available port...[/yellow]")
            new_port = self._get_next_port()
            console.print(f"[blue]Using port {new_port} instead[/blue]")
            self.db.update_session_port(session_id, new_port)
            session['port'] = new_port

        console.print(f"[blue]🚀 Starting session '{session['name']}'...[/blue]")

        profile_dir = session['profile_dir']
        os.makedirs(profile_dir, exist_ok=True)

        # Chrome flags with proper origin allow
        cmd = [
            self.chrome_path,
            f"--remote-debugging-port={session['port']}",
            f"--remote-allow-origins=http://127.0.0.1:{session['port']}",
            "--remote-allow-origins=*",  # Allow all origins for WebSocket
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--disable-extensions",
            "--disable-gpu",
            "--window-size=1366,768",
        ]

        if self.is_root:
            cmd.extend([
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--disable-accelerated-jpeg-decoding",
                "--disable-accelerated-mjpeg-decode",
                "--disable-accelerated-video-decode",
                "--disable-accelerated-video-encode",
                "--disable-gpu-driver-bug-workarounds",
                "--disable-gpu-process-crash-limit",
                "--disable-gpu-sandbox",
                "--disable-software-rasterizer",
                "--disable-webgl",
                "--disable-webgl2",
                "--disable-3d-apis",
                "--disable-glsl-translator",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-features=VizDisplayCompositor",
                "--disable-features=WebRtcUseEchoCancellation3",
            ])

        if self.display:
            cmd.extend([
                "--start-maximized",
                session['url']
            ])
            console.print(f"[green]🖥️ Using display: {self.display}[/green]")
        else:
            console.print("[yellow]⚠️ No display available. Running in headless mode.[/yellow]")
            cmd.extend([
                "--headless",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                f"--window-size=1366,768",
                session['url']
            ])

        if 'TERMUX_VERSION' in os.environ or 'com.termux' in os.environ.get('PREFIX', ''):
            cmd.extend([
                "--disable-dbus",
                "--disable-namespace-sandbox",
                "--disable-web-security",
            ])

        try:
            env = os.environ.copy()
            if self.display:
                env['DISPLAY'] = self.display

            if self.is_root:
                try:
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        start_new_session=True,
                        text=True,
                        env=env,
                        preexec_fn=lambda: os.nice(-10) if os.geteuid() == 0 else None
                    )
                except:
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        start_new_session=True,
                        text=True,
                        env=env
                    )
            else:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                    text=True,
                    env=env
                )

            console.print("[yellow]⏳ Waiting for Chrome to start...[/yellow]")

            time.sleep(2)

            if process.poll() is not None:
                stdout, stderr = process.communicate()
                console.print("[red]❌ Chrome process died immediately[/red]")
                if stderr:
                    console.print(f"[dim]Error: {stderr[:500]}[/dim]")
                return

            devtools = self._get_devtools(session['port'])
            connected = False

            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                task = progress.add_task("Connecting...", total=None)
                for i in range(30):
                    if process.poll() is not None:
                        stdout, stderr = process.communicate()
                        console.print("[red]❌ Chrome process died[/red]")
                        if stderr:
                            console.print(f"[dim]Error: {stderr[:500]}[/dim]")
                        break

                    if devtools.wait_for_connection(timeout=2):
                        connected = True
                        break

                    progress.update(task, description=f"Waiting... ({i+1}/30)")
                    time.sleep(2)

            if process.poll() is None and connected:
                self.db.start_session(session_id, process.pid)
                console.print(f"[green]✅ Session started (PID: {process.pid})[/green]")
                console.print(f"   Debug: http://127.0.0.1:{session['port']}")
                console.print(f"   URL: {session['url']}")
                console.print(f"   Profile: {profile_dir}")

                if self.is_root:
                    console.print("[green]🔒 Running with root privileges[/green]")

                if not self.display:
                    console.print("[yellow]ℹ️ Running in headless mode. Use DevTools to interact.[/yellow]")
                else:
                    console.print(f"[green]🖥️ Chrome window should appear on display {self.display}[/green]")

                version_info = devtools.get_version_info()
                if version_info:
                    console.print(f"[dim]   Chrome: {version_info.get('Browser', 'Unknown')}[/dim]")

                try:
                    tabs = devtools.get_tabs()
                    if tabs:
                        console.print(f"[dim]📑 {len(tabs)} tabs open[/dim]")
                    else:
                        console.print("[dim]📑 No tabs found (Chrome may still be loading)[/dim]")
                except:
                    console.print("[dim]📑 Could not retrieve tab info[/dim]")

            elif process.poll() is None and not connected:
                console.print("[yellow]⚠️ Chrome started but DevTools not responding[/yellow]")
                console.print(f"[dim]   Check manually: http://127.0.0.1:{session['port']}[/dim]")
                console.print(f"[dim]   Process is running (PID: {process.pid})[/dim]")
                self.db.start_session(session_id, process.pid)
            else:
                console.print("[red]❌ Failed to start Chrome[/red]")
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    console.print(f"[red]Process exited with code: {process.returncode}[/red]")
                    if stderr:
                        console.print(f"[dim]Error output: {stderr[:500]}[/dim]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback
            traceback.print_exc()

    def stop_session(self, session_id: int):
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
        sessions = self.db.list_sessions()

        if not sessions:
            console.print("[yellow]No sessions found[/yellow]")
            return

        for session in sessions:
            if session['status'] == 'running' and session['pid']:
                try:
                    os.kill(session['pid'], 0)
                except OSError:
                    self.db.stop_session(session['id'])
                    self.db.release_port(session['port'])
                    session['status'] = 'stopped'
                    session['pid'] = None

        sessions = self.db.list_sessions()

        table = Table(title="📋 Chrome Sessions", box=box.ROUNDED)
        table.add_column("ID", style="cyan", width=4)
        table.add_column("Name", style="green")
        table.add_column("URL", style="blue")
        table.add_column("Port", style="yellow", width=6)
        table.add_column("Status", style="magenta", width=10)
        table.add_column("PID", style="red", width=8)
        table.add_column("Monitoring", style="cyan", width=12)
        table.add_column("Profile", style="dim")
        table.add_column("Last Used", style="dim", width=16)

        for session in sessions:
            status_color = "green" if session['status'] == 'running' else "dim"
            profile_short = os.path.basename(session['profile_dir'])
            monitoring = "🔍 Active" if self.resource_monitor.monitoring else "-"
            table.add_row(
                str(session['id']),
                session['name'],
                session['url'][:30] + "..." if len(session['url']) > 30 else session['url'],
                str(session['port']),
                f"[{status_color}]{session['status']}[/{status_color}]",
                str(session['pid']) if session['pid'] else "-",
                monitoring,
                profile_short[:15],
                session['last_used'][:16] if session['last_used'] else "-"
            )

        console.print(table)

    def show_session_details(self, session_id: int):
        session = self.db.get_session(session_id)
        if not session:
            console.print(f"[red]Session not found[/red]")
            return

        history = self.db.get_history(session_id, limit=10)

        status = session['status']
        pid_status = ""
        if session['status'] == 'running' and session['pid']:
            try:
                os.kill(session['pid'], 0)
                pid_status = "✅ Alive"
            except OSError:
                pid_status = "❌ Dead"
                status = "zombie"

        content = f"""
[bold cyan]Session Details[/bold cyan]

[bold]ID:[/bold] {session['id']}
[bold]Name:[/bold] {session['name']}
[bold]URL:[/bold] {session['url']}
[bold]Port:[/bold] {session['port']}
[bold]Status:[/bold] {status}
[bold]PID:[/bold] {session['pid'] if session['pid'] else 'N/A'} {pid_status}
[bold]Profile Directory:[/bold] {session['profile_dir']}
[bold]Profile Size:[/bold] {self._get_dir_size(session['profile_dir'])}
[bold]Created:[/bold] {session['created_at']}
[bold]Updated:[/bold] {session['updated_at']}
[bold]Last Used:[/bold] {session['last_used'] if session['last_used'] else 'Never'}
[bold]Notes:[/bold] {session['notes'] if session['notes'] else 'None'}
[bold]Monitoring:[/bold] {"🔍 Active" if self.resource_monitor.monitoring else "❌ Inactive"}
[bold]Root Access:[/bold] {"✅ Yes" if self.is_root else "❌ No"}
[bold]Display:[/bold] {self.display if self.display else "❌ None"}

[bold cyan]Recent History:[/bold cyan]
"""

        if history:
            for entry in history[:5]:
                content += f"  • {entry['timestamp']}: {entry['action']}"
                if entry['details']:
                    content += f" ({entry['details']})"
                content += "\n"
        else:
            content += "  No history available\n"

        console.print(Panel(content, title="📊 Session Details", border_style="blue"))

        if self.resource_monitor.monitoring:
            console.print("\n[bold cyan]Current Resource Usage:[/bold cyan]")
            self.show_resource_usage(session_id)

    def show_resource_usage(self, session_id: int):
        """Display current resource usage for tabs in a session"""
        metrics = self.resource_monitor.get_tab_resource_usage(session_id)
        
        if not metrics:
            console.print("[yellow]No tab metrics available[/yellow]")
            return
        
        table = Table(title="📊 Tab Resource Usage", box=box.ROUNDED)
        table.add_column("Tab", style="cyan", width=6)
        table.add_column("Title", style="green", no_wrap=False)
        table.add_column("CPU %", style="yellow", width=8)
        table.add_column("Memory (MB)", style="red", width=12)
        table.add_column("Threads", style="blue", width=8)
        table.add_column("Connections", style="magenta", width=12)
        table.add_column("DOM Elements", style="dim", width=12)
        table.add_column("Status", style="white", width=10)
        
        for tab_index, tab_metrics in metrics.items():
            title = tab_metrics.get('title', 'Unknown')[:30]
            cpu = tab_metrics.get('cpu_percent', 0)
            memory = tab_metrics.get('memory_mb', 0)
            threads = tab_metrics.get('threads', 0)
            connections = tab_metrics.get('connections', 0)
            dom_elements = tab_metrics.get('dom', {}).get('elements', 0)
            
            status = "✅ OK"
            if cpu > RESOURCE_MONITOR_CONFIG['cpu_threshold']:
                status = "⚠️ HIGH CPU"
            if memory > RESOURCE_MONITOR_CONFIG['memory_threshold']:
                status = "⚠️ HIGH MEM"
            if cpu > RESOURCE_MONITOR_CONFIG['cpu_threshold'] and memory > RESOURCE_MONITOR_CONFIG['memory_threshold']:
                status = "🔴 CRITICAL"
            
            table.add_row(
                f"#{tab_index}",
                title,
                f"{cpu:.1f}%",
                f"{memory:.1f}",
                str(threads),
                str(connections),
                f"{dom_elements:,}",
                status
            )
        
        console.print(table)

    def show_resource_dashboard(self):
        """Show comprehensive resource dashboard for all running sessions"""
        if not self.resource_monitor.monitoring:
            console.print("[yellow]Resource monitoring is not active[/yellow]")
            return
        
        sessions = self.db.list_sessions()
        running_sessions = [s for s in sessions if s['status'] == 'running']
        
        if not running_sessions:
            console.print("[yellow]No running sessions[/yellow]")
            return
        
        console.print(Panel("[bold green]📊 Resource Monitor Dashboard[/bold green]", border_style="cyan"))
        
        for session in running_sessions:
            console.print(f"\n[bold cyan]Session: {session['name']}[/bold cyan] (PID: {session['pid']})")
            
            metrics = self.resource_monitor.get_tab_resource_usage(session['id'])
            
            if not metrics:
                console.print("[dim]No tabs or cannot retrieve metrics[/dim]")
                continue
            
            table = Table(box=box.SIMPLE)
            table.add_column("Tab", style="cyan")
            table.add_column("Memory (MB)", style="red", width=12)
            table.add_column("CPU %", style="yellow", width=10)
            table.add_column("DOM", style="dim", width=10)
            table.add_column("Status", style="white")
            
            total_memory = 0
            for tab_index, tab_metrics in metrics.items():
                memory = tab_metrics.get('memory_mb', 0)
                total_memory += memory
                cpu = tab_metrics.get('cpu_percent', 0)
                dom = tab_metrics.get('dom', {}).get('elements', 0)
                
                status = "✅"
                if cpu > RESOURCE_MONITOR_CONFIG['cpu_threshold'] or memory > RESOURCE_MONITOR_CONFIG['memory_threshold']:
                    status = "⚠️"
                
                table.add_row(
                    f"#{tab_index}",
                    f"{memory:.1f}",
                    f"{cpu:.1f}%",
                    f"{dom:,}",
                    status
                )
            
            table.add_row("[bold]Total[/bold]", f"[bold]{total_memory:.1f}[/bold]", "", "", "")
            console.print(table)

    def manage_javascript(self, session_id: int = None):
        """Manage JavaScript scripts - save, load, execute"""
        console.clear()
        console.print(Panel("[bold cyan]📜 JavaScript Script Manager[/bold cyan]", border_style="green"))
        
        while True:
            console.print("\n[bold]Scripts:[/bold]")
            scripts = self.js_manager.list_scripts()
            
            if scripts:
                table = Table(box=box.SIMPLE)
                table.add_column("ID", style="cyan", width=10)
                table.add_column("Name", style="green")
                table.add_column("URL Pattern", style="blue")
                table.add_column("Created", style="dim")
                table.add_column("Actions", style="yellow")
                
                for script in scripts[:20]:
                    actions = []
                    if session_id:
                        actions.append("Execute")
                    actions.append("Edit")
                    actions.append("Delete")
                    
                    table.add_row(
                        script.get('id', '')[:8],
                        script.get('name', 'Unnamed')[:30],
                        script.get('url', 'Any')[:30],
                        script.get('created', '')[:16],
                        " ".join(actions)
                    )
                
                console.print(table)
            else:
                console.print("[dim]No scripts saved[/dim]")
            
            console.print("\n[cyan]📌 Options:[/cyan]")
            console.print("  [1] Create/Save new script")
            console.print("  [2] Load and execute script" + (" on current session" if session_id else ""))
            console.print("  [3] Edit script")
            console.print("  [4] Delete script")
            console.print("  [5] Export script")
            console.print("  [6] Import script")
            console.print("  [0] Back")
            
            choice = Prompt.ask("Select", choices=["0", "1", "2", "3", "4", "5", "6"])
            
            if choice == "0":
                break
            
            elif choice == "1":  # Create new script
                script_data = self._create_script_from_input(session_id)
                if script_data:
                    script_id = self.js_manager.save_script(script_data)
                    console.print(f"[green]✅ Script saved with ID: {script_id[:8]}[/green]")
            
            elif choice == "2":  # Execute script
                if not session_id:
                    console.print("[red]No session selected. Please manage tabs first.[/red]")
                    continue
                
                script_id = Prompt.ask("Enter script ID to execute")
                script = self.js_manager.get_script(script_id)
                if script:
                    self._execute_script_on_session(session_id, script)
                else:
                    console.print("[red]Script not found[/red]")
            
            elif choice == "3":  # Edit script
                script_id = Prompt.ask("Enter script ID to edit")
                script = self.js_manager.get_script(script_id)
                if script:
                    self._edit_script(script)
                else:
                    console.print("[red]Script not found[/red]")
            
            elif choice == "4":  # Delete script
                script_id = Prompt.ask("Enter script ID to delete")
                if Confirm.ask(f"Delete script {script_id}?"):
                    if self.js_manager.delete_script(script_id):
                        console.print("[green]✅ Script deleted[/green]")
                    else:
                        console.print("[red]Failed to delete script[/red]")
            
            elif choice == "5":  # Export script
                script_id = Prompt.ask("Enter script ID to export")
                script = self.js_manager.get_script(script_id)
                if script:
                    filename = f"{script.get('name', 'script')}_{script_id}.json"
                    path = os.path.join(os.getcwd(), filename)
                    with open(path, 'w') as f:
                        json.dump(script, f, indent=2)
                    console.print(f"[green]✅ Exported to {filename}[/green]")
                else:
                    console.print("[red]Script not found[/red]")
            
            elif choice == "6":  # Import script
                filename = Prompt.ask("Enter script filename (JSON)")
                try:
                    with open(filename, 'r') as f:
                        script_data = json.load(f)
                    script_id = self.js_manager.save_script(script_data)
                    console.print(f"[green]✅ Imported script with ID: {script_id[:8]}[/green]")
                except Exception as e:
                    console.print(f"[red]Error importing: {e}[/red]")
            
            if choice != "0":
                console.print()
                Prompt.ask("Press Enter to continue...")

    def _create_script_from_input(self, session_id: int = None) -> Optional[Dict]:
        """Create a new script from user input"""
        console.print("\n[bold]Create New Script[/bold]")
        
        name = Prompt.ask("Script name (e.g., 'Clear Reddit Feed')")
        if not name:
            console.print("[red]Name required[/red]")
            return None
        
        url_pattern = Prompt.ask("URL pattern (optional - leave empty for any)")
        description = Prompt.ask("Description (optional)")
        
        console.print("\n[cyan]Enter JavaScript code (type 'END' on a new line when done):[/cyan]")
        lines = []
        while True:
            line = input()
            if line.strip() == "END":
                break
            lines.append(line)
        
        code = "\n".join(lines)
        if not code:
            console.print("[red]Code required[/red]")
            return None
        
        # Test the script if session is available
        if session_id:
            if Confirm.ask("Test this script on current session?"):
                session = self.db.get_session(session_id)
                if session and session['status'] == 'running':
                    devtools = self._get_devtools(session['port'])
                    if devtools._ensure_connection():
                        tabs = devtools.get_tabs()
                        if tabs:
                            tab_num = int(Prompt.ask("Tab number to test", default="1"))
                            if 0 < tab_num <= len(tabs):
                                console.print("[yellow]Testing script...[/yellow]")
                                result = devtools.execute_script(tabs[tab_num-1]['id'], code)
                                if result:
                                    console.print("[green]✅ Script executed successfully[/green]")
                                    console.print(f"[dim]Result: {json.dumps(result, indent=2, default=str)[:500]}[/dim]")
                                else:
                                    console.print("[red]❌ Script execution failed[/red]")
                                    if not Confirm.ask("Save script anyway?"):
                                        return None
        
        return {
            'name': name,
            'url': url_pattern,
            'description': description,
            'code': code,
            'type': 'user_script'
        }

    def _edit_script(self, script: Dict):
        """Edit an existing script"""
        console.print(f"\n[bold]Editing Script: {script.get('name', '')}[/bold]")
        
        name = Prompt.ask("Name", default=script.get('name', ''))
        url_pattern = Prompt.ask("URL pattern", default=script.get('url', ''))
        description = Prompt.ask("Description", default=script.get('description', ''))
        
        console.print("\n[cyan]Current code:[/cyan]")
        console.print(Panel(script.get('code', ''), border_style="dim"))
        
        if Confirm.ask("Edit code?"):
            console.print("[cyan]Enter new JavaScript code (type 'END' on a new line when done):[/cyan]")
            lines = []
            while True:
                line = input()
                if line.strip() == "END":
                    break
                lines.append(line)
            code = "\n".join(lines)
        else:
            code = script.get('code', '')
        
        script_data = {
            'name': name,
            'url': url_pattern,
            'description': description,
            'code': code,
            'type': script.get('type', 'user_script')
        }
        
        if self.js_manager.update_script(script.get('id'), script_data):
            console.print("[green]✅ Script updated[/green]")
        else:
            console.print("[red]❌ Failed to update script[/red]")

    def _execute_script_on_session(self, session_id: int, script: Dict):
        """Execute a script on a session"""
        session = self.db.get_session(session_id)
        if not session:
            console.print("[red]Session not found[/red]")
            return
        
        if session['status'] != 'running':
            console.print("[red]Session not running[/red]")
            return
        
        devtools = self._get_devtools(session['port'])
        if not devtools._ensure_connection():
            console.print("[red]Cannot connect to Chrome[/red]")
            return
        
        tabs = devtools.get_tabs()
        if not tabs:
            console.print("[yellow]No tabs open[/yellow]")
            return
        
        console.print("\n[bold]Select tab to execute on:[/bold]")
        for i, tab in enumerate(tabs, 1):
            console.print(f"  [{i}] {tab.get('title', 'Untitled')[:50]}")
        
        try:
            tab_num = int(Prompt.ask("Tab number", default="1"))
            if 0 < tab_num <= len(tabs):
                tab_id = tabs[tab_num-1]['id']
                
                console.print(f"[yellow]Executing script on tab {tab_num}...[/yellow]")
                result = devtools.execute_script(tab_id, script.get('code', ''))
                
                if result:
                    console.print("[green]✅ Script executed successfully[/green]")
                    result_str = json.dumps(result, indent=2, default=str)
                    if len(result_str) > 5000:
                        result_str = result_str[:5000] + "\n\n... (truncated)"
                    console.print(Panel(result_str, title="Result", border_style="green"))
                    
                    # Save to history
                    self.script_history.append({
                        'timestamp': datetime.now().isoformat(),
                        'session': session_id,
                        'tab': tab_num,
                        'script': script.get('name', 'Unknown'),
                        'result': result_str[:500]
                    })
                else:
                    console.print("[red]❌ Script execution failed[/red]")
        except:
            console.print("[red]Invalid input[/red]")

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
                    console.print(f"[dim]Deleted profile directory[/dim]")
                except:
                    console.print("[yellow]Could not fully delete profile directory (some files may be locked)[/yellow]")

            self.db.delete_session(session_id)
            console.print(f"[green]✅ Session deleted[/green]")

    def show_dashboard(self):
        self._cleanup_zombie_sessions()
        self._ensure_vnc_running()

        sessions = self.db.list_sessions()
        running = [s for s in sessions if s['status'] == 'running']
        stopped = [s for s in sessions if s['status'] == 'stopped']

        total_size = sum(self._get_dir_size_bytes(s['profile_dir']) for s in sessions)

        content = f"""
[bold green]📊 Chrome Session Dashboard[/bold green]

[bold]Overview:[/bold]
  Total Sessions: {len(sessions)}
  🟢 Running: {len(running)}
  ⚪ Stopped: {len(stopped)}
  🔌 Available Ports: {len(self.db.get_available_ports())}
  💾 Total Profile Size: {self._format_size(total_size)}
  📝 Script History: {len(self.script_history)} executions
  📜 Saved Scripts: {len(self.js_manager.list_scripts())}
  🔍 Monitoring: {"✅ Active" if self.resource_monitor.monitoring else "❌ Inactive"}
  🔒 Root Access: {"✅ Yes" if self.is_root else "❌ No"}
  🖥️ VNC Display: {self.display if self.display else "❌ None"}

[bold]Storage:[/bold]
  📁 Base Directory: {BASE_PROFILE_DIR}
  📁 Scripts Directory: {JS_SCRIPTS_DIR}
  🔧 Chrome: {self.chrome_path}

[bold]Resource Monitor Settings:[/bold]
  CPU Threshold: {RESOURCE_MONITOR_CONFIG['cpu_threshold']}%
  Memory Threshold: {RESOURCE_MONITOR_CONFIG['memory_threshold']} MB
  Check Interval: {RESOURCE_MONITOR_CONFIG['check_interval']}s
  Auto-Kill: {'✅' if RESOURCE_MONITOR_CONFIG['auto_kill'] else '❌'}
  Max Violations: {RESOURCE_MONITOR_CONFIG['max_consecutive_violations']}

[bold]Sessions:[/bold]
"""

        for session in sessions:
            status_icon = "🟢" if session['status'] == 'running' else "⚪"
            monitor_icon = "🔍" if (session['status'] == 'running' and self.resource_monitor.monitoring) else ""
            profile_size = self._get_dir_size(session['profile_dir'])
            content += f"  {status_icon} {session['name']:20} Port: {session['port']:4} Size: {profile_size:>10} {monitor_icon}\n"

        console.print(Panel(content, title="Dashboard", border_style="cyan"))

        if running:
            table = Table(title="🟢 Running Sessions", box=box.SIMPLE)
            table.add_column("Name", style="green")
            table.add_column("Port", style="yellow")
            table.add_column("PID", style="red")
            table.add_column("Debug URL", style="blue")
            table.add_column("Monitoring", style="cyan")
            table.add_column("Profile", style="dim")

            for session in running:
                try:
                    os.kill(session['pid'], 0)
                    status = "✅"
                except:
                    status = "❌"
                    self.db.stop_session(session['id'])
                    self.db.release_port(session['port'])

                monitoring = "🔍 Active" if self.resource_monitor.monitoring else "-"

                table.add_row(
                    session['name'],
                    str(session['port']),
                    f"{session['pid']} {status}",
                    f"http://127.0.0.1:{session['port']}",
                    monitoring,
                    os.path.basename(session['profile_dir'])
                )

            console.print(table)

    def interactive_menu(self):
        """Main interactive menu"""
        # Clean up VNC on startup
        self.vnc_manager.cleanup()
        self._ensure_vnc_running()
        
        while True:
            console.clear()
            console.print()

            header = """
╔══════════════════════════════════════════════════════════════╗
║           🌐 Chrome Session Manager - Root Enhanced       ║
║           Persistent Chrome Sessions with Automation     ║
╚══════════════════════════════════════════════════════════════╝
            """
            console.print(Panel(header, border_style="cyan"))

            self._cleanup_zombie_sessions()

            sessions = self.db.list_sessions()
            running = len([s for s in sessions if s['status'] == 'running'])
            total = len(sessions)
            available = len(self.db.get_available_ports())

            display_status = f"🖥️ Display: {self.display if self.display else '❌ Headless'}"
            root_status = f"🔒 Root: {'✅' if self.is_root else '❌'}"
            monitor_status = f"🔍 Monitoring: {'✅ Active' if self.resource_monitor.monitoring else '❌ Inactive'}"
            script_count = f"📜 Scripts: {len(self.js_manager.list_scripts())}"
            status_line = f"📊 {total} sessions | 🟢 {running} running | 🔌 {available} ports | {display_status} | {root_status} | {monitor_status} | {script_count}"
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
            menu.add_row("8", "[bold]Manage Tabs[/bold]", "Advanced tab control with monitoring")
            menu.add_row("9", "[bold]Resource Monitor[/bold]", "Monitor high-resource tabs")
            menu.add_row("10", "[bold]Resource Dashboard[/bold]", "Show resource usage dashboard")
            menu.add_row("11", "[bold]JavaScript Manager[/bold]", "Save, load, and execute scripts")
            menu.add_row("12", "[bold]VNC Manager[/bold]", "Manage VNC display")
            menu.add_row("13", "[bold]Cleanup[/bold]", "Clean up zombie sessions")
            menu.add_row("0", "[red]Exit[/red]", "Exit the manager")

            console.print(menu)
            console.print()

            choice = Prompt.ask("Select option", choices=["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"])

            if choice == "0":
                if self.resource_monitor.monitoring:
                    self.resource_monitor.stop_monitoring()
                console.print("[green]Goodbye! 👋[/green]")
                break

            elif choice == "1":
                self.create_session()

            elif choice == "2":
                self.list_sessions()
                try:
                    session_id = int(Prompt.ask("Enter session ID to start"))
                    self.start_session(session_id)
                    if Confirm.ask("Start resource monitoring?"):
                        self.resource_monitor.start_monitoring(session_id)
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

            elif choice == "9":
                self.list_sessions()
                try:
                    session_id = int(Prompt.ask("Enter session ID to monitor"))
                    self.resource_monitor.start_monitoring(session_id)
                except ValueError:
                    console.print("[red]Invalid ID[/red]")

            elif choice == "10":
                self.show_resource_dashboard()

            elif choice == "11":
                self.list_sessions()
                try:
                    session_id = int(Prompt.ask("Enter session ID (or 0 for script management only)"))
                    if session_id == 0:
                        self.manage_javascript()
                    else:
                        self.manage_javascript(session_id)
                except ValueError:
                    console.print("[red]Invalid ID[/red]")

            elif choice == "12":  # VNC Manager
                self._manage_vnc()

            elif choice == "13":
                cleaned = self._cleanup_zombie_sessions()
                self.vnc_manager.cleanup()
                console.print(f"[green]✅ Cleaned up {cleaned} zombie session(s)[/green]")

            if choice != "0":
                console.print()
                Prompt.ask("Press Enter to continue...")

    def _manage_vnc(self):
        """Manage VNC server"""
        console.clear()
        console.print(Panel("[bold cyan]🖥️ VNC Manager[/bold cyan]", border_style="magenta"))
        
        console.print(f"\nCurrent display: [bold]{self.display if self.display else 'None'}[/bold]")
        console.print(f"Root access: {'✅' if self.is_root else '❌'}")
        
        console.print("\n[cyan]VNC Actions:[/cyan]")
        console.print("  [1] Start VNC (auto-detect display)")
        console.print("  [2] Stop VNC")
        console.print("  [3] Clean up lock files")
        console.print("  [4] List running VNC sessions")
        console.print("  [5] Restart VNC")
        console.print("  [0] Back")
        
        choice = Prompt.ask("Select", choices=["0", "1", "2", "3", "4", "5"])
        
        if choice == "0":
            return
        elif choice == "1":
            display = self.vnc_manager.ensure_vnc()
            if display:
                self.display = display
                os.environ['DISPLAY'] = display
                console.print(f"[green]✅ VNC started on {display}[/green]")
            else:
                console.print("[red]❌ Failed to start VNC[/red]")
        elif choice == "2":
            if self.display:
                try:
                    subprocess.run(['vncserver', '-kill', self.display], timeout=5)
                    console.print(f"[green]✅ VNC {self.display} stopped[/green]")
                    self.display = None
                except:
                    console.print("[red]❌ Failed to stop VNC[/red]")
            else:
                console.print("[yellow]No VNC display active[/yellow]")
        elif choice == "3":
            self.vnc_manager.cleanup()
            console.print("[green]✅ Cleanup complete[/green]")
        elif choice == "4":
            result = subprocess.run(['vncserver', '-list'], capture_output=True, text=True)
            console.print(Panel(result.stdout, title="VNC Sessions", border_style="dim"))
        elif choice == "5":
            if self.display:
                try:
                    subprocess.run(['vncserver', '-kill', self.display], timeout=5)
                except:
                    pass
            time.sleep(1)
            display = self.vnc_manager.ensure_vnc()
            if display:
                self.display = display
                os.environ['DISPLAY'] = display
                console.print(f"[green]✅ VNC restarted on {display}[/green]")
            else:
                console.print("[red]❌ Failed to restart VNC[/red]")

    def manage_tabs_enhanced(self, session_id: int):
        """Enhanced interactive tab management with resource monitoring"""
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
            console.print("[yellow]Try restarting the session[/yellow]")
            return

        if not self.resource_monitor.monitoring:
            if Confirm.ask("Enable resource monitoring for this session?"):
                self.resource_monitor.start_monitoring(session_id)
                time.sleep(1)

        while True:
            console.clear()
            console.print(Panel(f"📑 Enhanced Tab Manager - {session['name']} (Port: {session['port']})", style="cyan"))
            console.print()

            if self.resource_monitor.monitoring:
                metrics = self.resource_monitor.get_tab_resource_usage(session_id)
                if metrics:
                    console.print("[bold cyan]Resource Usage:[/bold cyan]")
                    for tab_index, tab_metrics in metrics.items():
                        title = tab_metrics.get('title', 'Unknown')[:30]
                        cpu = tab_metrics.get('cpu_percent', 0)
                        memory = tab_metrics.get('memory_mb', 0)
                        status = "✅"
                        if cpu > RESOURCE_MONITOR_CONFIG['cpu_threshold']:
                            status = "⚠️"
                        if memory > RESOURCE_MONITOR_CONFIG['memory_threshold']:
                            status = "🔴"
                        console.print(f"  #{tab_index} {title}  CPU: {cpu:.1f}%  Memory: {memory:.1f}MB  {status}")
                console.print()

            tabs = devtools.get_tabs()

            if not tabs:
                console.print("[yellow]No tabs open[/yellow]")
            else:
                table = Table(title=f"Open Tabs ({len(tabs)})", box=box.ROUNDED)
                table.add_column("#", style="cyan", width=4)
                table.add_column("Title", style="green", no_wrap=False)
                table.add_column("URL", style="blue", no_wrap=False)
                table.add_column("Status", style="white", width=12)

                for i, tab in enumerate(tabs, 1):
                    title = tab.get('title', 'Untitled')[:60]
                    url = tab.get('url', '')[:70]
                    
                    if self.resource_monitor.monitoring:
                        metrics = self.resource_monitor.get_tab_resource_usage(session_id)
                        if i in metrics:
                            cpu = metrics[i].get('cpu_percent', 0)
                            memory = metrics[i].get('memory_mb', 0)
                            if cpu > RESOURCE_MONITOR_CONFIG['cpu_threshold'] or memory > RESOURCE_MONITOR_CONFIG['memory_threshold']:
                                status = "⚠️ HIGH"
                            else:
                                status = "✅ OK"
                        else:
                            status = "❓ Unknown"
                    else:
                        status = ""

                    table.add_row(str(i), title, url, status)

                console.print(table)

            console.print()
            console.print("[cyan]📌 Tab Actions:[/cyan]")
            console.print("  [1] New tab        [2] Close tab      [3] Navigate")
            console.print("  [4] View HTML      [5] View Text      [6] View Metadata")
            console.print("  [7] Execute JS     [8] Click Element  [9] Fill Input")
            console.print("  [10] Get Links     [11] Get Images    [12] Get Cookies")
            console.print("  [13] Get Storage   [14] Save Content  [15] Kill High-Resource")
            console.print("  [16] JS Scripts    [17] Load JS Script")
            console.print("  [0] Back")

            choice = Prompt.ask("Select", choices=["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17"])

            if choice == "0":
                break

            elif choice == "1":
                url = Prompt.ask("URL", default=session['url'])
                if not url.startswith(("http://", "https://")):
                    url = f"https://{url}"
                if devtools.create_tab(url):
                    console.print("[green]✅ Tab created[/green]")

            elif choice == "2":
                if tabs:
                    try:
                        num = int(Prompt.ask("Tab number", choices=[str(i+1) for i in range(len(tabs))]))
                        if 0 < num <= len(tabs):
                            if devtools.close_tab(tabs[num-1]['id']):
                                console.print("[green]✅ Tab closed[/green]")
                    except:
                        pass
                else:
                    console.print("[yellow]No tabs to close[/yellow]")

            elif choice == "3":
                if tabs:
                    try:
                        num = int(Prompt.ask("Tab number", choices=[str(i+1) for i in range(len(tabs))]))
                        if 0 < num <= len(tabs):
                            url = Prompt.ask("URL")
                            if not url.startswith(("http://", "https://")):
                                url = f"https://{url}"
                            if devtools.navigate_to(tabs[num-1]['id'], url):
                                console.print("[green]✅ Navigated[/green]")
                    except:
                        pass
                else:
                    console.print("[yellow]No tabs to navigate[/yellow]")

            elif choice == "4":  # View HTML
                if tabs:
                    try:
                        num = int(Prompt.ask("Tab number", choices=[str(i+1) for i in range(len(tabs))]))
                        if 0 < num <= len(tabs):
                            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                                progress.add_task("Fetching HTML...", total=None)
                                content = devtools.get_page_content(tabs[num-1]['id'])

                            if content:
                                if len(content) > 5000:
                                    content = content[:5000] + "\n\n... (truncated)"
                                console.print(Panel(
                                    content,
                                    title=f"HTML Content - Tab {num}",
                                    border_style="green"
                                ))
                                if Confirm.ask("Save full HTML to file?"):
                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    filename = f"{session['name']}_tab{num}_{timestamp}.html"
                                    devtools.save_page_content(tabs[num-1]['id'], filename)
                                    console.print(f"[green]✅ Saved: {filename}[/green]")
                    except:
                        pass
                else:
                    console.print("[yellow]No tabs to view[/yellow]")

            elif choice == "5":  # View Text
                if tabs:
                    try:
                        num = int(Prompt.ask("Tab number", choices=[str(i+1) for i in range(len(tabs))]))
                        if 0 < num <= len(tabs):
                            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                                progress.add_task("Fetching text...", total=None)
                                text = devtools.get_page_text(tabs[num-1]['id'])

                            if text:
                                if len(text) > 5000:
                                    text = text[:5000] + "\n\n... (truncated)"
                                console.print(Panel(
                                    text,
                                    title=f"Page Text - Tab {num}",
                                    border_style="blue"
                                ))
                    except:
                        pass
                else:
                    console.print("[yellow]No tabs to view[/yellow]")

            elif choice == "6":  # View Metadata
                if tabs:
                    try:
                        num = int(Prompt.ask("Tab number", choices=[str(i+1) for i in range(len(tabs))]))
                        if 0 < num <= len(tabs):
                            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                                progress.add_task("Fetching metadata...", total=None)
                                metadata = devtools.get_page_metadata(tabs[num-1]['id'])

                            if metadata:
                                content = "\n".join([f"[bold]{k}:[/bold] {v}" for k, v in metadata.items()])
                                console.print(Panel(
                                    content,
                                    title=f"Page Metadata - Tab {num}",
                                    border_style="cyan"
                                ))
                    except:
                        pass
                else:
                    console.print("[yellow]No tabs to view[/yellow]")

            elif choice == "7":  # Execute JS
                if tabs:
                    try:
                        num = int(Prompt.ask("Tab number", choices=[str(i+1) for i in range(len(tabs))]))
                        if 0 < num <= len(tabs):
                            console.print("[cyan]Enter JavaScript code (type 'END' on a new line when done):[/cyan]")
                            lines = []
                            while True:
                                line = input()
                                if line.strip() == "END":
                                    break
                                lines.append(line)
                            script = "\n".join(lines)
                            
                            if script:
                                with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                                    progress.add_task("Executing...", total=None)
                                    result = devtools.execute_script(tabs[num-1]['id'], script)

                                if result:
                                    result_str = json.dumps(result, indent=2, default=str)
                                    console.print(Panel(
                                        result_str[:5000] + ("..." if len(result_str) > 5000 else ""),
                                        title="Result",
                                        border_style="green"
                                    ))
                                    self.script_history.append({
                                        'timestamp': datetime.now().isoformat(),
                                        'tab': num,
                                        'script': script[:100],
                                        'result': result_str[:500]
                                    })
                                    
                                    # Ask to save script
                                    if Confirm.ask("Save this script?"):
                                        name = Prompt.ask("Script name")
                                        script_data = {
                                            'name': name,
                                            'url': tabs[num-1].get('url', ''),
                                            'code': script,
                                            'type': 'saved_script'
                                        }
                                        script_id = self.js_manager.save_script(script_data)
                                        console.print(f"[green]✅ Script saved with ID: {script_id[:8]}[/green]")
                    except:
                        pass
                else:
                    console.print("[yellow]No tabs to execute on[/yellow]")

            elif choice == "8":  # Click Element
                if tabs:
                    try:
                        num = int(Prompt.ask("Tab number", choices=[str(i+1) for i in range(len(tabs))]))
                        if 0 < num <= len(tabs):
                            selector = Prompt.ask("CSS selector")
                            if selector:
                                if devtools.click_element(tabs[num-1]['id'], selector):
                                    console.print("[green]✅ Element clicked[/green]")
                                else:
                                    console.print("[red]❌ Element not found[/red]")
                    except:
                        pass
                else:
                    console.print("[yellow]No tabs to interact with[/yellow]")

            elif choice == "9":  # Fill Input
                if tabs:
                    try:
                        num = int(Prompt.ask("Tab number", choices=[str(i+1) for i in range(len(tabs))]))
                        if 0 < num <= len(tabs):
                            selector = Prompt.ask("CSS selector")
                            value = Prompt.ask("Value to fill")
                            if selector and value:
                                if devtools.fill_input(tabs[num-1]['id'], selector, value):
                                    console.print("[green]✅ Input filled[/green]")
                                else:
                                    console.print("[red]❌ Element not found[/red]")
                    except:
                        pass
                else:
                    console.print("[yellow]No tabs to interact with[/yellow]")

            elif choice == "10":  # Get Links
                if tabs:
                    try:
                        num = int(Prompt.ask("Tab number", choices=[str(i+1) for i in range(len(tabs))]))
                        if 0 < num <= len(tabs):
                            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                                progress.add_task("Fetching links...", total=None)
                                links = devtools.get_all_links(tabs[num-1]['id'])

                            if links:
                                content = "\n".join(links[:50])
                                if len(links) > 50:
                                    content += f"\n\n... and {len(links)-50} more"
                                console.print(Panel(
                                    content,
                                    title=f"Links ({len(links)})",
                                    border_style="yellow"
                                ))
                            else:
                                console.print("[yellow]No links found[/yellow]")
                    except:
                        pass
                else:
                    console.print("[yellow]No tabs to analyze[/yellow]")

            elif choice == "11":  # Get Images
                if tabs:
                    try:
                        num = int(Prompt.ask("Tab number", choices=[str(i+1) for i in range(len(tabs))]))
                        if 0 < num <= len(tabs):
                            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                                progress.add_task("Fetching images...", total=None)
                                images = devtools.get_all_images(tabs[num-1]['id'])

                            if images:
                                content = "\n".join(images[:50])
                                if len(images) > 50:
                                    content += f"\n\n... and {len(images)-50} more"
                                console.print(Panel(
                                    content,
                                    title=f"Images ({len(images)})",
                                    border_style="magenta"
                                ))
                            else:
                                console.print("[yellow]No images found[/yellow]")
                    except:
                        pass
                else:
                    console.print("[yellow]No tabs to analyze[/yellow]")

            elif choice == "12":  # Get Cookies
                if tabs:
                    try:
                        num = int(Prompt.ask("Tab number", choices=[str(i+1) for i in range(len(tabs))]))
                        if 0 < num <= len(tabs):
                            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                                progress.add_task("Fetching cookies...", total=None)
                                cookies = devtools.get_cookies(tabs[num-1]['id'])

                            if cookies:
                                content = "\n".join([f"{c['name']}: {c['value']}" for c in cookies])
                                console.print(Panel(
                                    content,
                                    title=f"Cookies ({len(cookies)})",
                                    border_style="cyan"
                                ))
                            else:
                                console.print("[yellow]No cookies found[/yellow]")
                    except:
                        pass
                else:
                    console.print("[yellow]No tabs to analyze[/yellow]")

            elif choice == "13":  # Get Storage
                if tabs:
                    try:
                        num = int(Prompt.ask("Tab number", choices=[str(i+1) for i in range(len(tabs))]))
                        if 0 < num <= len(tabs):
                            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                                progress.add_task("Fetching storage...", total=None)
                                local = devtools.get_local_storage(tabs[num-1]['id'])
                                session_storage = devtools.get_session_storage(tabs[num-1]['id'])

                            content = ""
                            if local:
                                content += "[bold]Local Storage:[/bold]\n"
                                content += "\n".join([f"  {k}: {v}" for k, v in local.items()])
                            if session_storage:
                                if content:
                                    content += "\n\n"
                                content += "[bold]Session Storage:[/bold]\n"
                                content += "\n".join([f"  {k}: {v}" for k, v in session_storage.items()])
                            if content:
                                console.print(Panel(
                                    content,
                                    title="Storage",
                                    border_style="green"
                                ))
                            else:
                                console.print("[yellow]No storage data found[/yellow]")
                    except:
                        pass
                else:
                    console.print("[yellow]No tabs to analyze[/yellow]")

            elif choice == "14":  # Save Content
                if tabs:
                    try:
                        num = int(Prompt.ask("Tab number", choices=[str(i+1) for i in range(len(tabs))]))
                        if 0 < num <= len(tabs):
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            filename = f"{session['name']}_tab{num}_{timestamp}.html"
                            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                                progress.add_task("Saving...", total=None)
                                if devtools.save_page_content(tabs[num-1]['id'], filename):
                                    console.print(f"[green]✅ Saved: {filename}[/green]")
                                else:
                                    console.print("[red]❌ Failed to save[/red]")
                    except:
                        pass
                else:
                    console.print("[yellow]No tabs to save[/yellow]")

            elif choice == "15":  # Kill High-Resource Tab
                if tabs and self.resource_monitor.monitoring:
                    metrics = self.resource_monitor.get_tab_resource_usage(session_id)
                    if metrics:
                        console.print("[bold red]High-Resource Tabs:[/bold red]")
                        for tab_index, tab_metrics in metrics.items():
                            cpu = tab_metrics.get('cpu_percent', 0)
                            memory = tab_metrics.get('memory_mb', 0)
                            if cpu > RESOURCE_MONITOR_CONFIG['cpu_threshold'] or memory > RESOURCE_MONITOR_CONFIG['memory_threshold']:
                                console.print(f"  #{tab_index}: {tab_metrics.get('title', 'Unknown')[:30]} - CPU: {cpu:.1f}% Memory: {memory:.1f}MB")
                        
                        try:
                            num = int(Prompt.ask("Tab number to kill"))
                            if 0 < num <= len(tabs):
                                tab_id = tabs[num-1]['id']
                                proc_info = self.resource_monitor.get_tab_process_info(tab_id, session['port'])
                                if proc_info:
                                    console.print(f"[yellow]Process PID: {proc_info['pid']}[/yellow]")
                                    if Confirm.ask(f"Kill tab {num} and its process?"):
                                        if devtools.close_tab(tab_id):
                                            console.print("[green]✅ Tab killed[/green]")
                                            if proc_info and proc_info['pid']:
                                                try:
                                                    os.kill(proc_info['pid'], signal.SIGKILL)
                                                    console.print(f"[green]✅ Process {proc_info['pid']} killed[/green]")
                                                except:
                                                    pass
                                        else:
                                            if proc_info and proc_info['pid']:
                                                try:
                                                    os.kill(proc_info['pid'], signal.SIGKILL)
                                                    console.print(f"[green]✅ Process {proc_info['pid']} killed[/green]")
                                                    console.print("[yellow]Tab may still be visible but should be dead[/yellow]")
                                                except:
                                                    console.print("[red]❌ Failed to kill process[/red]")
                        except:
                            pass
                else:
                    console.print("[yellow]Resource monitoring not active[/yellow]")

            elif choice == "16":  # JS Scripts
                self.manage_javascript(session_id)

            elif choice == "17":  # Load JS Script
                if tabs:
                    scripts = self.js_manager.list_scripts()
                    if not scripts:
                        console.print("[yellow]No scripts available[/yellow]")
                        continue
                    
                    console.print("\n[bold]Available Scripts:[/bold]")
                    for i, script in enumerate(scripts, 1):
                        console.print(f"  [{i}] {script.get('name', 'Unnamed')} - {script.get('description', '')[:30]}")
                    
                    try:
                        script_idx = int(Prompt.ask("Select script number"))
                        if 0 < script_idx <= len(scripts):
                            script = scripts[script_idx - 1]
                            
                            tab_num = int(Prompt.ask("Tab number to execute on", default="1"))
                            if 0 < tab_num <= len(tabs):
                                with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                                    progress.add_task("Executing script...", total=None)
                                    result = devtools.execute_script(tabs[tab_num-1]['id'], script.get('code', ''))
                                
                                if result:
                                    result_str = json.dumps(result, indent=2, default=str)
                                    console.print(Panel(
                                        result_str[:5000] + ("..." if len(result_str) > 5000 else ""),
                                        title=f"Script Result: {script.get('name')}",
                                        border_style="green"
                                    ))
                                else:
                                    console.print("[red]❌ Script execution failed[/red]")
                    except:
                        pass
                else:
                    console.print("[yellow]No tabs open[/yellow]")

            if choice != "0":
                console.print()
                Prompt.ask("Press Enter to continue...")

def main():
    try:
        manager = ChromeSessionManager()
        manager.interactive_menu()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
