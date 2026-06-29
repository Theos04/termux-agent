#!/usr/bin/env python3
"""
Chrome Page Tool - Debug Version
"""

import json
import time
import requests
import websocket
import re
import sys
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt

console = Console()

class Page:
    def __init__(self, port):
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.ws = None
        self.connected = False
        self.debug = True
    
    def log(self, msg):
        if self.debug:
            console.print(f"[dim]{msg}[/dim]")
    
    def connect(self):
        try:
            # Get tabs
            self.log("Getting tabs...")
            r = requests.get(f"{self.base_url}/json", timeout=5)
            if r.status_code != 200:
                console.print("[red]❌ Chrome not responding[/red]")
                return False
            
            tabs = r.json()
            self.log(f"Found {len(tabs)} tabs")
            
            pages = [t for t in tabs if t.get('type') == 'page']
            if not pages:
                console.print("[red]❌ No tabs[/red]")
                return False
            
            # Use first tab
            ws_url = pages[0].get('webSocketDebuggerUrl')
            if not ws_url:
                console.print("[red]❌ No WebSocket URL[/red]")
                return False
            
            self.log(f"WS URL: {ws_url}")
            
            # Connect with proper timeout
            self.ws = websocket.create_connection(ws_url, timeout=10)
            self.log("WebSocket connected")
            
            # Enable Runtime
            self.log("Enabling Runtime...")
            self.ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
            response = self.ws.recv()
            self.log(f"Runtime enable response: {response[:100]}")
            
            self.connected = True
            console.print(f"[green]✅ Connected to: {pages[0].get('title', 'Untitled')}[/green]")
            return True
            
        except Exception as e:
            console.print(f"[red]❌ Error: {e}[/red]")
            import traceback
            traceback.print_exc()
            return False
    
    def js(self, script):
        """Execute JavaScript and return result"""
        if not self.connected:
            console.print("[red]Not connected[/red]")
            return None
        
        try:
            msg_id = int(time.time() * 1000)
            cmd = {
                "id": msg_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": script,
                    "returnByValue": True,
                    "awaitPromise": True
                }
            }
            
            self.log(f"Sending: {script[:50]}...")
            self.ws.send(json.dumps(cmd))
            
            # Wait for response with timeout
            self.ws.settimeout(10)
            response = self.ws.recv()
            self.log(f"Response: {response[:100]}...")
            
            result = json.loads(response)
            
            if 'error' in result:
                console.print(f"[red]Script error: {result['error']}[/red]")
                return None
            
            return result.get('result', {})
            
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return None
    
    def text(self):
        """Get page text"""
        r = self.js("document.body ? document.body.innerText : 'No body'")
        return r.get('value') if r else None
    
    def title(self):
        """Get page title"""
        r = self.js("document.title || 'No title'")
        return r.get('value') if r else None
    
    def find(self, selector):
        """Find elements by CSS selector"""
        script = f"""
        (function() {{
            try {{
                const el = document.querySelectorAll('{selector}');
                if (el.length === 0) return [];
                return Array.from(el).map(e => ({{
                    tag: e.tagName,
                    text: e.textContent ? e.textContent.trim().slice(0, 100) : '',
                    id: e.id || '',
                    class: e.className || '',
                    href: e.href || '',
                    value: e.value || '',
                    type: e.type || '',
                    name: e.name || '',
                    visible: e.offsetParent !== null
                }}));
            }} catch(e) {{
                return {{error: e.message}};
            }}
        }})()
        """
        r = self.js(script)
        if r:
            val = r.get('value')
            if isinstance(val, dict) and 'error' in val:
                console.print(f"[red]Error: {val['error']}[/red]")
                return []
            return val if isinstance(val, list) else []
        return []
    
    def click(self, selector):
        """Click an element"""
        script = f"""
        (function() {{
            try {{
                const el = document.querySelector('{selector}');
                if (el) {{
                    el.click();
                    return true;
                }}
                return false;
            }} catch(e) {{
                return {{error: e.message}};
            }}
        }})()
        """
        r = self.js(script)
        if r:
            val = r.get('value')
            if isinstance(val, dict) and 'error' in val:
                console.print(f"[red]Error: {val['error']}[/red]")
                return False
            return val if isinstance(val, bool) else False
        return False
    
    def fill(self, selector, value):
        """Fill an input"""
        escaped = value.replace("'", "\\'").replace('"', '\\"')
        script = f"""
        (function() {{
            try {{
                const el = document.querySelector('{selector}');
                if (el) {{
                    el.value = '{escaped}';
                    el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return true;
                }}
                return false;
            }} catch(e) {{
                return {{error: e.message}};
            }}
        }})()
        """
        r = self.js(script)
        if r:
            val = r.get('value')
            if isinstance(val, dict) and 'error' in val:
                console.print(f"[red]Error: {val['error']}[/red]")
                return False
            return val if isinstance(val, bool) else False
        return False
    
    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except:
                pass

def main():
    console.clear()
    console.print(Panel("[bold cyan]🌐 Chrome Page Tool[/bold cyan]", border_style="green"))
    
    port = Prompt.ask("Port", default="9236")
    page = Page(int(port))
    
    if not page.connect():
        return
    
    # Test connection
    console.print("[dim]Testing connection...[/dim]")
    title = page.title()
    console.print(f"[dim]Page title: {title}[/dim]")
    
    # Test text
    text = page.text()
    if text:
        console.print(f"[dim]Page has text: {len(text)} chars[/dim]")
    else:
        console.print("[yellow]⚠️ No text returned - page might be loading[/yellow]")
    
    while True:
        console.print()
        console.print("[cyan]Options:[/cyan]")
        console.print("  [1] Show page text")
        console.print("  [2] Show page title")
        console.print("  [3] Find elements by selector")
        console.print("  [4] Show all inputs")
        console.print("  [5] Show all buttons")
        console.print("  [6] Show all links")
        console.print("  [7] Click element")
        console.print("  [8] Fill input")
        console.print("  [9] Execute custom JS")
        console.print("  [d] Debug - show page info")
        console.print("  [0] Exit")
        
        choice = Prompt.ask("Select", choices=["0","1","2","3","4","5","6","7","8","9","d"])
        
        if choice == "0":
            break
        
        elif choice == "d":
            # Debug - show page info
            js = """
            (function() {
                return {
                    url: window.location.href,
                    title: document.title,
                    body_exists: !!document.body,
                    body_text_length: document.body ? document.body.innerText.length : 0,
                    has_content: document.body ? document.body.innerText.length > 0 : false,
                    all_children: document.body ? document.body.children.length : 0
                };
            })()
            """
            r = page.js(js)
            if r:
                console.print(Panel(json.dumps(r, indent=2, default=str), title="Debug Info"))
            else:
                console.print("[red]No debug info[/red]")
        
        elif choice == "1":
            text = page.text()
            if text:
                console.print(Panel(text[:2000] + ("..." if len(text) > 2000 else ""), title="Page Text", border_style="blue"))
            else:
                console.print("[yellow]No text content found[/yellow]")
                console.print("[dim]Try option 'd' to debug[/dim]")
        
        elif choice == "2":
            title = page.title()
            console.print(f"[bold]Title:[/bold] {title}")
        
        elif choice == "3":
            sel = Prompt.ask("CSS selector")
            results = page.find(sel)
            if results:
                console.print(f"[green]Found {len(results)} elements:[/green]")
                for i, el in enumerate(results[:20], 1):
                    console.print(f"  {i}. {el.get('tag', '')} - {el.get('text', '')[:40]}")
                    if el.get('href'):
                        console.print(f"     href: {el.get('href')[:50]}")
                if len(results) > 20:
                    console.print(f"[dim]... and {len(results)-20} more[/dim]")
            else:
                console.print("[yellow]No elements found[/yellow]")
        
        elif choice == "4":
            results = page.find('input, textarea, select')
            if results:
                table = Table(title="Inputs")
                table.add_column("#", style="cyan")
                table.add_column("Type")
                table.add_column("Name")
                table.add_column("Value")
                for i, el in enumerate(results[:20], 1):
                    table.add_row(str(i), el.get('type', ''), el.get('name', ''), el.get('value', '')[:20])
                console.print(table)
            else:
                console.print("[yellow]No inputs found[/yellow]")
        
        elif choice == "5":
            results = page.find('button, input[type="submit"], input[type="button"]')
            if results:
                table = Table(title="Buttons")
                table.add_column("#", style="cyan")
                table.add_column("Text")
                for i, el in enumerate(results[:20], 1):
                    table.add_row(str(i), el.get('text', '')[:30])
                console.print(table)
            else:
                console.print("[yellow]No buttons found[/yellow]")
        
        elif choice == "6":
            results = page.find('a[href]')
            if results:
                table = Table(title="Links")
                table.add_column("#", style="cyan")
                table.add_column("Text")
                table.add_column("Href")
                for i, el in enumerate(results[:20], 1):
                    table.add_row(str(i), el.get('text', '')[:20], el.get('href', '')[:40])
                console.print(table)
            else:
                console.print("[yellow]No links found[/yellow]")
        
        elif choice == "7":
            sel = Prompt.ask("CSS selector to click")
            if page.click(sel):
                console.print("[green]✅ Clicked![/green]")
                time.sleep(1)
            else:
                console.print("[red]❌ Not found or error[/red]")
        
        elif choice == "8":
            sel = Prompt.ask("CSS selector")
            val = Prompt.ask("Value")
            if page.fill(sel, val):
                console.print("[green]✅ Filled![/green]")
            else:
                console.print("[red]❌ Not found or error[/red]")
        
        elif choice == "9":
            script = Prompt.ask("JavaScript code")
            result = page.js(script)
            if result:
                console.print(Panel(json.dumps(result, indent=2, default=str), title="Result", border_style="green"))
            else:
                console.print("[yellow]No result or error[/yellow]")
        
        if choice != "0":
            input("\nPress Enter to continue...")
    
    page.close()
    console.print("[green]Goodbye! 👋[/green]")

if __name__ == "__main__":
    main()
