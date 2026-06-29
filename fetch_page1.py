#!/usr/bin/env python3
"""
Chrome Page Tool - Complete Interactive Version
"""

import json
import websocket
import requests
import sys
import time
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import box
from rich.text import Text

console = Console()

class ChromePage:
    def __init__(self, port=9236):
        self.port = port
        self.ws = None
        self.connected = False
        self.page_title = ""
        self.page_url = ""
    
    def connect(self):
        """Connect to Chrome DevTools"""
        try:
            resp = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=5)
            tabs = resp.json()
            
            # Find page tab
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
            
            # Enable Runtime
            self.ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
            while True:
                resp = self.ws.recv()
                data = json.loads(resp)
                if data.get('id') == 1:
                    break
            
            self.connected = True
            console.print(f"[green]✅ Connected to: {self.page_title}[/green]")
            console.print(f"[dim]   URL: {self.page_url}[/dim]")
            return True
            
        except Exception as e:
            console.print(f"[red]Connection failed: {e}[/red]")
            return False
    
    def js(self, script, await_promise=False):
        """Execute JavaScript and return result"""
        if not self.connected:
            return None
        
        import time
        cmd_id = int(time.time() * 1000) % 100000
        
        self.ws.send(json.dumps({
            "id": cmd_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": script,
                "returnByValue": True,
                "awaitPromise": await_promise
            }
        }))
        
        # Wait for response with matching ID
        timeout = 30
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = self.ws.recv()
                data = json.loads(resp)
                if data.get('id') == cmd_id:
                    result = data.get('result', {})
                    if 'result' in result:
                        return result['result'].get('value')
                    elif 'error' in result:
                        console.print(f"[red]Error: {result['error']}[/red]")
                        return None
                    return None
            except Exception as e:
                console.print(f"[red]WS read error: {e}[/red]")
                return None
        
        console.print("[yellow]Timeout waiting for response[/yellow]")
        return None
    
    def get_title(self):
        return self.js("document.title") or "No title"
    
    def get_text(self):
        return self.js("document.body ? document.body.innerText : ''") or ""
    
    def get_html(self):
        return self.js("document.documentElement.outerHTML") or ""
    
    def get_page_info(self):
        script = """
        (function() {
            return {
                url: window.location.href,
                title: document.title,
                links: document.querySelectorAll('a[href]').length,
                images: document.querySelectorAll('img').length,
                inputs: document.querySelectorAll('input, textarea, select').length,
                buttons: document.querySelectorAll('button, input[type="submit"]').length,
                forms: document.querySelectorAll('form').length,
                text_length: document.body ? document.body.innerText.length : 0,
                html_length: document.documentElement.outerHTML.length
            };
        })()
        """
        return self.js(script) or {}
    
    def find_elements(self, selector):
        script = f"""
        (function() {{
            const els = document.querySelectorAll('{selector}');
            return Array.from(els).map(el => ({{
                tag: el.tagName.toLowerCase(),
                text: (el.textContent || '').trim().slice(0, 100),
                id: el.id || '',
                class: el.className || '',
                href: el.href || '',
                src: el.src || '',
                value: el.value || '',
                type: el.type || '',
                name: el.name || '',
                placeholder: el.placeholder || '',
                visible: el.offsetParent !== null
            }}));
        }})()
        """
        return self.js(script) or []
    
    def click(self, selector):
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
        return self.js(script) or False
    
    def fill(self, selector, value):
        escaped = value.replace("'", "\\'")
        script = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (el) {{
                el.value = '{escaped}';
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                return true;
            }}
            return false;
        }})()
        """
        return self.js(script) or False
    
    def scroll_to(self, selector):
        script = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (el) {{
                el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                return true;
            }}
            return false;
        }})()
        """
        return self.js(script) or False
    
    def get_cookies(self):
        script = """
        (function() {
            if (!document.cookie) return [];
            return document.cookie.split(';').map(c => {
                const parts = c.trim().split('=');
                return {name: parts[0], value: parts.slice(1).join('=')};
            });
        })()
        """
        return self.js(script) or []
    
    def wait_for_element(self, selector, timeout=30):
        script = f"""
        (function() {{
            return new Promise((resolve) => {{
                const start = Date.now();
                const check = () => {{
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        resolve(true);
                    }} else if (Date.now() - start > {timeout * 1000}) {{
                        resolve(false);
                    }} else {{
                        setTimeout(check, 200);
                    }}
                }};
                check();
            }});
        }})()
        """
        return self.js(script, await_promise=True) or False
    
    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except:
                pass

def display_elements_table(elements, title="Elements"):
    """Display elements in a nice table"""
    if not elements:
        console.print("[yellow]No elements found[/yellow]")
        return
    
    table = Table(title=title, box=box.ROUNDED)
    table.add_column("#", style="cyan", width=4)
    table.add_column("Tag", style="yellow")
    table.add_column("Text / Value", style="green")
    table.add_column("ID / HREF", style="blue")
    
    for i, el in enumerate(elements[:30], 1):
        text = el.get('text', '') or el.get('value', '') or el.get('src', '') or ''
        ident = el.get('id') or el.get('href', '') or ''
        table.add_row(str(i), el.get('tag', ''), text[:40], ident[:40])
    
    console.print(table)
    if len(elements) > 30:
        console.print(f"[dim]... and {len(elements)-30} more[/dim]")

def main():
    console.clear()
    console.print(Panel("[bold cyan]🌐 Chrome Page Tool - Complete[/bold cyan]", border_style="green"))
    
    port = int(Prompt.ask("Port", default="9236"))
    page = ChromePage(port)
    
    if not page.connect():
        return
    
    while True:
        console.print()
        console.print(Panel(f"[bold]Current Page: {page.get_title() or 'Unknown'}[/bold]", border_style="blue"))
        
        console.print("[cyan]📌 Options:[/cyan]")
        console.print("  1. Page Info")
        console.print("  2. Show Page Text")
        console.print("  3. Find Elements")
        console.print("  4. Show All Links")
        console.print("  5. Show All Buttons")
        console.print("  6. Show All Inputs")
        console.print("  7. Show All Images")
        console.print("  8. Show Forms")
        console.print("  9. Show Cookies")
        console.print(" 10. Click Element")
        console.print(" 11. Fill Input")
        console.print(" 12. Scroll to Element")
        console.print(" 13. Wait for Element")
        console.print(" 14. Execute Custom JS")
        console.print(" 15. Refresh Page")
        console.print(" 16. Navigate to URL")
        console.print("  0. Exit")
        
        choice = Prompt.ask("Select", choices=["0","1","2","3","4","5","6","7","8","9","10","11","12","13","14","15","16"])
        
        if choice == "0":
            break
        
        elif choice == "1":  # Page Info
            info = page.get_page_info()
            if info:
                content = ""
                for key, value in info.items():
                    content += f"[bold]{key}:[/bold] {value}\n"
                console.print(Panel(content, title="Page Information", border_style="cyan"))
            else:
                console.print("[yellow]No info available[/yellow]")
        
        elif choice == "2":  # Show Page Text
            text = page.get_text()
            if text:
                console.print(Panel(text[:3000] + ("..." if len(text) > 3000 else ""), 
                                   title="Page Text", border_style="blue"))
            else:
                console.print("[yellow]No text content[/yellow]")
        
        elif choice == "3":  # Find Elements
            selector = Prompt.ask("CSS selector")
            elements = page.find_elements(selector)
            display_elements_table(elements, f"Elements matching '{selector}'")
        
        elif choice == "4":  # Show Links
            elements = page.find_elements('a[href]')
            display_elements_table(elements, f"Links ({len(elements)})")
        
        elif choice == "5":  # Show Buttons
            elements = page.find_elements('button, input[type="submit"], input[type="button"]')
            display_elements_table(elements, f"Buttons ({len(elements)})")
        
        elif choice == "6":  # Show Inputs
            elements = page.find_elements('input, textarea, select')
            display_elements_table(elements, f"Inputs ({len(elements)})")
        
        elif choice == "7":  # Show Images
            elements = page.find_elements('img[src]')
            display_elements_table(elements, f"Images ({len(elements)})")
        
        elif choice == "8":  # Show Forms
            forms = page.find_elements('form')
            if forms:
                console.print(f"[green]Found {len(forms)} forms[/green]")
                for i, form in enumerate(forms[:10], 1):
                    console.print(f"  Form {i}: id={form.get('id', 'N/A')} method={form.get('method', 'GET')}")
            else:
                console.print("[yellow]No forms found[/yellow]")
        
        elif choice == "9":  # Show Cookies
            cookies = page.get_cookies()
            if cookies:
                table = Table(title="Cookies", box=box.ROUNDED)
                table.add_column("Name", style="green")
                table.add_column("Value", style="blue")
                for cookie in cookies[:20]:
                    table.add_row(cookie.get('name', ''), cookie.get('value', '')[:50])
                console.print(table)
                if len(cookies) > 20:
                    console.print(f"[dim]... and {len(cookies)-20} more[/dim]")
            else:
                console.print("[yellow]No cookies found[/yellow]")
        
        elif choice == "10":  # Click Element
            selector = Prompt.ask("CSS selector to click")
            if page.click(selector):
                console.print("[green]✅ Clicked![/green]")
                time.sleep(1)
                console.print(f"[dim]New title: {page.get_title()}[/dim]")
            else:
                console.print("[red]❌ Element not found[/red]")
        
        elif choice == "11":  # Fill Input
            selector = Prompt.ask("CSS selector")
            value = Prompt.ask("Value")
            if page.fill(selector, value):
                console.print("[green]✅ Filled![/green]")
            else:
                console.print("[red]❌ Element not found[/red]")
        
        elif choice == "12":  # Scroll to Element
            selector = Prompt.ask("CSS selector")
            if page.scroll_to(selector):
                console.print("[green]✅ Scrolled to element![/green]")
            else:
                console.print("[red]❌ Element not found[/red]")
        
        elif choice == "13":  # Wait for Element
            selector = Prompt.ask("CSS selector to wait for")
            timeout = int(Prompt.ask("Timeout (seconds)", default="30"))
            if page.wait_for_element(selector, timeout):
                console.print("[green]✅ Element appeared![/green]")
            else:
                console.print("[red]❌ Element not found within timeout[/red]")
        
        elif choice == "14":  # Execute Custom JS
            script = Prompt.ask("JavaScript code")
            result = page.js(script)
            if result is not None:
                console.print(Panel(str(result)[:2000], title="Result", border_style="green"))
            else:
                console.print("[yellow]No result or error[/yellow]")
        
        elif choice == "15":  # Refresh Page
            page.js("location.reload()")
            console.print("[yellow]⏳ Page reloading...[/yellow]")
            time.sleep(2)
            console.print(f"[dim]New title: {page.get_title()}[/dim]")
        
        elif choice == "16":  # Navigate to URL
            url = Prompt.ask("URL")
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"
            page.js(f"window.location.href = '{url}'")
            console.print(f"[yellow]⏳ Navigating to {url}...[/yellow]")
            time.sleep(3)
            console.print(f"[dim]New title: {page.get_title()}[/dim]")
        
        if choice != "0":
            console.print()
            input("Press Enter to continue...")
    
    page.close()
    console.print("[green]Goodbye! 👋[/green]")

if __name__ == "__main__":
    main()
