#!/usr/bin/env python3
"""
Complete Chrome Session Manager - Production Ready
All features working with proper error handling
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

try:
    import psutil
except ImportError:
    import subprocess
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

class ChromeDevTools:
    """Chrome DevTools Protocol interface"""

    def __init__(self, host='127.0.0.1', port=9222):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.session = requests.Session()
        self.session.timeout = 3

    def _ensure_connection(self) -> bool:
        """Check if Chrome DevTools is accessible"""
        try:
            # Try to connect to the websocket directly first
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((self.host, self.port))
            sock.close()
            if result == 0:
                # Port is open, try the HTTP endpoint
                try:
                    response = self.session.get(f"{self.base_url}/json/version", timeout=2)
                    return response.status_code == 200
                except:
                    # Sometimes the HTTP endpoint takes a moment, but WebSocket is ready
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

    def execute_script(self, tab_id: str, script: str) -> Optional[Dict]:
        try:
            tab = self.get_tab_by_id(tab_id)
            if not tab:
                return None

            ws_url = tab.get('webSocketDebuggerUrl')
            if not ws_url:
                return None

            ws = websocket.create_connection(ws_url, timeout=5)
            msg_id = int(time.time() * 1000)
            command = {
                "id": msg_id,
                "method": "Runtime.evaluate",
                "params": {"expression": script, "returnByValue": True}
            }

            ws.send(json.dumps(command))
            response = ws.recv()
            ws.close()

            result = json.loads(response)
            return result.get('result')
        except:
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

    def navigate_to(self, tab_id: str, url: str) -> bool:
        script = f"window.location.href = '{url}'"
        result = self.execute_script(tab_id, script)
        return result is not None

    def get_version_info(self) -> Optional[Dict]:
        """Get Chrome version info"""
        try:
            response = self.session.get(f"{self.base_url}/json/version", timeout=3)
            if response.status_code == 200:
                return response.json()
            return None
        except:
            return None

class ChromeSessionManager:
    def __init__(self):
        self.db = SessionDB()
        os.makedirs(BASE_PROFILE_DIR, exist_ok=True)
        self.chrome_path = self._find_chrome()
        self.devtools = {}

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
        available = self.db.get_available_ports()
        if not available:
            raise RuntimeError("No available ports")
        return available[0]

    def _get_devtools(self, port: int) -> ChromeDevTools:
        if port not in self.devtools:
            self.devtools[port] = ChromeDevTools(port=port)
        return self.devtools[port]

    def _cleanup_zombie_sessions(self):
        """Check and cleanup zombie Chrome processes"""
        sessions = self.db.list_sessions()
        cleaned = 0

        for session in sessions:
            if session['status'] == 'running' and session['pid']:
                try:
                    os.kill(session['pid'], 0)
                    # Check if it's actually Chrome
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
        """Get directory size in human readable format"""
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
        """Check if a port is in use"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result == 0

    def create_session(self):
        """Create a new session"""
        console.print()
        console.print(Panel("🆕 Create New Chrome Session", style="bold green"))

        self._cleanup_zombie_sessions()

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
                    break
                except ValueError:
                    console.print("[red]Please enter a valid number[/red]")
                    continue

        profile_dir = self._get_profile_dir(name)
        os.makedirs(profile_dir, exist_ok=True)

        session_id = self.db.create_session(name, url, port, profile_dir)

        console.print()
        console.print(f"[green]✅ Session created! ID: {session_id}[/green]")
        console.print(f"   Name: {name}")
        console.print(f"   URL: {url}")
        console.print(f"   Port: {port}")
        console.print(f"   Profile: {profile_dir}")

        if Confirm.ask("🚀 Start this session now?"):
            self.start_session(session_id)

    def start_session(self, session_id: int):
        """Start a Chrome session"""
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

        # Check if port is already in use
        if self._is_port_in_use(session['port']):
            console.print(f"[yellow]Port {session['port']} is already in use. Trying next available port...[/yellow]")
            new_port = self._get_next_port()
            console.print(f"[blue]Using port {new_port} instead[/blue]")
            self.db.update_session_port(session_id, new_port)
            session['port'] = new_port

        console.print(f"[blue]🚀 Starting session '{session['name']}'...[/blue]")

        profile_dir = session['profile_dir']
        os.makedirs(profile_dir, exist_ok=True)

        cmd = [
            self.chrome_path,
            f"--remote-debugging-port={session['port']}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--disable-extensions",
            "--disable-gpu",
            "--window-size=1366,768",
            "--start-maximized",
            session['url']
        ]

        try:
            # Redirect output to /dev/null to avoid cluttering the terminal
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )

            console.print("[yellow]⏳ Waiting for Chrome to start...[/yellow]")

            devtools = self._get_devtools(session['port'])
            connected = False
            
            # Wait for Chrome to be ready
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                task = progress.add_task("Connecting...", total=None)
                for i in range(20):  # Try for 40 seconds (20 * 2)
                    if process.poll() is not None:
                        console.print("[red]❌ Chrome process died[/red]")
                        break
                    
                    if devtools.wait_for_connection(timeout=2):
                        connected = True
                        break
                    
                    progress.update(task, description=f"Waiting... ({i+1}/20)")
                    time.sleep(2)

            if process.poll() is None and connected:
                self.db.start_session(session_id, process.pid)
                console.print(f"[green]✅ Session started (PID: {process.pid})[/green]")
                console.print(f"   Debug: http://127.0.0.1:{session['port']}")
                console.print(f"   URL: {session['url']}")
                console.print(f"   Profile: {profile_dir}")

                # Get version info
                version_info = devtools.get_version_info()
                if version_info:
                    console.print(f"[dim]   Chrome: {version_info.get('Browser', 'Unknown')}[/dim]")

                # Get tab info
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
                # Check if process died with an error
                if process.poll() is not None:
                    console.print(f"[red]Process exited with code: {process.returncode}[/red]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback
            traceback.print_exc()

    def stop_session(self, session_id: int):
        """Stop a Chrome session"""
        session = self.db.get_session(session_id)
        if not session:
            console.print(f"[red]Session not found[/red]")
            return

        if session['status'] != 'running':
            console.print(f"[yellow]Session not running[/yellow]")
            return

        try:
            if session['pid']:
                # Try graceful termination first
                os.kill(session['pid'], signal.SIGTERM)
                time.sleep(2)
                
                # Check if still running
                try:
                    os.kill(session['pid'], 0)
                    # Force kill
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

        # Check running status
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
        table.add_column("Last Used", style="dim", width=16)

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
                profile_short[:15],
                session['last_used'][:16] if session['last_used'] else "-"
            )

        console.print(table)

    def show_session_details(self, session_id: int):
        """Show detailed session information"""
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

        # Show profile directory contents (skip locked files)
        if os.path.exists(session['profile_dir']):
            console.print("[dim]Profile directory:[/dim]")
            try:
                files = os.listdir(session['profile_dir'])
                # Filter out locked/temporary files
                visible_files = [f for f in files if not f.startswith('.') and not f.endswith('.lock')]
                if visible_files:
                    table = Table(box=box.SIMPLE)
                    table.add_column("File/Dir", style="green")
                    table.add_column("Size", style="yellow")
                    for f in visible_files[:15]:
                        f_path = os.path.join(session['profile_dir'], f)
                        if os.path.isdir(f_path):
                            try:
                                count = len(os.listdir(f_path))
                                size = f"📁 {count} items"
                            except:
                                size = "📁"
                        else:
                            try:
                                size = f"{os.path.getsize(f_path):,} bytes"
                            except:
                                size = "Unknown"
                        table.add_row(f, size)
                    console.print(table)
                    if len(visible_files) > 15:
                        console.print(f"[dim]... and {len(visible_files) - 15} more files[/dim]")
                else:
                    console.print("[dim]Profile directory is empty or locked[/dim]")
            except Exception as e:
                console.print(f"[dim]Could not list directory (Chrome is using it)[/dim]")

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
                    # Try to delete, ignore locked files
                    shutil.rmtree(session['profile_dir'], ignore_errors=True)
                    console.print(f"[dim]Deleted profile directory[/dim]")
                except:
                    console.print("[yellow]Could not fully delete profile directory (some files may be locked)[/yellow]")

            self.db.delete_session(session_id)
            console.print(f"[green]✅ Session deleted[/green]")

    def manage_tabs(self, session_id: int):
        """Interactive tab management"""
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

        while True:
            console.clear()
            console.print(Panel(f"📑 Tab Manager - {session['name']} (Port: {session['port']})", style="cyan"))
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
            console.print("[cyan]Actions:[/cyan]")
            console.print("  [1] New tab    [2] Close tab    [3] Navigate")
            console.print("  [4] Get content    [5] Execute script")
            console.print("  [6] Refresh    [0] Back")

            choice = Prompt.ask("Select", choices=["0", "1", "2", "3", "4", "5", "6"])

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

            elif choice == "4":
                if tabs:
                    try:
                        num = int(Prompt.ask("Tab number", choices=[str(i+1) for i in range(len(tabs))]))
                        if 0 < num <= len(tabs):
                            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                                progress.add_task("Fetching...", total=None)
                                title = devtools.get_page_title(tabs[num-1]['id'])
                                content = devtools.get_page_content(tabs[num-1]['id'])

                            if content:
                                console.print(Panel(
                                    f"[bold]Title:[/bold] {title or 'Untitled'}\n"
                                    f"[bold]Size:[/bold] {len(content):,} bytes\n\n"
                                    f"{content[:1000]}{'...' if len(content) > 1000 else ''}",
                                    title="Page Content", border_style="green"
                                ))
                                if Confirm.ask("Save to file?"):
                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    filename = f"{session['name']}_{timestamp}.html"
                                    with open(filename, 'w', encoding='utf-8') as f:
                                        f.write(content)
                                    console.print(f"[green]✅ Saved: {filename}[/green]")
                    except:
                        pass
                else:
                    console.print("[yellow]No tabs to fetch[/yellow]")

            elif choice == "5":
                if tabs:
                    try:
                        num = int(Prompt.ask("Tab number", choices=[str(i+1) for i in range(len(tabs))]))
                        if 0 < num <= len(tabs):
                            script = Prompt.ask("JavaScript")
                            result = devtools.execute_script(tabs[num-1]['id'], script)
                            if result:
                                console.print(Panel(
                                    json.dumps(result, indent=2, default=str),
                                    title="Result", border_style="cyan"
                                ))
                    except:
                        pass
                else:
                    console.print("[yellow]No tabs to execute on[/yellow]")

            elif choice == "6":
                continue

            if choice != "0":
                Prompt.ask("Press Enter...")

    def show_dashboard(self):
        """Show comprehensive dashboard"""
        self._cleanup_zombie_sessions()

        sessions = self.db.list_sessions()
        running = [s for s in sessions if s['status'] == 'running']
        stopped = [s for s in sessions if s['status'] == 'stopped']

        # Calculate total size
        total_size = sum(self._get_dir_size_bytes(s['profile_dir']) for s in sessions)

        content = f"""
[bold green]📊 Chrome Session Dashboard[/bold green]

[bold]Overview:[/bold]
  Total Sessions: {len(sessions)}
  🟢 Running: {len(running)}
  ⚪ Stopped: {len(stopped)}
  🔌 Available Ports: {len(self.db.get_available_ports())}
  💾 Total Profile Size: {self._format_size(total_size)}

[bold]Storage:[/bold]
  📁 Base Directory: {BASE_PROFILE_DIR}
  🔧 Chrome: {self.chrome_path}

[bold]Sessions:[/bold]
"""

        for session in sessions:
            status_icon = "🟢" if session['status'] == 'running' else "⚪"
            profile_size = self._get_dir_size(session['profile_dir'])
            content += f"  {status_icon} {session['name']:20} Port: {session['port']:4} Size: {profile_size:>10}\n"

        console.print(Panel(content, title="Dashboard", border_style="cyan"))

        if running:
            table = Table(title="🟢 Running Sessions", box=box.SIMPLE)
            table.add_column("Name", style="green")
            table.add_column("Port", style="yellow")
            table.add_column("PID", style="red")
            table.add_column("Debug URL", style="blue")
            table.add_column("Profile", style="dim")

            for session in running:
                try:
                    os.kill(session['pid'], 0)
                    status = "✅"
                except:
                    status = "❌"
                    self.db.stop_session(session['id'])
                    self.db.release_port(session['port'])

                table.add_row(
                    session['name'],
                    str(session['port']),
                    f"{session['pid']} {status}",
                    f"http://127.0.0.1:{session['port']}",
                    os.path.basename(session['profile_dir'])
                )

            console.print(table)

    def interactive_menu(self):
        """Main interactive menu"""
        while True:
            console.clear()
            console.print()

            header = """
╔══════════════════════════════════════════════════════════════╗
║           🌐 Chrome Session Manager Complete              ║
║           Persistent Chrome Sessions with Automation     ║
╚══════════════════════════════════════════════════════════════╝
            """
            console.print(Panel(header, border_style="cyan"))

            self._cleanup_zombie_sessions()

            sessions = self.db.list_sessions()
            running = len([s for s in sessions if s['status'] == 'running'])
            total = len(sessions)
            available = len(self.db.get_available_ports())

            status_line = f"📊 {total} sessions | 🟢 {running} running | 🔌 {available} ports available"
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
            menu.add_row("8", "[bold]Manage Tabs[/bold]", "Manage tabs in a running session")
            menu.add_row("9", "[bold]Cleanup[/bold]", "Clean up zombie sessions")
            menu.add_row("0", "[red]Exit[/red]", "Exit the manager")

            console.print(menu)
            console.print()

            choice = Prompt.ask("Select option", choices=["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"])

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
                    self.manage_tabs(session_id)
                except ValueError:
                    console.print("[red]Invalid ID[/red]")

            elif choice == "9":
                cleaned = self._cleanup_zombie_sessions()
                console.print(f"[green]✅ Cleaned up {cleaned} zombie session(s)[/green]")

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
