#!/usr/bin/env python3
"""
Enhanced Chrome Session Manager - Final WebSocket Fix
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
import socket
import threading
import hashlib
import urllib.parse

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
import websocket

console = Console()

# Configuration
BASE_PROFILE_DIR = os.path.expanduser("~/chrome-sessions")
DEBUG_PORT_START = 9222
DEBUG_PORT_END = 9299
JS_SCRIPTS_DIR = os.path.expanduser("~/chrome-scripts")
os.makedirs(JS_SCRIPTS_DIR, exist_ok=True)

class ChromeDevTools:
    """Chrome DevTools Protocol with fixed WebSocket handling"""
    
    def __init__(self, host='127.0.0.1', port=9222):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.session = requests.Session()
        self.session.timeout = 3
        self._ws_connection = None

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

    def get_tab_by_id(self, tab_id: str) -> Optional[Dict]:
        tabs = self.get_tabs()
        for tab in tabs:
            if tab.get('id') == tab_id:
                return tab
        return None

    def _fix_websocket_url(self, ws_url: str) -> str:
        """Fix malformed WebSocket URLs"""
        # Remove any trailing commas or invalid characters
        ws_url = ws_url.strip()
        ws_url = re.sub(r',[^,]*$', '', ws_url)
        
        # Ensure proper format
        if not ws_url.startswith('ws://'):
            ws_url = ws_url.replace('http://', 'ws://').replace('https://', 'wss://')
        
        # Ensure proper port
        if 'localhost' in ws_url and ':922' not in ws_url:
            ws_url = ws_url.replace('localhost', f'localhost:{self.port}')
        
        # Fix any double slashes
        ws_url = re.sub(r'/(?=/)', '', ws_url)
        
        return ws_url

    def execute_script(self, tab_id: str, script: str, return_by_value: bool = True) -> Optional[Dict]:
        """Execute JavaScript with proper WebSocket connection"""
        try:
            # Get tab info
            tab = self.get_tab_by_id(tab_id)
            if not tab:
                console.print("[red]Tab not found[/red]")
                return None

            ws_url = tab.get('webSocketDebuggerUrl')
            if not ws_url:
                console.print("[red]No WebSocket URL found[/red]")
                return None

            # Fix the WebSocket URL
            ws_url = self._fix_websocket_url(ws_url)
            
            # Try different connection methods
            ws = None
            methods_tried = []
            
            # Method 1: Direct connection
            try:
                ws = websocket.create_connection(ws_url, timeout=10)
                methods_tried.append("Direct")
            except Exception as e:
                pass
            
            # Method 2: With Origin header
            if not ws:
                try:
                    origin = f"http://{self.host}:{self.port}"
                    ws = websocket.create_connection(
                        ws_url,
                        timeout=10,
                        header={"Origin": origin}
                    )
                    methods_tried.append("With Origin")
                except Exception as e:
                    pass
            
            # Method 3: Try without any headers
            if not ws:
                try:
                    ws = websocket.create_connection(
                        ws_url,
                        timeout=10,
                        header={}
                    )
                    methods_tried.append("No Headers")
                except Exception as e:
                    pass
            
            # Method 4: Try with localhost instead of 127.0.0.1
            if not ws:
                try:
                    ws_url_local = ws_url.replace('127.0.0.1', 'localhost')
                    ws = websocket.create_connection(ws_url_local, timeout=10)
                    methods_tried.append("localhost")
                except Exception as e:
                    pass
            
            # Method 5: Try with explicit port
            if not ws:
                try:
                    # Force the port to be the debug port
                    ws_url_fixed = re.sub(r':\d+', f':{self.port}', ws_url)
                    ws = websocket.create_connection(ws_url_fixed, timeout=10)
                    methods_tried.append("Fixed Port")
                except Exception as e:
                    pass
            
            if not ws:
                console.print(f"[red]Failed to connect to WebSocket after trying: {', '.join(methods_tried)}[/red]")
                return None

            try:
                # Enable Runtime domain
                enable_cmd = {
                    "id": 1,
                    "method": "Runtime.enable"
                }
                ws.send(json.dumps(enable_cmd))
                response = ws.recv()
                
                # Check if enable succeeded
                resp_json = json.loads(response)
                if 'error' in resp_json:
                    console.print(f"[red]Runtime.enable failed: {resp_json['error']}[/red]")
                    ws.close()
                    return None

                # Execute the script
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
                
                if 'error' in result:
                    console.print(f"[red]Script error: {result['error']}[/red]")
                    return None
                    
                return result.get('result')
            except Exception as e:
                console.print(f"[red]Error during execution: {e}[/red]")
                return None
            finally:
                try:
                    ws.close()
                except:
                    pass
                
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
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
        script = "document.body.innerText"
        result = self.execute_script(tab_id, script)
        return result.get('value') if result else None

    def get_page_metadata(self, tab_id: str) -> Dict:
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
        try:
            content = self.get_page_content(tab_id)
            if content:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)
                return True
            return False
        except:
            return False

    def get_all_links(self, tab_id: str) -> List[str]:
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
        script = """
        (function() {
            return Array.from(document.querySelectorAll('img'))
                .map(img => img.src)
                .filter(src => src && src.startsWith('http'));
        })()
        """
        result = self.execute_script(tab_id, script)
        return result.get('value') if result else []

    def get_cookies(self, tab_id: str) -> Optional[List[Dict]]:
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

class JavaScriptManager:
    def __init__(self):
        self.scripts = {}
        self.load_scripts()
    
    def load_scripts(self):
        if os.path.exists(JS_SCRIPTS_DIR):
            for filename in os.listdir(JS_SCRIPTS_DIR):
                if filename.endswith('.json'):
                    try:
                        path = os.path.join(JS_SCRIPTS_DIR, filename)
                        with open(path, 'r') as f:
                            script_data = json.load(f)
                            script_id = filename.replace('.json', '')
                            self.scripts[script_id] = script_data
                    except Exception:
                        pass
    
    def save_script(self, script_data: Dict) -> str:
        script_id = hashlib.md5(
            f"{script_data.get('name', '')}_{time.time()}".encode()
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
    
    def delete_script(self, script_id: str) -> bool:
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
        return self.scripts.get(script_id)
    
    def list_scripts(self) -> List[Dict]:
        return list(self.scripts.values())

class ChromeSessionManager:
    def __init__(self):
        self.db = SessionDB()
        os.makedirs(BASE_PROFILE_DIR, exist_ok=True)
        self.chrome_path = self._find_chrome()
        self.devtools = {}
        self.display = self._find_display()
        self.js_manager = JavaScriptManager()
        self.is_root = os.geteuid() == 0
        
        if self.display:
            os.environ['DISPLAY'] = self.display
            console.print(f"[green]✅ Using display: {self.display}[/green]")
        else:
            console.print("[yellow]⚠️ No display available[/yellow]")

    def _find_display(self) -> Optional[str]:
        if 'DISPLAY' in os.environ:
            return os.environ['DISPLAY']
        
        for display in [':0', ':1', ':2', ':3', ':99']:
            try:
                port = 6000 + int(display.replace(':', ''))
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', port))
                sock.close()
                if result == 0:
                    return display
            except:
                pass
        return None

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
        raise RuntimeError(f"No available ports")

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

    def start_session(self, session_id: int, force_restart: bool = False):
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

        # Chrome flags with proper WebSocket support
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
        ]

        if self.is_root:
            cmd.extend([
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ])

        if self.display:
            cmd.extend(["--start-maximized", session['url']])
        else:
            cmd.extend([
                "--headless",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--no-sandbox",
                f"--window-size=1366,768",
                session['url']
            ])

        try:
            env = os.environ.copy()
            if self.display:
                env['DISPLAY'] = self.display

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
                text=True,
                env=env
            )

            console.print("[yellow]⏳ Waiting for Chrome to start...[/yellow]")
            time.sleep(4)

            if process.poll() is not None:
                stdout, stderr = process.communicate()
                console.print("[red]❌ Chrome process died[/red]")
                if stderr:
                    console.print(f"[dim]{stderr[:500]}[/dim]")
                return

            devtools = self._get_devtools(session['port'])
            connected = False

            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                task = progress.add_task("Connecting...", total=None)
                for i in range(30):
                    if process.poll() is not None:
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
                
                version_info = devtools.get_version_info()
                if version_info:
                    console.print(f"[dim]   Chrome: {version_info.get('Browser', 'Unknown')}[/dim]")
            else:
                console.print("[red]❌ Failed to start Chrome[/red]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

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
  📜 Saved Scripts: {len(self.js_manager.list_scripts())}

[bold]Storage:[/bold]
  📁 Base Directory: {BASE_PROFILE_DIR}
  📁 Scripts Directory: {JS_SCRIPTS_DIR}
  🔧 Chrome: {self.chrome_path}
  🖥️ Display: {self.display if self.display else "❌ None"}
  🔒 Root: {"✅" if self.is_root else "❌"}
"""
        console.print(Panel(content, title="Dashboard", border_style="cyan"))

    def manage_tabs_enhanced(self, session_id: int):
        """Enhanced tab management with proper WebSocket handling"""
        session = self.db.get_session(session_id)
        if not session:
            console.print("[red]Session not found[/red]")
            return

        if session['status'] != 'running':
            console.print("[red]Session not running[/red]")
            if Confirm.ask("Start this session?"):
                self.start_session(session_id)
                time.sleep(2)
                session = self.db.get_session(session_id)
                if session['status'] != 'running':
                    console.print("[red]Failed to start session[/red]")
                    return
            else:
                return

        devtools = self._get_devtools(session['port'])

        if not devtools._ensure_connection():
            console.print(f"[red]Cannot connect to Chrome on port {session['port']}[/red]")
            return

        while True:
            console.clear()
            console.print(Panel(f"📑 Enhanced Tab Manager - {session['name']} (Port: {session['port']})", style="cyan"))
            console.print()

            tabs = devtools.get_tabs()

            if not tabs:
                console.print("[yellow]No tabs open[/yellow]")
            else:
                table = Table(title=f"Open Tabs ({len(tabs)})", box=box.ROUNDED)
                table.add_column("#", style="cyan", width=4)
                table.add_column("Title", style="green", no_wrap=False)
                table.add_column("URL", style="blue", no_wrap=False)

                for i, tab in enumerate(tabs, 1):
                    title = tab.get('title', 'Untitled')[:60]
                    url = tab.get('url', '')[:70]
                    table.add_row(str(i), title, url)

                console.print(table)

            console.print()
            console.print("[cyan]📌 Tab Actions:[/cyan]")
            console.print("  [1] New tab        [2] Close tab      [3] Navigate")
            console.print("  [4] View HTML      [5] View Text      [6] View Metadata")
            console.print("  [7] Execute JS     [8] Click Element  [9] Fill Input")
            console.print("  [10] Get Links     [11] Get Images    [12] Get Cookies")
            console.print("  [13] Get Storage   [14] Save Content  [15] JS Scripts")
            console.print("  [0] Back")

            choice = Prompt.ask("Select", choices=["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15"])

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
                                console.print(Panel(content, title=f"HTML Content - Tab {num}", border_style="green"))
                    except Exception as e:
                        console.print(f"[red]Error: {e}[/red]")
                else:
                    console.print("[yellow]No tabs to view[/yellow]")

            elif choice == "5":  # View Text
                if tabs:
                    try:
                        num = int(Prompt.ask("Tab number", choices=[str(i+1) for i in range(len(tabs))]))
                        if 0 < num <= len(tabs):
                            text = devtools.get_page_text(tabs[num-1]['id'])
                            if text:
                                if len(text) > 5000:
                                    text = text[:5000] + "\n\n... (truncated)"
                                console.print(Panel(text, title=f"Page Text - Tab {num}", border_style="blue"))
                    except:
                        pass
                else:
                    console.print("[yellow]No tabs to view[/yellow]")

            elif choice == "6":  # View Metadata
                if tabs:
                    try:
                        num = int(Prompt.ask("Tab number", choices=[str(i+1) for i in range(len(tabs))]))
                        if 0 < num <= len(tabs):
                            metadata = devtools.get_page_metadata(tabs[num-1]['id'])
                            if metadata:
                                content = "\n".join([f"[bold]{k}:[/bold] {v}" for k, v in metadata.items()])
                                console.print(Panel(content, title=f"Page Metadata - Tab {num}", border_style="cyan"))
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
                                console.print("[yellow]Executing script...[/yellow]")
                                result = devtools.execute_script(tabs[num-1]['id'], script)

                                if result:
                                    result_str = json.dumps(result, indent=2, default=str)
                                    console.print(Panel(
                                        result_str[:5000] + ("..." if len(result_str) > 5000 else ""),
                                        title="Result",
                                        border_style="green"
                                    ))
                                    
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
                                else:
                                    console.print("[red]❌ Script execution failed - no result returned[/red]")
                    except Exception as e:
                        console.print(f"[red]Error: {e}[/red]")
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
                            links = devtools.get_all_links(tabs[num-1]['id'])
                            if links:
                                content = "\n".join(links[:50])
                                if len(links) > 50:
                                    content += f"\n\n... and {len(links)-50} more"
                                console.print(Panel(content, title=f"Links ({len(links)})", border_style="yellow"))
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
                            images = devtools.get_all_images(tabs[num-1]['id'])
                            if images:
                                content = "\n".join(images[:50])
                                if len(images) > 50:
                                    content += f"\n\n... and {len(images)-50} more"
                                console.print(Panel(content, title=f"Images ({len(images)})", border_style="magenta"))
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
                            cookies = devtools.get_cookies(tabs[num-1]['id'])
                            if cookies:
                                content = "\n".join([f"{c['name']}: {c['value']}" for c in cookies])
                                console.print(Panel(content, title=f"Cookies ({len(cookies)})", border_style="cyan"))
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
                                console.print(Panel(content, title="Storage", border_style="green"))
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
                            if devtools.save_page_content(tabs[num-1]['id'], filename):
                                console.print(f"[green]✅ Saved: {filename}[/green]")
                            else:
                                console.print("[red]❌ Failed to save[/red]")
                    except:
                        pass
                else:
                    console.print("[yellow]No tabs to save[/yellow]")

            elif choice == "15":  # JS Scripts
                self._manage_scripts(session_id)

            if choice != "0":
                console.print()
                Prompt.ask("Press Enter to continue...")

    def _manage_scripts(self, session_id: int):
        """Manage JavaScript scripts"""
        console.clear()
        console.print(Panel("[bold cyan]📜 JavaScript Script Manager[/bold cyan]", border_style="green"))
        
        while True:
            scripts = self.js_manager.list_scripts()
            
            if scripts:
                table = Table(box=box.SIMPLE)
                table.add_column("ID", style="cyan", width=10)
                table.add_column("Name", style="green")
                table.add_column("URL Pattern", style="blue")
                table.add_column("Created", style="dim")
                
                for script in scripts[:20]:
                    table.add_row(
                        script.get('id', '')[:8],
                        script.get('name', 'Unnamed')[:30],
                        script.get('url', 'Any')[:30],
                        script.get('created', '')[:16]
                    )
                console.print(table)
            else:
                console.print("[dim]No scripts saved[/dim]")
            
            console.print("\n[cyan]📌 Options:[/cyan]")
            console.print("  [1] Load and execute script")
            console.print("  [2] Delete script")
            console.print("  [0] Back")
            
            choice = Prompt.ask("Select", choices=["0", "1", "2"])
            
            if choice == "0":
                break
            elif choice == "1":
                script_id = Prompt.ask("Enter script ID to execute")
                script = self.js_manager.get_script(script_id)
                if script:
                    self._execute_script_on_session(session_id, script)
                else:
                    console.print("[red]Script not found[/red]")
            elif choice == "2":
                script_id = Prompt.ask("Enter script ID to delete")
                if Confirm.ask(f"Delete script {script_id}?"):
                    if self.js_manager.delete_script(script_id):
                        console.print("[green]✅ Script deleted[/green]")
                    else:
                        console.print("[red]Failed to delete script[/red]")
            
            if choice != "0":
                console.print()
                Prompt.ask("Press Enter to continue...")

    def _execute_script_on_session(self, session_id: int, script: Dict):
        """Execute a script on a session"""
        session = self.db.get_session(session_id)
        if not session or session['status'] != 'running':
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
                else:
                    console.print("[red]❌ Script execution failed[/red]")
        except:
            console.print("[red]Invalid input[/red]")

    def interactive_menu(self):
        """Main interactive menu"""
        while True:
            console.clear()
            console.print()

            header = """
╔══════════════════════════════════════════════════════════════╗
║           🌐 Chrome Session Manager - Final Fix            ║
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
            script_count = f"📜 Scripts: {len(self.js_manager.list_scripts())}"
            status_line = f"📊 {total} sessions | 🟢 {running} running | 🔌 {available} ports | {display_status} | {script_count}"
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
            menu.add_row("C", "[bold]Cleanup[/bold]", "Clean up zombie sessions")
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

            elif choice == "C":
                cleaned = self._cleanup_zombie_sessions()
                console.print(f"[green]✅ Cleaned up {cleaned} zombie session(s)[/green]")

            if choice != "0":
                console.print()
                Prompt.ask("Press Enter to continue...")

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
[bold]Profile Directory:[/bold] {session['profile_dir']}
[bold]Profile Size:[/bold] {self._get_dir_size(session['profile_dir'])}
[bold]Created:[/bold] {session['created_at']}
[bold]Last Used:[/bold] {session['last_used'] if session['last_used'] else 'Never'}
"""
        console.print(Panel(content, title="📊 Session Details", border_style="blue"))

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

    def create_session(self):
        console.print()
        console.print(Panel("🆕 Create New Chrome Session", style="bold green"))

        self._cleanup_zombie_sessions()

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
