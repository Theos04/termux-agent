#!/usr/bin/env python3
"""
Web Intelligence Agent - CDP + HAR Analysis + DOM Fingerprinting
Fixed version with proper imports and network capture
"""

import json
import websocket
import requests
import sys
import time
import base64
import hashlib
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import box
from rich.tree import Tree
from collections import defaultdict
from urllib.parse import urlparse, urljoin
from datetime import datetime
import gzip
from io import BytesIO

console = Console()

class WebIntelligenceAgent:
    def __init__(self, port=9257):
        self.port = port
        self.ws = None
        self.connected = False
        self.page_title = ""
        self.page_url = ""
        self.dom_fingerprint = {}
        self.navigation_graph = {}
        self.actions = []
        self.network_logs = []
        self.js_contexts = {}
        self.dom_snapshot = {}
        self.network_capture_active = False
        
    def connect(self):
        """Connect to Chrome DevTools Protocol"""
        try:
            resp = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=5)
            tabs = resp.json()

            page_tab = None
            for tab in tabs:
                if tab.get('type') == 'page':
                    page_tab = tab
                    break

            if not page_tab:
                console.print("[red]No page found[/red]")
                return False

            self.page_title = page_tab.get('title', 'Untitled')
            self.page_url = page_tab.get('url', '')
            ws_url = page_tab.get('webSocketDebuggerUrl')

            self.ws = websocket.create_connection(ws_url, timeout=10)

            # Enable required domains
            self._enable_domains()
            
            self.connected = True
            console.print(f"[green]✅ Connected to: {self.page_title}[/green]")
            console.print(f"[dim]   URL: {self.page_url}[/dim]")
            
            # Initial page analysis
            self._analyze_page()
            return True

        except Exception as e:
            console.print(f"[red]Connection failed: {e}[/red]")
            return False

    def _enable_domains(self):
        """Enable all necessary CDP domains"""
        domains = [
            "Network.enable",
            "Runtime.enable",
            "DOM.enable",
            "Page.enable",
            "Performance.enable",
            "Debugger.enable"
        ]
        
        for i, domain in enumerate(domains, start=1):
            try:
                self.ws.send(json.dumps({"id": i, "method": domain}))
                # Wait for response
                self.ws.settimeout(2)
                try:
                    resp = self.ws.recv()
                    data = json.loads(resp)
                    if data.get('error'):
                        console.print(f"[yellow]Warning: {domain} failed: {data['error']}[/yellow]")
                except:
                    pass
            except Exception as e:
                console.print(f"[yellow]Warning: Could not enable {domain}: {e}[/yellow]")

    def _analyze_page(self):
        """Analyze the current page"""
        console.print("[dim]Analyzing page...[/dim]")
        self.dom_fingerprint = self._get_dom_fingerprint()
        self.actions = self._discover_actions()
        self.navigation_graph = self._build_navigation_graph()
        self.dom_snapshot = self._take_dom_snapshot()

    def _get_dom_fingerprint(self):
        """Generate a unique DOM fingerprint"""
        script = """
        (function() {
            const fingerprint = {
                url: window.location.href,
                title: document.title,
                timestamp: Date.now(),
                // Structural fingerprint
                tag_counts: {},
                class_counts: {},
                id_counts: {},
                // Content fingerprint
                text_hash: '',
                // Dynamic elements
                forms: [],
                inputs: [],
                buttons: [],
                links: []
            };
            
            // Count tags
            document.querySelectorAll('*').forEach(el => {
                const tag = el.tagName.toLowerCase();
                fingerprint.tag_counts[tag] = (fingerprint.tag_counts[tag] || 0) + 1;
                
                // Count classes
                if (el.className) {
                    const classes = el.className.split(' ');
                    classes.forEach(cls => {
                        if (cls) {
                            fingerprint.class_counts[cls] = (fingerprint.class_counts[cls] || 0) + 1;
                        }
                    });
                }
                
                // Collect IDs
                if (el.id) {
                    fingerprint.id_counts[el.id] = (fingerprint.id_counts[el.id] || 0) + 1;
                }
            });
            
            // Collect forms
            document.querySelectorAll('form').forEach(form => {
                fingerprint.forms.push({
                    id: form.id || '',
                    action: form.action || '',
                    method: form.method || 'GET',
                    inputs: form.querySelectorAll('input').length
                });
            });
            
            // Collect inputs
            document.querySelectorAll('input:not([type="hidden"]), textarea, select').forEach(input => {
                fingerprint.inputs.push({
                    type: input.type || input.tagName.toLowerCase(),
                    name: input.name || '',
                    id: input.id || '',
                    placeholder: input.placeholder || ''
                });
            });
            
            // Collect buttons
            document.querySelectorAll('button, input[type="submit"], input[type="button"]').forEach(btn => {
                fingerprint.buttons.push({
                    text: btn.textContent.trim() || btn.value || '',
                    id: btn.id || '',
                    type: btn.type || 'button'
                });
            });
            
            // Collect links
            document.querySelectorAll('a[href]').forEach(link => {
                fingerprint.links.push({
                    text: link.textContent.trim() || '',
                    href: link.href || '',
                    path: new URL(link.href).pathname || ''
                });
            });
            
            // Generate text hash
            const text = document.body.textContent;
            let hash = 0;
            for (let i = 0; i < text.length; i++) {
                const char = text.charCodeAt(i);
                hash = ((hash << 5) - hash) + char;
                hash = hash & hash;
            }
            fingerprint.text_hash = hash.toString();
            
            return fingerprint;
        })()
        """
        return self.js(script) or {}

    def _discover_actions(self):
        """Discover all possible actions on the page"""
        script = """
        (function() {
            const actions = [];
            
            // Find all interactive elements
            const interactive = document.querySelectorAll(
                'a[href], button, input:not([type="hidden"]), textarea, select, [role="button"], [role="link"], [onclick]'
            );
            
            interactive.forEach(el => {
                const tag = el.tagName.toLowerCase();
                const text = el.textContent.trim() || el.value || '';
                const action = {
                    type: tag,
                    text: text.substring(0, 50),
                    id: el.id || '',
                    class: el.className || '',
                    // Action type detection
                    action_type: 'click',
                    confidence: 0
                };
                
                // Determine action type
                if (tag === 'a' && el.href) {
                    action.action_type = 'navigate';
                    action.target = el.href;
                    action.confidence = 1.0;
                } else if (tag === 'button' || tag === 'input') {
                    if (el.type === 'submit') {
                        action.action_type = 'submit';
                        action.confidence = 0.9;
                    } else if (el.type === 'reset') {
                        action.action_type = 'reset';
                        action.confidence = 0.8;
                    } else {
                        action.action_type = 'click';
                        action.confidence = 0.7;
                    }
                } else if (['input', 'textarea', 'select'].includes(tag)) {
                    action.action_type = 'input';
                    action.confidence = 0.9;
                } else if (el.getAttribute('role') === 'button' || el.getAttribute('role') === 'link') {
                    action.action_type = 'click';
                    action.confidence = 0.8;
                }
                
                // Check for onclick attribute
                if (el.hasAttribute('onclick')) {
                    action.action_type = 'click';
                    action.confidence = 1.0;
                }
                
                actions.push(action);
            });
            
            return actions;
        })()
        """
        return self.js(script) or []

    def _build_navigation_graph(self):
        """Build a graph of all navigation paths"""
        script = """
        (function() {
            const graph = {
                current_path: window.location.pathname,
                base_url: window.location.origin,
                links: [],
                forms: [],
                possible_routes: []
            };
            
            // Collect all links
            document.querySelectorAll('a[href]').forEach(link => {
                const href = link.href;
                const text = link.textContent.trim() || '';
                try {
                    const url = new URL(href);
                    graph.links.push({
                        text: text.substring(0, 50),
                        path: url.pathname,
                        full_url: href,
                        is_relative: href.startsWith('/')
                    });
                    
                    // Add to possible routes
                    if (href.startsWith('/')) {
                        graph.possible_routes.push(url.pathname);
                    }
                } catch(e) {
                    // Invalid URL
                }
            });
            
            // Collect forms
            document.querySelectorAll('form').forEach(form => {
                graph.forms.push({
                    action: form.action || '',
                    method: form.method || 'GET',
                    inputs: form.querySelectorAll('input').length
                });
            });
            
            return graph;
        })()
        """
        return self.js(script) or {}

    def _take_dom_snapshot(self):
        """Take a complete DOM snapshot"""
        script = """
        (function() {
            const snapshot = {
                timestamp: Date.now(),
                url: window.location.href,
                title: document.title,
                body_hash: '',
                elements: {}
            };
            
            // Get all elements with their content
            const elements = document.querySelectorAll('*');
            snapshot.elements.total = elements.length;
            
            // Sample important elements
            const important = {
                headers: [],
                paragraphs: [],
                lists: [],
                tables: [],
                forms: []
            };
            
            document.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(h => {
                important.headers.push({
                    tag: h.tagName,
                    text: h.textContent.trim()
                });
            });
            
            document.querySelectorAll('p').forEach(p => {
                const text = p.textContent.trim();
                if (text && text.length > 10) {
                    important.paragraphs.push(text.substring(0, 200));
                }
            });
            
            document.querySelectorAll('ul, ol').forEach(list => {
                const items = list.querySelectorAll('li');
                important.lists.push({
                    count: items.length,
                    items: Array.from(items).map(li => li.textContent.trim()).slice(0, 5)
                });
            });
            
            document.querySelectorAll('table').forEach(table => {
                const rows = table.querySelectorAll('tr');
                important.tables.push({
                    rows: rows.length,
                    cols: rows[0] ? rows[0].querySelectorAll('td, th').length : 0
                });
            });
            
            document.querySelectorAll('form').forEach(form => {
                important.forms.push({
                    action: form.action || '',
                    method: form.method || 'GET',
                    inputs: form.querySelectorAll('input, textarea, select').length
                });
            });
            
            snapshot.elements.important = important;
            
            // Generate body hash
            const bodyText = document.body.textContent;
            let hash = 0;
            for (let i = 0; i < bodyText.length; i++) {
                const char = bodyText.charCodeAt(i);
                hash = ((hash << 5) - hash) + char;
                hash = hash & hash;
            }
            snapshot.body_hash = hash.toString();
            
            return snapshot;
        })()
        """
        return self.js(script) or {}

    def capture_network(self, duration=10):
        """Capture network activity for specified duration"""
        console.print(f"[yellow]⏳ Capturing network traffic for {duration}s...[/yellow]")
        
        self.network_logs = []
        
        # Enable network capture
        self.ws.send(json.dumps({"id": 100, "method": "Network.enable"}))
        
        # Clear any existing events
        self.ws.settimeout(0.1)
        while True:
            try:
                self.ws.recv()
            except:
                break
        self.ws.settimeout(None)
        
        start_time = time.time()
        event_count = 0
        
        while time.time() - start_time < duration:
            try:
                self.ws.settimeout(0.5)
                resp = self.ws.recv()
                data = json.loads(resp)
                event_count += 1
                
                if 'method' in data:
                    if data['method'] == 'Network.requestWillBeSent':
                        request = data['params']['request']
                        self.network_logs.append({
                            'type': 'request',
                            'url': request.get('url', ''),
                            'method': request.get('method', ''),
                            'headers': request.get('headers', {}),
                            'timestamp': time.time() - start_time
                        })
                    elif data['method'] == 'Network.responseReceived':
                        response = data['params']['response']
                        self.network_logs.append({
                            'type': 'response',
                            'url': response.get('url', ''),
                            'status': response.get('status', 0),
                            'statusText': response.get('statusText', ''),
                            'headers': response.get('headers', {}),
                            'timestamp': time.time() - start_time
                        })
            except websocket.WebSocketTimeoutException:
                continue
            except Exception as e:
                if "timed out" not in str(e).lower():
                    pass
                continue
        
        self.ws.settimeout(None)
        console.print(f"[green]✅ Captured {len(self.network_logs)} network events[/green]")
        return self.network_logs

    def js(self, script, await_promise=False):
        """Execute JavaScript and return result"""
        if not self.connected:
            return None

        cmd_id = int(time.time() * 1000) % 100000

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
        except Exception as e:
            console.print(f"[red]Error sending JS: {e}[/red]")
            return None

        timeout = 30
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
                    if 'error' in result:
                        console.print(f"[red]JS Error: {result['error']}[/red]")
                    return None
            except websocket.WebSocketTimeoutException:
                continue
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                return None

        console.print("[yellow]Timeout waiting for JS response[/yellow]")
        return None

    def get_all_text(self):
        """Get all text from the page"""
        script = """
        (function() {
            const texts = [];
            document.querySelectorAll('h1, h2, h3, h4, h5, h6, p, li').forEach(el => {
                const text = el.textContent.trim();
                if (text && text.length > 2) {
                    texts.push({
                        tag: el.tagName.toLowerCase(),
                        text: text.substring(0, 200)
                    });
                }
            });
            return texts;
        })()
        """
        return self.js(script) or []

    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except:
                pass

def display_dom_fingerprint(fingerprint):
    """Display DOM fingerprint"""
    if not fingerprint or not fingerprint.get('tag_counts'):
        console.print("[yellow]No fingerprint data. Try refreshing the page or navigating to a different URL.[/yellow]")
        return

    console.print("\n[bold cyan]🔐 DOM Fingerprint[/bold cyan]")
    console.print(f"  URL: {fingerprint.get('url', 'N/A')}")
    console.print(f"  Title: {fingerprint.get('title', 'N/A')}")
    console.print(f"  Text Hash: {fingerprint.get('text_hash', 'N/A')}")
    
    console.print("\n[bold]Tag Counts:[/bold]")
    tag_counts = fingerprint.get('tag_counts', {})
    for tag, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        console.print(f"  {tag}: {count}")
    
    console.print("\n[bold]Interactive Elements:[/bold]")
    console.print(f"  Forms: {len(fingerprint.get('forms', []))}")
    console.print(f"  Inputs: {len(fingerprint.get('inputs', []))}")
    console.print(f"  Buttons: {len(fingerprint.get('buttons', []))}")
    console.print(f"  Links: {len(fingerprint.get('links', []))}")

def display_actions(actions):
    """Display discovered actions"""
    if not actions:
        console.print("[yellow]No actions discovered[/yellow]")
        return

    console.print(f"\n[bold cyan]🎯 Discovered Actions ({len(actions)})[/bold cyan]")
    
    # Group by action type
    by_type = defaultdict(list)
    for action in actions:
        by_type[action.get('action_type', 'unknown')].append(action)
    
    for action_type, items in by_type.items():
        console.print(f"\n[bold]{action_type.upper()}:[/bold] ({len(items)})")
        for item in items[:5]:
            text = item.get('text', '') or '[no text]'
            console.print(f"  • {text[:40]}")
            if item.get('id'):
                console.print(f"    id: {item['id']}")
            if item.get('target'):
                console.print(f"    target: {item['target'][:50]}")

def display_navigation_graph(graph):
    """Display navigation graph"""
    if not graph or not graph.get('links'):
        console.print("[yellow]No navigation data[/yellow]")
        return

    console.print(f"\n[bold cyan]🗺️ Navigation Graph[/bold cyan]")
    console.print(f"  Current Path: {graph.get('current_path', 'N/A')}")
    console.print(f"  Base URL: {graph.get('base_url', 'N/A')}")
    
    links = graph.get('links', [])
    console.print(f"\n[bold]Links:[/bold] ({len(links)})")
    
    # Group by path prefix
    by_prefix = defaultdict(list)
    for link in links:
        path = link.get('path', '')
        prefix = path.split('/')[1] if path.startswith('/') and len(path.split('/')) > 1 else 'root'
        by_prefix[prefix].append(link)
    
    for prefix, items in sorted(by_prefix.items()):
        console.print(f"\n  /{prefix}/ ({len(items)})")
        for item in items[:3]:
            text = item.get('text', '') or '[no text]'
            console.print(f"    • {text[:30]} → {item.get('path', '')}")

def display_network_logs(logs):
    """Display captured network logs"""
    if not logs:
        console.print("[yellow]No network logs captured[/yellow]")
        return

    console.print(f"\n[bold cyan]🌐 Network Traffic ({len(logs)})[/bold cyan]")
    
    requests = [l for l in logs if l.get('type') == 'request']
    responses = [l for l in logs if l.get('type') == 'response']
    
    console.print(f"  Requests: {len(requests)}")
    console.print(f"  Responses: {len(responses)}")
    
    if requests:
        console.print("\n[bold]Request URLs:[/bold]")
        for req in requests[:10]:
            console.print(f"  {req.get('method', '')} {req.get('url', '')[:80]}")
    
    if responses:
        console.print("\n[bold]Response Status:[/bold]")
        for resp in responses[:10]:
            status = resp.get('status', 0)
            color = "green" if 200 <= status < 300 else "yellow" if 300 <= status < 400 else "red"
            console.print(f"  [{color}]{status}[/{color}] {resp.get('url', '')[:80]}")

def display_dom_snapshot(snapshot):
    """Display DOM snapshot summary"""
    if not snapshot or not snapshot.get('elements'):
        console.print("[yellow]No snapshot data[/yellow]")
        return

    console.print(f"\n[bold cyan]📸 DOM Snapshot[/bold cyan]")
    console.print(f"  Timestamp: {datetime.fromtimestamp(snapshot.get('timestamp', 0)/1000).strftime('%Y-%m-%d %H:%M:%S')}")
    console.print(f"  URL: {snapshot.get('url', 'N/A')}")
    console.print(f"  Title: {snapshot.get('title', 'N/A')}")
    console.print(f"  Body Hash: {snapshot.get('body_hash', 'N/A')}")
    
    important = snapshot.get('elements', {}).get('important', {})
    
    console.print("\n[bold]Content Structure:[/bold]")
    console.print(f"  Headers: {len(important.get('headers', []))}")
    console.print(f"  Paragraphs: {len(important.get('paragraphs', []))}")
    console.print(f"  Lists: {len(important.get('lists', []))}")
    console.print(f"  Tables: {len(important.get('tables', []))}")
    console.print(f"  Forms: {len(important.get('forms', []))}")

def display_page_text(texts):
    """Display page text"""
    if not texts:
        console.print("[yellow]No text content found[/yellow]")
        return
    
    console.print(f"\n[bold cyan]📄 Page Text ({len(texts)} elements)[/bold cyan]\n")
    for item in texts[:30]:
        tag = item.get('tag', '')
        text = item.get('text', '')
        if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            console.print(f"[bold]{text}[/bold]")
        else:
            console.print(f"  {text}")

def main():
    console.clear()
    console.print(Panel("[bold cyan]🕷️ Web Intelligence Agent[/bold cyan]", border_style="green"))
    console.print("[dim]CDP + HAR + DOM Fingerprinting[/dim]")

    port = int(Prompt.ask("Port", default="9257"))
    agent = WebIntelligenceAgent(port)

    if not agent.connect():
        return

    while True:
        console.print()
        console.print(Panel(f"[bold]Current Page: {agent.page_title or 'Unknown'}[/bold]", border_style="blue"))

        console.print("[cyan]📌 Options:[/cyan]")
        console.print("  1. DOM Fingerprint")
        console.print("  2. Discover Actions")
        console.print("  3. Navigation Graph")
        console.print("  4. 📸 DOM Snapshot")
        console.print("  5. 🌐 Capture Network Traffic (HAR)")
        console.print("  6. Show All Page Text")
        console.print("  7. Execute Custom JS")
        console.print("  8. Navigate to URL")
        console.print("  9. Refresh Page")
        console.print(" 10. Advanced Analysis (All in One)")
        console.print("  0. Exit")

        choice = Prompt.ask("Select", choices=["0","1","2","3","4","5","6","7","8","9","10"])

        if choice == "0":
            break

        elif choice == "1":
            display_dom_fingerprint(agent.dom_fingerprint)

        elif choice == "2":
            agent.actions = agent._discover_actions()
            display_actions(agent.actions)

        elif choice == "3":
            agent.navigation_graph = agent._build_navigation_graph()
            display_navigation_graph(agent.navigation_graph)

        elif choice == "4":
            agent.dom_snapshot = agent._take_dom_snapshot()
            display_dom_snapshot(agent.dom_snapshot)

        elif choice == "5":
            duration = int(Prompt.ask("Capture duration (seconds)", default="10"))
            logs = agent.capture_network(duration)
            display_network_logs(logs)
            # Save HAR
            if logs and Confirm.ask("Save HAR file?"):
                filename = f"har_{int(time.time())}.json"
                with open(filename, 'w') as f:
                    json.dump(logs, f, indent=2)
                console.print(f"[green]✅ Saved to {filename}[/green]")

        elif choice == "6":
            texts = agent.get_all_text()
            display_page_text(texts)

        elif choice == "7":
            script = Prompt.ask("JavaScript code")
            result = agent.js(script)
            if result is not None:
                console.print(Panel(str(result)[:2000], title="Result", border_style="green"))
            else:
                console.print("[yellow]No result or error[/yellow]")

        elif choice == "8":
            url = Prompt.ask("URL")
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"
            agent.js(f"window.location.href = '{url}'")
            console.print(f"[yellow]⏳ Navigating to {url}...[/yellow]")
            time.sleep(3)
            console.print("[green]✅ Navigated![/green]")
            agent.page_title = agent.js("document.title") or "Unknown"
            agent.page_url = agent.js("window.location.href") or url
            agent._analyze_page()

        elif choice == "9":
            agent.js("location.reload()")
            console.print("[yellow]⏳ Page reloading...[/yellow]")
            time.sleep(2)
            console.print("[green]✅ Refreshed![/green]")
            agent._analyze_page()

        elif choice == "10":
            console.print("\n[bold cyan]🔍 Advanced Analysis[/bold cyan]")
            console.print("[yellow]Analyzing page...[/yellow]")
            
            # Re-analyze everything
            agent._analyze_page()
            
            console.print("\n[bold green]📊 Page Intelligence Summary:[/bold green]")
            console.print(f"  • URL: {agent.page_url}")
            console.print(f"  • DOM Fingerprint: {len(agent.dom_fingerprint.get('tag_counts', {}))} tags")
            console.print(f"  • Actions: {len(agent.actions)}")
            console.print(f"  • Navigation Paths: {len(agent.navigation_graph.get('links', []))}")
            console.print(f"  • DOM Hash: {agent.dom_snapshot.get('body_hash', 'N/A')}")
            
            # Show top 5 action types
            action_types = defaultdict(int)
            for action in agent.actions:
                action_types[action.get('action_type', 'unknown')] += 1
            
            console.print("\n[bold]Top Actions:[/bold]")
            for action_type, count in sorted(action_types.items(), key=lambda x: x[1], reverse=True)[:5]:
                console.print(f"  • {action_type}: {count}")

        if choice != "0":
            console.print()
            input("Press Enter to continue...")

    agent.close()
    console.print("[green]Goodbye! 👋[/green]")

if __name__ == "__main__":
    main()
