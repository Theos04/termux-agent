#!/usr/bin/env python3
"""
Simple Chrome Interaction Tool
Pull content, find elements, interact with pages
"""

import json
import time
import requests
import websocket
import re
from typing import Optional, Dict, List, Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

console = Console()

class ChromePage:
    """Simple Chrome page interaction"""
    
    def __init__(self, port: int = 9236):
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.ws = None
        self.tab_id = None
        self.connected = False
        
    def connect(self) -> bool:
        """Connect to Chrome"""
        try:
            # Get tabs
            response = requests.get(f"{self.base_url}/json", timeout=5)
            if response.status_code != 200:
                console.print("[red]❌ Cannot connect to Chrome[/red]")
                return False
            
            tabs = response.json()
            pages = [t for t in tabs if t.get('type') == 'page']
            if not pages:
                console.print("[red]❌ No tabs found[/red]")
                return False
            
            # Use first tab
            tab = pages[0]
            self.tab_id = tab.get('id')
            ws_url = tab.get('webSocketDebuggerUrl')
            
            if not ws_url:
                console.print("[red]❌ No WebSocket URL[/red]")
                return False
            
            # Connect WebSocket
            self.ws = websocket.create_connection(ws_url, timeout=10)
            
            # Enable Runtime
            self.ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
            response = self.ws.recv()
            
            self.connected = True
            console.print(f"[green]✅ Connected to: {tab.get('title', 'Untitled')}[/green]")
            return True
            
        except Exception as e:
            console.print(f"[red]❌ Connection failed: {e}[/red]")
            return False
    
    def execute_js(self, script: str, await_promise: bool = True) -> Optional[Dict]:
        """Execute JavaScript and return result"""
        if not self.connected:
            console.print("[red]❌ Not connected[/red]")
            return None
        
        try:
            msg_id = int(time.time() * 1000)
            cmd = {
                "id": msg_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": script,
                    "returnByValue": True,
                    "awaitPromise": await_promise
                }
            }
            
            self.ws.send(json.dumps(cmd))
            response = self.ws.recv()
            result = json.loads(response)
            
            if 'error' in result:
                console.print(f"[red]❌ Script error: {result['error']}[/red]")
                return None
            
            return result.get('result', {})
            
        except Exception as e:
            console.print(f"[red]❌ Execution failed: {e}[/red]")
            return None
    
    def get_page_content(self) -> Optional[str]:
        """Get full page HTML"""
        result = self.execute_js("document.documentElement.outerHTML")
        return result.get('value') if result else None
    
    def get_page_text(self) -> Optional[str]:
        """Get visible text content"""
        result = self.execute_js("document.body.innerText")
        return result.get('value') if result else None
    
    def get_page_title(self) -> Optional[str]:
        """Get page title"""
        result = self.execute_js("document.title")
        return result.get('value') if result else None
    
    def get_elements(self, selector: str) -> List[Dict]:
        """Get elements matching selector with their properties"""
        script = f"""
        (function() {{
            const elements = document.querySelectorAll('{selector}');
            return Array.from(elements).map(el => ({{
                tag: el.tagName,
                id: el.id || '',
                classes: el.className || '',
                text: el.textContent ? el.textContent.trim().slice(0, 200) : '',
                href: el.href || '',
                src: el.src || '',
                value: el.value || '',
                type: el.type || '',
                name: el.name || '',
                placeholder: el.placeholder || '',
                innerHTML: el.innerHTML ? el.innerHTML.slice(0, 500) : '',
                visible: el.offsetParent !== null
            }}));
        }})()
        """
        result = self.execute_js(script)
        return result.get('value', []) if result else []
    
    def find_inputs(self) -> List[Dict]:
        """Find all input fields"""
        return self.get_elements('input, textarea, select')
    
    def find_buttons(self) -> List[Dict]:
        """Find all buttons"""
        return self.get_elements('button, input[type="submit"], input[type="button"], a[role="button"]')
    
    def find_links(self) -> List[Dict]:
        """Find all links"""
        return self.get_elements('a[href]')
    
    def find_images(self) -> List[Dict]:
        """Find all images"""
        return self.get_elements('img[src]')
    
    def find_forms(self) -> List[Dict]:
        """Find all forms"""
        script = """
        (function() {
            const forms = document.querySelectorAll('form');
            return Array.from(forms).map(form => ({
                id: form.id || '',
                action: form.action || '',
                method: form.method || '',
                inputs: Array.from(form.querySelectorAll('input, textarea, select')).map(el => ({
                    name: el.name || '',
                    type: el.type || '',
                    value: el.value || '',
                    placeholder: el.placeholder || ''
                }))
            }));
        })()
        """
        result = self.execute_js(script)
        return result.get('value', []) if result else []
    
    def click(self, selector: str) -> bool:
        """Click an element"""
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
        result = self.execute_js(script)
        return result.get('value') if result else False
    
    def fill(self, selector: str, value: str) -> bool:
        """Fill an input field"""
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
        result = self.execute_js(script)
        return result.get('value') if result else False
    
    def wait_for_element(self, selector: str, timeout: int = 30) -> bool:
        """Wait for an element to appear"""
        script = f"""
        (function() {{
            return new Promise((resolve) => {{
                const check = () => {{
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        resolve(true);
                    }} else {{
                        setTimeout(check, 200);
                    }}
                }};
                check();
            }});
        }})()
        """
        result = self.execute_js(script)
        return result.get('value') if result else False
    
    def get_element_text(self, selector: str) -> Optional[str]:
        """Get text from an element"""
        script = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            return el ? el.textContent.trim() : null;
        }})()
        """
        result = self.execute_js(script)
        return result.get('value') if result else None
    
    def get_all_links(self) -> List[str]:
        """Get all links as URLs"""
        script = """
        (function() {
            return Array.from(document.querySelectorAll('a[href]'))
                .map(a => a.href)
                .filter(href => href && href.startsWith('http'));
        })()
        """
        result = self.execute_js(script)
        return result.get('value', []) if result else []
    
    def get_cookies(self) -> List[Dict]:
        """Get all cookies"""
        script = """
        (function() {
            return document.cookie.split(';').map(c => {
                const [name, value] = c.trim().split('=');
                return {name, value};
            });
        })()
        """
        result = self.execute_js(script)
        return result.get('value', []) if result else []
    
    def scroll_to(self, selector: str) -> bool:
        """Scroll to an element"""
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
        result = self.execute_js(script)
        return result.get('value') if result else False
    
    def close(self):
        """Close connection"""
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
            self.ws = None
            self.connected = False

def main():
    """Interactive CLI"""
    port = int(Prompt.ask("🔌 Port", default="9236"))
    page = ChromePage(port)
    
    if not page.connect():
        return
    
    console.print()
    console.print(Panel("[bold cyan]🎯 Page Content Explorer[/bold cyan]", border_style="green"))
    
    # Show page info
    title = page.get_page_title()
    console.print(f"[bold]Title:[/bold] {title}")
    
    while True:
        console.print()
        console.print("[cyan]📌 Options:[/cyan]")
        console.print("  [1] Show page text")
        console.print("  [2] Find elements by selector")
        console.print("  [3] Show all inputs")
        console.print("  [4] Show all buttons")
        console.print("  [5] Show all links")
        console.print("  [6] Show all images")
        console.print("  [7] Show forms")
        console.print("  [8] Click element")
        console.print("  [9] Fill input")
        console.print("  [10] Get all links (URLs)")
        console.print("  [11] Get cookies")
        console.print("  [12] Show page structure")
        console.print("  [13] Wait for element")
        console.print("  [0] Exit")
        
        choice = Prompt.ask("Select", choices=["0","1","2","3","4","5","6","7","8","9","10","11","12","13"])
        
        if choice == "0":
            break
        
        elif choice == "1":  # Show page text
            text = page.get_page_text()
            if text:
                console.print(Panel(text[:2000] + ("..." if len(text) > 2000 else ""), 
                                   title="Page Text", border_style="blue"))
        
        elif choice == "2":  # Find elements
            selector = Prompt.ask("CSS selector")
            elements = page.get_elements(selector)
            if elements:
                console.print(f"[green]Found {len(elements)} elements:[/green]")
                for i, el in enumerate(elements[:20], 1):
                    console.print(f"  [{i}] {el.get('tag')} - {el.get('text', '')[:50]}")
                    if el.get('href'):
                        console.print(f"       href: {el.get('href')[:50]}")
                    if el.get('src'):
                        console.print(f"       src: {el.get('src')[:50]}")
                if len(elements) > 20:
                    console.print(f"[dim]... and {len(elements)-20} more[/dim]")
            else:
                console.print("[yellow]No elements found[/yellow]")
        
        elif choice == "3":  # Show inputs
            inputs = page.find_inputs()
            if inputs:
                table = Table(title="Input Fields")
                table.add_column("#", style="cyan", width=4)
                table.add_column("Type", style="yellow")
                table.add_column("Name", style="green")
                table.add_column("Placeholder", style="blue")
                table.add_column("Value", style="white")
                
                for i, inp in enumerate(inputs[:20], 1):
                    table.add_row(
                        str(i),
                        inp.get('type', 'text'),
                        inp.get('name', ''),
                        inp.get('placeholder', ''),
                        inp.get('value', '')[:30]
                    )
                console.print(table)
                if len(inputs) > 20:
                    console.print(f"[dim]... and {len(inputs)-20} more[/dim]")
            else:
                console.print("[yellow]No inputs found[/yellow]")
        
        elif choice == "4":  # Show buttons
            buttons = page.find_buttons()
            if buttons:
                table = Table(title="Buttons")
                table.add_column("#", style="cyan", width=4)
                table.add_column("Text", style="green")
                table.add_column("Type", style="yellow")
                
                for i, btn in enumerate(buttons[:20], 1):
                    table.add_row(
                        str(i),
                        btn.get('text', '')[:30],
                        btn.get('type', 'button')
                    )
                console.print(table)
                if len(buttons) > 20:
                    console.print(f"[dim]... and {len(buttons)-20} more[/dim]")
            else:
                console.print("[yellow]No buttons found[/yellow]")
        
        elif choice == "5":  # Show links
            links = page.find_links()
            if links:
                table = Table(title="Links")
                table.add_column("#", style="cyan", width=4)
                table.add_column("Text", style="green")
                table.add_column("HREF", style="blue")
                
                for i, link in enumerate(links[:20], 1):
                    table.add_row(
                        str(i),
                        link.get('text', '')[:30],
                        link.get('href', '')[:40]
                    )
                console.print(table)
                if len(links) > 20:
                    console.print(f"[dim]... and {len(links)-20} more[/dim]")
            else:
                console.print("[yellow]No links found[/yellow]")
        
        elif choice == "6":  # Show images
            images = page.find_images()
            if images:
                table = Table(title="Images")
                table.add_column("#", style="cyan", width=4)
                table.add_column("Alt Text", style="green")
                table.add_column("Source", style="blue")
                
                for i, img in enumerate(images[:20], 1):
                    table.add_row(
                        str(i),
                        img.get('text', '')[:30],
                        img.get('src', '')[:40]
                    )
                console.print(table)
                if len(images) > 20:
                    console.print(f"[dim]... and {len(images)-20} more[/dim]")
            else:
                console.print("[yellow]No images found[/yellow]")
        
        elif choice == "7":  # Show forms
            forms = page.find_forms()
            if forms:
                for i, form in enumerate(forms, 1):
                    console.print(f"[bold]Form {i}:[/bold]")
                    console.print(f"  Action: {form.get('action', '')}")
                    console.print(f"  Method: {form.get('method', 'GET')}")
                    console.print("  Inputs:")
                    for inp in form.get('inputs', []):
                        console.print(f"    - {inp.get('name', '')} ({inp.get('type', 'text')})")
            else:
                console.print("[yellow]No forms found[/yellow]")
        
        elif choice == "8":  # Click element
            selector = Prompt.ask("CSS selector to click")
            if page.click(selector):
                console.print("[green]✅ Clicked![/green]")
                time.sleep(0.5)
                # Show new page title
                new_title = page.get_page_title()
                console.print(f"[dim]New title: {new_title}[/dim]")
            else:
                console.print("[red]❌ Element not found[/red]")
        
        elif choice == "9":  # Fill input
            selector = Prompt.ask("CSS selector for input")
            value = Prompt.ask("Value to fill")
            if page.fill(selector, value):
                console.print("[green]✅ Filled![/green]")
            else:
                console.print("[red]❌ Element not found[/red]")
        
        elif choice == "10":  # Get all links
            links = page.get_all_links()
            if links:
                console.print(f"[green]Found {len(links)} links:[/green]")
                for i, link in enumerate(links[:20], 1):
                    console.print(f"  [{i}] {link[:80]}")
                if len(links) > 20:
                    console.print(f"[dim]... and {len(links)-20} more[/dim]")
            else:
                console.print("[yellow]No links found[/yellow]")
        
        elif choice == "11":  # Get cookies
            cookies = page.get_cookies()
            if cookies:
                table = Table(title="Cookies")
                table.add_column("Name", style="green")
                table.add_column("Value", style="blue")
                
                for cookie in cookies:
                    table.add_row(
                        cookie.get('name', ''),
                        cookie.get('value', '')[:50]
                    )
                console.print(table)
            else:
                console.print("[yellow]No cookies found[/yellow]")
        
        elif choice == "12":  # Page structure
            # Get all elements with their hierarchy
            script = """
            (function() {
                function getStructure(el, depth) {
                    const indent = '  '.repeat(depth);
                    let result = indent + '<' + el.tagName.toLowerCase();
                    if (el.id) result += ' id="' + el.id + '"';
                    if (el.className) result += ' class="' + el.className + '"';
                    result += '>';
                    if (el.children.length === 0 && el.textContent) {
                        result += ' ' + el.textContent.trim().slice(0, 50);
                    }
                    result += '\\n';
                    for (const child of el.children) {
                        result += getStructure(child, depth + 1);
                    }
                    return result;
                }
                return getStructure(document.body, 0);
            })()
            """
            result = page.execute_js(script)
            if result:
                structure = result.get('value', '')
                if structure:
                    console.print(Panel(structure[:2000] + ("..." if len(structure) > 2000 else ""),
                                       title="Page Structure", border_style="cyan"))
                else:
                    console.print("[yellow]No structure data[/yellow]")
        
        elif choice == "13":  # Wait for element
            selector = Prompt.ask("CSS selector to wait for")
            timeout = int(Prompt.ask("Timeout (seconds)", default="30"))
            if page.wait_for_element(selector, timeout):
                console.print(f"[green]✅ Element appeared![/green]")
            else:
                console.print("[red]❌ Element not found within timeout[/red]")
        
        if choice != "0":
            console.print()
            Prompt.ask("Press Enter to continue...")

if __name__ == "__main__":
    main()
