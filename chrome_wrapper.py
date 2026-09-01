# chrome_wrapper.py - Complete wrapper for Chrome API + Script Library
#!/usr/bin/env python3
"""
Chrome Automation Wrapper
Combines API client with script library management
"""

import os
import sys
import json
import time
import base64
import requests
from pathlib import Path
from typing import Optional, Dict, List, Any, Union
from datetime import datetime
from dataclasses import dataclass, field
import subprocess
import argparse

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich import box
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.syntax import Syntax
    from rich.tree import Tree
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("⚠️  Rich library not installed. Run: pip install rich")

# ============================================================================
# Configuration
# ============================================================================

@dataclass
class Config:
    api_url: str = "http://127.0.0.1:5000"
    scripts_dir: str = "/data/data/com.termux/files/home/automation/chrome-launcher/scripts-library"
    session_name: str = "unstop"
    timeout: int = 30
    
    # Color codes for non-rich output
    COLORS = {
        'green': '\033[92m',
        'red': '\033[91m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'cyan': '\033[96m',
        'magenta': '\033[95m',
        'white': '\033[97m',
        'reset': '\033[0m'
    }

# ============================================================================
# Chrome API Client
# ============================================================================

class ChromeAPIClient:
    """Client for the Chrome Daemon API"""
    
    def __init__(self, config: Config):
        self.config = config
        self.base_url = config.api_url
        self.session_name = config.session_name
        self._session = requests.Session()
        self._session.timeout = config.timeout
        
    def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make API request with error handling"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method.upper() == 'GET':
                resp = self._session.get(url)
            elif method.upper() == 'POST':
                resp = self._session.post(url, json=data)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            return {'error': 'API server not running. Start with: python api.py'}
        except requests.exceptions.Timeout:
            return {'error': 'Request timeout'}
        except Exception as e:
            return {'error': str(e)}
    
    # ===== Session Management =====
    
    def health_check(self) -> Dict:
        """Check API health"""
        return self._request('GET', '/health')
    
    def list_sessions(self) -> Dict:
        """List all sessions"""
        return self._request('GET', '/sessions')
    
    def get_session_status(self, name: str = None) -> Dict:
        """Get session status"""
        name = name or self.session_name
        return self._request('GET', f'/session/{name}/status')
    
    def start_session(self, name: str = None, url: str = "https://unstop.com/") -> Dict:
        """Start a session"""
        name = name or self.session_name
        return self._request('POST', f'/session/{name}/start', {'url': url})
    
    def stop_session(self, name: str = None) -> Dict:
        """Stop a session"""
        name = name or self.session_name
        return self._request('POST', f'/session/{name}/stop')
    
    # ===== Page Operations =====
    
    def navigate(self, url: str, name: str = None) -> Dict:
        """Navigate to URL"""
        name = name or self.session_name
        return self._request('POST', f'/session/{name}/navigate', {'url': url})
    
    def get_url(self, name: str = None) -> Dict:
        """Get current URL"""
        name = name or self.session_name
        return self._request('GET', f'/session/{name}/url')
    
    def get_html(self, name: str = None) -> Dict:
        """Get page HTML"""
        name = name or self.session_name
        return self._request('GET', f'/session/{name}/html')
    
    def get_screenshot(self, name: str = None) -> Dict:
        """Get screenshot (base64)"""
        name = name or self.session_name
        return self._request('GET', f'/session/{name}/screenshot')
    
    # ===== Interaction =====
    
    def click(self, selector: str, name: str = None) -> Dict:
        """Click element by CSS selector"""
        name = name or self.session_name
        return self._request('POST', f'/session/{name}/click', {'selector': selector})
    
    def evaluate(self, expression: str, name: str = None) -> Dict:
        """Execute JavaScript"""
        name = name or self.session_name
        return self._request('POST', f'/session/{name}/evaluate', {'expression': expression})
    
    def cdp_command(self, method: str, params: Dict = None, name: str = None) -> Dict:
        """Execute CDP command"""
        name = name or self.session_name
        return self._request('POST', f'/session/{name}/cdp', {
            'method': method,
            'params': params or {}
        })
    
    # ===== Script Execution =====
    
    def execute_script_file(self, script_path: str, name: str = None) -> Dict:
        """Execute a JavaScript file"""
        name = name or self.session_name
        
        if not os.path.exists(script_path):
            return {'error': f'Script not found: {script_path}'}
        
        with open(script_path, 'r') as f:
            script_content = f.read()
        
        # Wrap in IIFE if not already
        if not script_content.strip().startswith('(function'):
            script_content = f"(function() {{ {script_content} }})()"
        
        return self.evaluate(script_content, name)
    
    def execute_script_by_name(self, script_name: str, category: str = None, 
                                name: str = None) -> Dict:
        """Execute a script by name from the library"""
        name = name or self.session_name
        script_path = self.find_script(script_name, category)
        
        if not script_path:
            return {'error': f'Script not found: {script_name}'}
        
        return self.execute_script_file(script_path, name)
    
    def find_script(self, script_name: str, category: str = None) -> Optional[str]:
        """Find a script in the library"""
        scripts_dir = Path(self.config.scripts_dir)
        
        # If category specified, look there first
        if category:
            path = scripts_dir / category / script_name
            if path.exists():
                return str(path)
            # Try with .js extension
            if not script_name.endswith('.js'):
                path = scripts_dir / category / f"{script_name}.js"
                if path.exists():
                    return str(path)
        
        # Search all directories
        for js_file in scripts_dir.rglob("*.js"):
            if js_file.name == script_name or js_file.stem == script_name:
                return str(js_file)
        
        # Try direct path
        if os.path.exists(script_name):
            return script_name
        
        return None

# ============================================================================
# Script Library Manager
# ============================================================================

class ScriptLibraryManager:
    """Manage and organize scripts from the scripts-library folder"""
    
    def __init__(self, config: Config):
        self.config = config
        self.scripts_dir = Path(config.scripts_dir)
        self._cache = None
        
    def get_structure(self) -> Dict[str, List[str]]:
        """Get the folder structure of scripts"""
        structure = {}
        
        if not self.scripts_dir.exists():
            return {'error': f'Scripts directory not found: {self.scripts_dir}'}
        
        for item in self.scripts_dir.iterdir():
            if item.is_dir():
                structure[item.name] = []
                for js_file in item.glob("*.js"):
                    structure[item.name].append(js_file.name)
        
        return structure
    
    def list_all_scripts(self) -> List[Dict[str, str]]:
        """List all scripts with their categories"""
        scripts = []
        
        for category_dir in self.scripts_dir.iterdir():
            if category_dir.is_dir():
                for js_file in category_dir.glob("*.js"):
                    scripts.append({
                        'name': js_file.name,
                        'category': category_dir.name,
                        'path': str(js_file),
                        'size': js_file.stat().st_size,
                        'modified': datetime.fromtimestamp(js_file.stat().st_mtime).isoformat()
                    })
        
        return sorted(scripts, key=lambda x: (x['category'], x['name']))
    
    def get_script_content(self, script_name: str, category: str = None) -> Optional[str]:
        """Get script content"""
        client = ChromeAPIClient(self.config)
        path = client.find_script(script_name, category)
        
        if not path:
            return None
        
        with open(path, 'r') as f:
            return f.read()
    
    def get_categories(self) -> List[str]:
        """Get all categories"""
        if not self.scripts_dir.exists():
            return []
        
        return [d.name for d in self.scripts_dir.iterdir() if d.is_dir()]
    
    def get_scripts_in_category(self, category: str) -> List[str]:
        """Get all scripts in a category"""
        category_dir = self.scripts_dir / category
        if not category_dir.exists():
            return []
        
        return [f.name for f in category_dir.glob("*.js")]
    
    def create_script(self, category: str, name: str, content: str) -> Dict:
        """Create a new script"""
        category_dir = self.scripts_dir / category
        category_dir.mkdir(parents=True, exist_ok=True)
        
        if not name.endswith('.js'):
            name = f"{name}.js"
        
        file_path = category_dir / name
        
        if file_path.exists():
            return {'error': f'Script already exists: {name}'}
        
        with open(file_path, 'w') as f:
            f.write(content)
        
        return {
            'success': True,
            'path': str(file_path),
            'category': category,
            'name': name
        }
    
    def delete_script(self, script_name: str, category: str = None) -> Dict:
        """Delete a script"""
        client = ChromeAPIClient(self.config)
        path = client.find_script(script_name, category)
        
        if not path:
            return {'error': f'Script not found: {script_name}'}
        
        try:
            os.remove(path)
            return {'success': True, 'path': path}
        except Exception as e:
            return {'error': str(e)}

# ============================================================================
# Rich Output Helpers
# ============================================================================

class OutputHelper:
    """Helper for formatted output"""
    
    def __init__(self, config: Config):
        self.config = config
        self.use_rich = RICH_AVAILABLE
        self.console = Console() if RICH_AVAILABLE else None
    
    def print(self, text: str, color: str = 'white', bold: bool = False):
        """Print colored text"""
        if self.use_rich:
            style = color
            if bold:
                style = f"bold {color}"
            self.console.print(text, style=style)
        else:
            color_code = self.config.COLORS.get(color, '')
            reset = self.config.COLORS.get('reset', '')
            print(f"{color_code}{text}{reset}")
    
    def print_success(self, text: str):
        self.print(f"✅ {text}", 'green')
    
    def print_error(self, text: str):
        self.print(f"❌ {text}", 'red')
    
    def print_warning(self, text: str):
        self.print(f"⚠️  {text}", 'yellow')
    
    def print_info(self, text: str):
        self.print(f"ℹ️  {text}", 'blue')
    
    def print_header(self, text: str):
        if self.use_rich:
            self.console.print(Panel(text, border_style='cyan'))
        else:
            print(f"\n{'='*60}")
            print(f" {text}")
            print(f"{'='*60}\n")
    
    def print_table(self, headers: List[str], rows: List[List], title: str = None):
        """Print a table"""
        if self.use_rich:
            table = Table(title=title, box=box.ROUNDED)
            for header in headers:
                table.add_column(header, style='cyan')
            for row in rows:
                table.add_row(*[str(cell) for cell in row])
            self.console.print(table)
        else:
            if title:
                print(f"\n{title}")
                print("-" * len(title))
            
            # Print headers
            header_row = " | ".join(headers)
            print(header_row)
            print("-" * len(header_row))
            
            # Print rows
            for row in rows:
                print(" | ".join(str(cell) for cell in row))
            print()
    
    def print_script_content(self, content: str, title: str = "Script Content"):
        """Print script content with syntax highlighting"""
        if self.use_rich:
            syntax = Syntax(content, "javascript", theme="monokai", line_numbers=True)
            self.console.print(Panel(syntax, title=title, border_style='green'))
        else:
            print(f"\n--- {title} ---")
            print(content[:500] + ("..." if len(content) > 500 else ""))
            print("---\n")
    
    def print_response(self, response: Dict, title: str = "Response"):
        """Print API response"""
        if self.use_rich:
            json_str = json.dumps(response, indent=2)
            syntax = Syntax(json_str, "json", theme="monokai")
            self.console.print(Panel(syntax, title=title, border_style='yellow'))
        else:
            print(f"\n--- {title} ---")
            print(json.dumps(response, indent=2))
            print("---\n")

# ============================================================================
# Main Wrapper Application
# ============================================================================

class ChromeWrapper:
    """Main wrapper application"""
    
    def __init__(self, config: Config = None):
        self.config = config or Config()
        self.client = ChromeAPIClient(self.config)
        self.script_manager = ScriptLibraryManager(self.config)
        self.output = OutputHelper(self.config)
        
    def run_interactive(self):
        """Run interactive mode"""
        while True:
            self._clear_screen()
            self._show_menu()
            
            choice = Prompt.ask("Select option", 
                               choices=["0","1","2","3","4","5","6","7","8","9","10","11","12"])
            
            if choice == "0":
                self.output.print("Goodbye! 👋", 'green')
                break
            elif choice == "1":
                self._list_sessions()
            elif choice == "2":
                self._start_session()
            elif choice == "3":
                self._stop_session()
            elif choice == "4":
                self._navigate()
            elif choice == "5":
                self._execute_script()
            elif choice == "6":
                self._list_scripts()
            elif choice == "7":
                self._create_script()
            elif choice == "8":
                self._delete_script()
            elif choice == "9":
                self._view_script()
            elif choice == "10":
                self._get_page_info()
            elif choice == "11":
                self._take_screenshot()
            elif choice == "12":
                self._show_status()
            
            if choice != "0":
                Prompt.ask("\nPress Enter to continue...")
    
    def _clear_screen(self):
        """Clear terminal screen"""
        os.system('clear' if os.name == 'posix' else 'cls')
    
    def _show_menu(self):
        """Show main menu"""
        self.output.print_header("🌐 Chrome Automation Wrapper")
        
        # Show current session
        self.output.print_info(f"Current Session: {self.config.session_name}")
        
        # Check API health
        health = self.client.health_check()
        if 'error' in health:
            self.output.print_error(f"API Status: OFFLINE - {health['error']}")
        else:
            self.output.print_success(f"API Status: ONLINE - {health.get('service', '')}")
        
        # Show session status
        status = self.client.get_session_status()
        if 'exists' in status and status['exists']:
            connected = status.get('connected', False)
            icon = "🟢" if connected else "🟡"
            self.output.print(f"  Session Status: {icon} {status.get('session', {}).get('status', 'unknown')}")
            if connected:
                self.output.print_success("  WebSocket: Connected")
        else:
            self.output.print_warning("  Session: Not running")
        
        print()
        
        menu_items = [
            ("1", "List Sessions", "Show all available sessions"),
            ("2", "Start Session", "Start a Chrome session"),
            ("3", "Stop Session", "Stop a running session"),
            ("4", "Navigate", "Navigate to a URL"),
            ("5", "Execute Script", "Run a JavaScript script"),
            ("6", "List Scripts", "Browse available scripts"),
            ("7", "Create Script", "Create a new script"),
            ("8", "Delete Script", "Delete an existing script"),
            ("9", "View Script", "View script content"),
            ("10", "Page Info", "Get current page information"),
            ("11", "Screenshot", "Take a screenshot"),
            ("12", "Session Status", "Show detailed session status"),
            ("0", "Exit", "Exit the wrapper"),
        ]
        
        self.output.print_table(
            ["Option", "Action", "Description"],
            menu_items,
            "Main Menu"
        )
    
    def _list_sessions(self):
        """List all sessions"""
        self.output.print_header("📋 All Sessions")
        result = self.client.list_sessions()
        
        if 'error' in result:
            self.output.print_error(result['error'])
            return
        
        sessions = result.get('sessions', [])
        if not sessions:
            self.output.print_warning("No sessions found")
            return
        
        rows = []
        for s in sessions:
            status = s.get('status', 'unknown')
            status_icon = "🟢" if status == 'running' else "⚪"
            rows.append([
                s.get('id', 'N/A'),
                s.get('name', 'N/A'),
                s.get('url', 'N/A')[:40] + "...",
                s.get('port', 'N/A'),
                f"{status_icon} {status}",
                s.get('ws_id', 'None') or 'None'
            ])
        
        self.output.print_table(
            ["ID", "Name", "URL", "Port", "Status", "WS ID"],
            rows,
            "Sessions"
        )
    
    def _start_session(self):
        """Start a session"""
        self.output.print_header("🚀 Start Session")
        
        name = Prompt.ask("Session name", default=self.config.session_name)
        url = Prompt.ask("URL to open", default="https://unstop.com/")
        
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), 
                     transient=True) as progress:
            progress.add_task(description="Starting session...", total=None)
            result = self.client.start_session(name, url)
        
        if 'error' in result:
            self.output.print_error(f"Failed: {result['error']}")
        else:
            self.output.print_success(f"Session '{name}' started successfully")
            if result.get('ws_connected'):
                self.output.print_success("✅ WebSocket connected")
            else:
                self.output.print_warning("WebSocket connection pending...")
    
    def _stop_session(self):
        """Stop a session"""
        self.output.print_header("⏹️ Stop Session")
        
        name = Prompt.ask("Session name to stop", default=self.config.session_name)
        
        if not Confirm.ask(f"Stop session '{name}'?"):
            return
        
        result = self.client.stop_session(name)
        
        if 'error' in result:
            self.output.print_error(f"Failed: {result['error']}")
        else:
            self.output.print_success(f"Session '{name}' stopped")
    
    def _navigate(self):
        """Navigate to URL"""
        self.output.print_header("🌐 Navigate")
        
        url = Prompt.ask("URL to navigate to", default="https://unstop.com/")
        name = Prompt.ask("Session name", default=self.config.session_name)
        
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), 
                     transient=True) as progress:
            progress.add_task(description="Navigating...", total=None)
            result = self.client.navigate(url, name)
        
        if 'error' in result:
            self.output.print_error(f"Failed: {result['error']}")
        else:
            self.output.print_success(f"Navigated to: {url}")
            
            # Get current URL after navigation
            time.sleep(1)
            current = self.client.get_url(name)
            if 'url' in current:
                self.output.print_info(f"Current URL: {current['url']}")
    
    def _list_scripts(self):
        """List all scripts"""
        self.output.print_header("📜 Script Library")
        
        scripts = self.script_manager.list_all_scripts()
        
        if not scripts:
            self.output.print_warning("No scripts found")
            return
        
        # Group by category
        rows = []
        for script in scripts:
            rows.append([
                script['category'],
                script['name'],
                f"{script['size']:,} bytes",
                script['modified'][:10]
            ])
        
        self.output.print_table(
            ["Category", "Script Name", "Size", "Modified"],
            rows,
            f"Scripts Library ({len(scripts)} scripts)"
        )
        
        # Show folder structure
        self.output.print_info("\n📂 Categories:")
        structure = self.script_manager.get_structure()
        for category, files in structure.items():
            count = len(files)
            self.output.print(f"  📁 {category}/ ({count} scripts)", 'cyan')
    
    def _execute_script(self):
        """Execute a script"""
        self.output.print_header("▶️ Execute Script")
        
        # List categories
        categories = self.script_manager.get_categories()
        if not categories:
            self.output.print_error("No script categories found")
            return
        
        self.output.print("Available categories:")
        for i, cat in enumerate(categories, 1):
            self.output.print(f"  [{i}] {cat}")
        
        cat_choice = Prompt.ask("Select category (or press Enter for all)", 
                                default="")
        
        if cat_choice:
            try:
                idx = int(cat_choice) - 1
                category = categories[idx] if 0 <= idx < len(categories) else None
            except ValueError:
                category = cat_choice if cat_choice in categories else None
        else:
            category = None
        
        # List scripts
        if category:
            scripts = self.script_manager.get_scripts_in_category(category)
            self.output.print_info(f"Scripts in {category}:")
        else:
            scripts = [s['name'] for s in self.script_manager.list_all_scripts()]
        
        for i, script in enumerate(scripts, 1):
            self.output.print(f"  [{i}] {script}")
        
        script_choice = Prompt.ask("Select script (number or name)")
        
        # Find the script
        if script_choice.isdigit():
            idx = int(script_choice) - 1
            if 0 <= idx < len(scripts):
                script_name = scripts[idx]
            else:
                self.output.print_error("Invalid selection")
                return
        else:
            script_name = script_choice
        
        name = Prompt.ask("Session name", default=self.config.session_name)
        
        self.output.print_info(f"Executing: {script_name}")
        self.output.print_info(f"Session: {name}")
        
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), 
                     transient=True) as progress:
            progress.add_task(description="Executing script...", total=None)
            result = self.client.execute_script_by_name(script_name, category, name)
        
        if 'error' in result:
            self.output.print_error(f"Failed: {result['error']}")
        else:
            self.output.print_success("Script executed successfully")
            self.output.print_response(result, "Script Result")
    
    def _create_script(self):
        """Create a new script"""
        self.output.print_header("✏️ Create Script")
        
        category = Prompt.ask("Category name (will create if doesn't exist)")
        name = Prompt.ask("Script name (e.g., my-script.js)")
        
        if not name.endswith('.js'):
            name = f"{name}.js"
        
        self.output.print_info("Enter script content (type 'END' on a new line to finish):")
        lines = []
        while True:
            line = input()
            if line.strip() == 'END':
                break
            lines.append(line)
        
        content = '\n'.join(lines)
        
        if not content.strip():
            self.output.print_warning("Empty script, not creating")
            return
        
        result = self.script_manager.create_script(category, name, content)
        
        if 'error' in result:
            self.output.print_error(f"Failed: {result['error']}")
        else:
            self.output.print_success(f"Script created: {result['path']}")
    
    def _delete_script(self):
        """Delete a script"""
        self.output.print_header("🗑️ Delete Script")
        
        scripts = self.script_manager.list_all_scripts()
        if not scripts:
            self.output.print_warning("No scripts found")
            return
        
        for i, s in enumerate(scripts, 1):
            self.output.print(f"  [{i}] {s['category']}/{s['name']}")
        
        choice = Prompt.ask("Select script to delete (number or name)")
        
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(scripts):
                script = scripts[idx]
            else:
                self.output.print_error("Invalid selection")
                return
        else:
            # Find by name
            matches = [s for s in scripts if s['name'] == choice or s['name'].startswith(choice)]
            if not matches:
                self.output.print_error(f"Script not found: {choice}")
                return
            script = matches[0]
        
        if not Confirm.ask(f"Delete {script['category']}/{script['name']}?"):
            return
        
        result = self.script_manager.delete_script(script['name'], script['category'])
        
        if 'error' in result:
            self.output.print_error(f"Failed: {result['error']}")
        else:
            self.output.print_success(f"Deleted: {result['path']}")
    
    def _view_script(self):
        """View script content"""
        self.output.print_header("📄 View Script")
        
        scripts = self.script_manager.list_all_scripts()
        if not scripts:
            self.output.print_warning("No scripts found")
            return
        
        for i, s in enumerate(scripts, 1):
            self.output.print(f"  [{i}] {s['category']}/{s['name']}")
        
        choice = Prompt.ask("Select script to view (number or name)")
        
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(scripts):
                script = scripts[idx]
            else:
                self.output.print_error("Invalid selection")
                return
        else:
            matches = [s for s in scripts if s['name'] == choice or s['name'].startswith(choice)]
            if not matches:
                self.output.print_error(f"Script not found: {choice}")
                return
            script = matches[0]
        
        content = self.script_manager.get_script_content(script['name'], script['category'])
        
        if content:
            self.output.print_script_content(content, f"{script['category']}/{script['name']}")
        else:
            self.output.print_error("Failed to read script")
    
    def _get_page_info(self):
        """Get current page information"""
        self.output.print_header("📊 Page Information")
        
        name = Prompt.ask("Session name", default=self.config.session_name)
        
        # Get URL
        url_result = self.client.get_url(name)
        if 'url' in url_result:
            self.output.print_success(f"URL: {url_result['url']}")
        else:
            self.output.print_warning("Could not get URL")
        
        # Get HTML length
        html_result = self.client.get_html(name)
        if 'html' in html_result:
            html_len = len(html_result['html'])
            self.output.print_info(f"HTML length: {html_len:,} characters")
            
            # Show first 200 chars
            preview = html_result['html'][:200].replace('\n', ' ')
            self.output.print(f"Preview: {preview}...")
        else:
            self.output.print_warning("Could not get HTML")
        
        # Get session status
        status = self.client.get_session_status(name)
        if 'exists' in status and status['exists']:
            self.output.print_info(f"Session: {status.get('session', {}).get('name', 'unknown')}")
            self.output.print_info(f"Port: {status.get('session', {}).get('port', 'N/A')}")
            self.output.print_info(f"Connected: {status.get('connected', False)}")
    
    def _take_screenshot(self):
        """Take a screenshot"""
        self.output.print_header("📸 Screenshot")
        
        name = Prompt.ask("Session name", default=self.config.session_name)
        
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), 
                     transient=True) as progress:
            progress.add_task(description="Taking screenshot...", total=None)
            result = self.client.get_screenshot(name)
        
        if 'error' in result:
            self.output.print_error(f"Failed: {result['error']}")
            return
        
        if 'screenshot' in result:
            # Save screenshot
            filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            
            with open(filename, 'wb') as f:
                f.write(base64.b64decode(result['screenshot']))
            
            self.output.print_success(f"Screenshot saved: {filename}")
        else:
            self.output.print_warning("No screenshot data received")
    
    def _show_status(self):
        """Show detailed session status"""
        self.output.print_header("📊 Session Status")
        
        name = Prompt.ask("Session name", default=self.config.session_name)
        
        result = self.client.get_session_status(name)
        
        if 'error' in result:
            self.output.print_error(f"Failed: {result['error']}")
            return
        
        if not result.get('exists'):
            self.output.print_warning(f"Session '{name}' does not exist")
            return
        
        session = result.get('session', {})
        
        self.output.print_table(
            ["Property", "Value"],
            [
                ["Name", session.get('name', 'N/A')],
                ["URL", session.get('url', 'N/A')],
                ["Port", session.get('port', 'N/A')],
                ["Status", session.get('status', 'unknown')],
                ["PID", session.get('pid', 'N/A')],
                ["WebSocket Connected", "✅" if result.get('connected') else "❌"],
                ["WS ID", session.get('current_ws_id', 'None')],
                ["Profile Dir", session.get('profile_dir', 'N/A')],
            ],
            f"Session: {name}"
        )

# ============================================================================
# Command Line Interface
# ============================================================================

def create_parser():
    """Create command-line argument parser"""
    parser = argparse.ArgumentParser(description="Chrome Automation Wrapper")
    parser.add_argument("--api", default="http://127.0.0.1:5000",
                       help="API server URL")
    parser.add_argument("--session", default="unstop",
                       help="Default session name")
    parser.add_argument("--scripts-dir", 
                       default="/data/data/com.termux/files/home/automation/chrome-launcher/scripts-library",
                       help="Scripts library directory")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # List sessions
    subparsers.add_parser("list", help="List all sessions")
    
    # Start session
    start_parser = subparsers.add_parser("start", help="Start a session")
    start_parser.add_argument("--url", default="https://unstop.com/",
                             help="URL to open")
    
    # Stop session
    subparsers.add_parser("stop", help="Stop a session")
    
    # Navigate
    nav_parser = subparsers.add_parser("navigate", help="Navigate to URL")
    nav_parser.add_argument("url", help="URL to navigate to")
    
    # Execute script
    script_parser = subparsers.add_parser("script", help="Execute a script")
    script_parser.add_argument("script", help="Script name or path")
    script_parser.add_argument("--category", help="Script category")
    script_parser.add_argument("--name", help="Session name", default="unstop")
    
    # List scripts
    subparsers.add_parser("scripts", help="List all scripts")
    
    # Status
    subparsers.add_parser("status", help="Show session status")
    
    # Screenshot
    subparsers.add_parser("screenshot", help="Take screenshot")
    
    return parser

def main():
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()
    
    config = Config()
    config.api_url = args.api
    config.session_name = args.session
    config.scripts_dir = args.scripts_dir
    
    wrapper = ChromeWrapper(config)
    
    if not args.command or args.command == "interactive":
        wrapper.run_interactive()
        return
    
    # Handle commands
    client = wrapper.client
    output = wrapper.output
    
    if args.command == "list":
        result = client.list_sessions()
        if 'error' in result:
            output.print_error(result['error'])
        else:
            output.print_response(result, "Sessions")
    
    elif args.command == "start":
        result = client.start_session(config.session_name, args.url)
        output.print_response(result, "Start Session")
    
    elif args.command == "stop":
        result = client.stop_session(config.session_name)
        output.print_response(result, "Stop Session")
    
    elif args.command == "navigate":
        result = client.navigate(args.url)
        output.print_response(result, "Navigate")
    
    elif args.command == "script":
        result = client.execute_script_by_name(args.script, args.category, args.name)
        output.print_response(result, "Script Execution")
    
    elif args.command == "scripts":
        scripts = wrapper.script_manager.list_all_scripts()
        output.print_response({"scripts": scripts, "count": len(scripts)}, "Scripts")
    
    elif args.command == "status":
        result = client.get_session_status(config.session_name)
        output.print_response(result, "Status")
    
    elif args.command == "screenshot":
        result = client.get_screenshot(config.session_name)
        if 'screenshot' in result:
            filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            with open(filename, 'wb') as f:
                f.write(base64.b64decode(result['screenshot']))
            print(f"✅ Screenshot saved: {filename}")
        else:
            print(f"❌ {result.get('error', 'Failed to take screenshot')}")

if __name__ == "__main__":
    main()
