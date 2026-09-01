#!/usr/bin/env python3
"""
Direct Chrome Download Handler - Specifically for MCA Portal
Uses Chrome DevTools Protocol to interact with React/MUI components
"""

import json
import websocket
import requests
import time
import os
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from urllib.parse import urljoin
import subprocess

console = Console()

class ChromeDownloader:
    def __init__(self, port=9248):
        self.port = port
        self.ws = None
        self.page_url = ""
        
    def connect(self):
        """Connect to Chrome via DevTools Protocol"""
        try:
            # Get list of open tabs
            resp = requests.get(f"http://127.0.0.1:{self.port}/json")
            tabs = resp.json()
            
            # Find the MCA page
            target_tab = None
            for tab in tabs:
                if tab.get('type') == 'page' and 'mca' in tab.get('url', '').lower():
                    target_tab = tab
                    break
            
            if not target_tab:
                # If no MCA tab found, use first page
                for tab in tabs:
                    if tab.get('type') == 'page':
                        target_tab = tab
                        break
            
            if not target_tab:
                console.print("[red]No page found in Chrome![/red]")
                return False
            
            self.page_url = target_tab.get('url', '')
            ws_url = target_tab.get('webSocketDebuggerUrl')
            
            if not ws_url:
                console.print("[red]No WebSocket URL found[/red]")
                return False
            
            # Connect to WebSocket
            self.ws = websocket.create_connection(ws_url, timeout=10)
            
            # Enable Runtime
            self.ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
            self._wait_for_response(1)
            
            # Enable DOM
            self.ws.send(json.dumps({"id": 2, "method": "DOM.enable"}))
            self._wait_for_response(2)
            
            console.print(f"[green]✅ Connected to: {target_tab.get('title', 'Unknown')}[/green]")
            console.print(f"[dim]   {self.page_url}[/dim]")
            return True
            
        except Exception as e:
            console.print(f"[red]Connection failed: {e}[/red]")
            return False
    
    def _wait_for_response(self, cmd_id, timeout=5):
        """Wait for a specific response from Chrome"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = self.ws.recv()
                data = json.loads(resp)
                if data.get('id') == cmd_id:
                    return data
            except:
                pass
        return None
    
    def execute_js(self, script, await_promise=False):
        """Execute JavaScript in the page"""
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
        
        start = time.time()
        while time.time() - start < 30:
            try:
                resp = self.ws.recv()
                data = json.loads(resp)
                if data.get('id') == cmd_id:
                    result = data.get('result', {})
                    if 'result' in result:
                        return result['result'].get('value')
                    if 'exceptionDetails' in result:
                        console.print(f"[red]JS Error: {result['exceptionDetails']}[/red]")
                        return None
                    return None
            except:
                pass
        return None
    
    def find_download_button(self):
        """Specifically find the 'Important New! Online Submission' button"""
        script = """
        (function() {
            // Find all elements that might be the download button
            const results = [];
            
            // Look for text containing "Important New! Online Submission"
            const elements = document.querySelectorAll('*');
            for (let el of elements) {
                const text = el.textContent || '';
                if (text.includes('Important New! Online Submission') || 
                    text.includes('Online Submission') ||
                    (text.includes('Important') && text.includes('New') && text.includes('Submission'))) {
                    
                    // Get the clickable parent
                    let clickable = el;
                    while (clickable && !clickable.click && clickable.parentElement) {
                        clickable = clickable.parentElement;
                    }
                    
                    results.push({
                        tag: clickable.tagName,
                        text: clickable.textContent.trim().substring(0, 100),
                        id: clickable.id || '',
                        className: clickable.className || '',
                        hasOnClick: clickable.hasAttribute('onclick'),
                        hasRole: clickable.getAttribute('role') || '',
                        href: clickable.getAttribute('href') || '',
                        dataset: JSON.stringify(clickable.dataset || {}),
                        // Get all parents for context
                        parents: []
                    });
                    
                    // Get parent chain
                    let parent = clickable.parentElement;
                    let depth = 0;
                    while (parent && depth < 5) {
                        results[results.length - 1].parents.push({
                            tag: parent.tagName,
                            className: parent.className || '',
                            id: parent.id || ''
                        });
                        parent = parent.parentElement;
                        depth++;
                    }
                }
            }
            
            return results;
        })()
        """
        return self.execute_js(script) or []
    
    def find_all_download_triggers(self):
        """Find all potential download triggers on the page"""
        script = """
        (function() {
            const results = [];
            
            // Method 1: Find elements with download icon (SVG path)
            const svgs = document.querySelectorAll('svg');
            for (let svg of svgs) {
                const hasDownloadPath = svg.innerHTML.includes('M5 20h14v-2H5zM19 9h-4V3H9v6H5l7 7z');
                if (hasDownloadPath) {
                    let parent = svg;
                    let depth = 0;
                    while (parent && depth < 10) {
                        if (parent.tagName === 'BUTTON' || parent.tagName === 'A' || 
                            parent.getAttribute('role') === 'button' || parent.getAttribute('role') === 'link') {
                            results.push({
                                type: 'icon-button',
                                tag: parent.tagName,
                                text: parent.textContent.trim().substring(0, 100),
                                id: parent.id || '',
                                className: parent.className || '',
                                href: parent.getAttribute('href') || '',
                                onclick: parent.getAttribute('onclick') || '',
                                dataset: JSON.stringify(parent.dataset || {})
                            });
                            break;
                        }
                        parent = parent.parentElement;
                        depth++;
                    }
                }
            }
            
            // Method 2: Find elements with download in text
            const allElements = document.querySelectorAll('*');
            for (let el of allElements) {
                const text = el.textContent.toLowerCase();
                if ((text.includes('download') || text.includes('submit') || text.includes('view')) &&
                    (text.includes('important') || text.includes('new') || text.includes('online'))) {
                    
                    // Check if it's clickable
                    let clickable = el;
                    while (clickable && !clickable.click && clickable.parentElement) {
                        clickable = clickable.parentElement;
                    }
                    
                    if (clickable.tagName === 'BUTTON' || clickable.tagName === 'A' ||
                        clickable.getAttribute('role') === 'button') {
                        results.push({
                            type: 'text-button',
                            tag: clickable.tagName,
                            text: clickable.textContent.trim().substring(0, 100),
                            id: clickable.id || '',
                            className: clickable.className || '',
                            href: clickable.getAttribute('href') || '',
                            onclick: clickable.getAttribute('onclick') || '',
                            dataset: JSON.stringify(clickable.dataset || {})
                        });
                    }
                }
            }
            
            return results;
        })()
        """
        return self.execute_js(script) or []
    
    def click_element_by_selector(self, selector):
        """Click an element using a CSS selector"""
        script = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (el) {{
                console.log('Found element, clicking...');
                el.click();
                return true;
            }}
            console.log('Element not found: {selector}');
            return false;
        }})()
        """
        return self.execute_js(script)
    
    def click_element_by_text(self, text):
        """Click an element containing specific text"""
        script = f"""
        (function() {{
            const elements = document.querySelectorAll('button, a, [role="button"], [role="link"], div[onclick]');
            for (let el of elements) {{
                const elText = el.textContent || '';
                if (elText.includes('{text}')) {{
                    console.log('Found element with text: ' + elText.substring(0, 50));
                    el.click();
                    return true;
                }}
            }}
            return false;
        }})()
        """
        return self.execute_js(script)
    
    def simulate_click_with_events(self, text):
        """Simulate a click with full event chain"""
        script = f"""
        (function() {{
            const elements = document.querySelectorAll('button, a, [role="button"], [role="link"]');
            for (let el of elements) {{
                const elText = el.textContent || '';
                if (elText.includes('{text}')) {{
                    // Create and dispatch mouse events
                    const rect = el.getBoundingClientRect();
                    const x = rect.left + rect.width / 2;
                    const y = rect.top + rect.height / 2;
                    
                    // Mouse events
                    const events = ['mousedown', 'mouseup', 'click'];
                    for (let eventType of events) {{
                        const event = new MouseEvent(eventType, {{
                            view: window,
                            bubbles: true,
                            cancelable: true,
                            clientX: x,
                            clientY: y
                        }});
                        el.dispatchEvent(event);
                    }}
                    
                    // Also try direct click
                    el.click();
                    return true;
                }}
            }}
            return false;
        }})()
        """
        return self.execute_js(script)
    
    def find_download_urls_in_page(self):
        """Find PDF and document URLs on the page"""
        script = """
        (function() {
            const urls = [];
            const links = document.querySelectorAll('a[href]');
            const fileExtensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'];
            
            for (let link of links) {
                const href = link.getAttribute('href');
                if (href) {
                    const lower = href.toLowerCase();
                    if (fileExtensions.some(ext => lower.includes(ext))) {
                        urls.push({
                            url: href,
                            text: link.textContent.trim().substring(0, 50),
                            download: link.getAttribute('download') || ''
                        });
                    }
                }
            }
            return urls;
        })()
        """
        return self.execute_js(script) or []
    
    def download_file(self, url, filename=None):
        """Download a file using requests"""
        try:
            if not filename:
                filename = url.split('/')[-1]
                if not filename or '.' not in filename:
                    filename = f"download_{int(time.time())}"
            
            # Make sure filename has extension
            if '.' not in filename:
                # Try to get from URL
                if '.' in url.split('/')[-1]:
                    filename = url.split('/')[-1]
                else:
                    filename += '.pdf'  # Default to PDF
            
            console.print(f"[cyan]Downloading: {filename}[/cyan]")
            
            # Use requests with browser headers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/pdf,application/vnd.openxmlformats-officedocument.*,*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': self.page_url
            }
            
            # Handle relative URLs
            if url.startswith('/'):
                # Get base domain from page URL
                from urllib.parse import urlparse
                parsed = urlparse(self.page_url)
                base = f"{parsed.scheme}://{parsed.netloc}"
                url = base + url
            
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            
            if response.status_code == 200:
                with open(filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                console.print(f"[green]✅ Downloaded: {filename}[/green]")
                console.print(f"[dim]   Size: {len(response.content) // 1024} KB[/dim]")
                return True
            else:
                console.print(f"[red]Download failed: HTTP {response.status_code}[/red]")
                return False
                
        except Exception as e:
            console.print(f"[red]Download error: {e}[/red]")
            return False

def show_clickable_elements(downloader):
    """Show all clickable elements that might trigger downloads"""
    console.print("\n[cyan]🔍 Finding download triggers...[/cyan]")
    
    # Find download buttons
    buttons = downloader.find_all_download_triggers()
    
    if not buttons:
        console.print("[yellow]No download triggers found automatically[/yellow]")
        console.print("[dim]Try using text search: 'Important New! Online Submission'[/dim]")
        
        # Search by text
        console.print("\n[cyan]Searching for 'Important New! Online Submission'...[/cyan]")
        results = downloader.find_download_button()
        if results:
            console.print(f"[green]Found {len(results)} potential matches[/green]")
            for i, result in enumerate(results, 1):
                console.print(f"\n{i}. Tag: {result.get('tag', 'Unknown')}")
                console.print(f"   Text: {result.get('text', '')[:50]}")
                console.print(f"   ID: {result.get('id', 'None')}")
                console.print(f"   Class: {result.get('className', 'None')[:50]}")
                console.print(f"   Role: {result.get('hasRole', 'None')}")
                console.print(f"   Parents: {len(result.get('parents', []))} levels")
        else:
            console.print("[yellow]No matches found[/yellow]")
    
    # Show as table
    if buttons:
        table = Table(title="Download Triggers Found", box=box.ROUNDED)
        table.add_column("#", style="dim")
        table.add_column("Type", style="cyan")
        table.add_column("Tag", style="yellow")
        table.add_column("Text", style="white")
        table.add_column("ID/Class", style="dim")
        
        for i, btn in enumerate(buttons, 1):
            table.add_row(
                str(i),
                btn.get('type', 'unknown'),
                btn.get('tag', ''),
                btn.get('text', '')[:30],
                btn.get('id', '') or btn.get('className', '')[:20]
            )
        
        console.print(table)
    
    return buttons

def main():
    console.clear()
    console.print(Panel("[bold green]📥 MCA Portal Download Helper[/bold green]", border_style="green"))
    console.print("[dim]Specifically designed for the MCA CAP Round documents[/dim]")
    console.print()
    
    port = int(Prompt.ask("Chrome DevTools Port", default="9248"))
    
    downloader = ChromeDownloader(port)
    
    if not downloader.connect():
        console.print("[red]Failed to connect to Chrome[/red]")
        console.print("[dim]Make sure Chrome is open with --remote-debugging-port=9248[/dim]")
        return
    
    while True:
        console.print()
        console.print(Panel("[bold]MCA Portal Downloader[/bold]", border_style="blue"))
        
        console.print("[cyan]📌 Options:[/cyan]")
        console.print("  1. 🔍 Find Download Triggers")
        console.print("  2. 🖱️ Click 'Important New! Online Submission'")
        console.print("  3. 📄 Find PDF/Document Links")
        console.print("  4. 🔧 Try Advanced Click (with events)")
        console.print("  5. 📋 Show Page Structure")
        console.print("  6. 💾 Save Page HTML")
        console.print("  7. 🔄 Refresh Page")
        console.print("  0. Exit")
        
        choice = Prompt.ask("Select", choices=["0","1","2","3","4","5","6","7"])
        
        if choice == "0":
            break
        
        elif choice == "1":
            show_clickable_elements(downloader)
        
        elif choice == "2":
            console.print("\n[yellow]Attempting to click 'Important New! Online Submission'...[/yellow]")
            
            # Try multiple methods
            methods = [
                ("By exact text", "Important New! Online Submission"),
                ("By partial text", "Online Submission"),
                ("By partial text", "Important New!"),
                ("By partial text", "New! Online")
            ]
            
            success = False
            for method_name, text in methods:
                console.print(f"[dim]Trying {method_name}...[/dim]")
                result = downloader.click_element_by_text(text)
                if result:
                    console.print(f"[green]✅ Clicked! ({method_name})[/green]")
                    success = True
                    break
            
            if not success:
                console.print("[yellow]Could not click automatically[/yellow]")
                console.print("[cyan]Please click the 'Important New! Online Submission' button manually in your browser[/cyan]")
                console.print("[dim]Press Enter when done...[/dim]")
                input()
                console.print("[green]✅ Done! Check if download started[/green]")
        
        elif choice == "3":
            console.print("\n[cyan]🔍 Searching for PDF/Document links...[/cyan]")
            urls = downloader.find_download_urls_in_page()
            
            if urls:
                table = Table(title="Document Links Found", box=box.ROUNDED)
                table.add_column("#", style="dim")
                table.add_column("Filename", style="yellow")
                table.add_column("Text", style="white")
                table.add_column("URL", style="dim")
                
                for i, doc in enumerate(urls, 1):
                    filename = doc.get('download', doc.get('url', '').split('/')[-1])
                    table.add_row(
                        str(i),
                        filename[:30],
                        doc.get('text', '')[:30],
                        doc.get('url', '')[:40]
                    )
                
                console.print(table)
                
                if Confirm.ask("\nDownload a document?"):
                    choice_num = int(Prompt.ask(f"Enter number (1-{len(urls)})", default="1")) - 1
                    if 0 <= choice_num < len(urls):
                        doc_url = urls[choice_num].get('url')
                        if doc_url:
                            filename = urls[choice_num].get('download')
                            if not filename:
                                filename = doc_url.split('/')[-1]
                            downloader.download_file(doc_url, filename)
            else:
                console.print("[yellow]No document links found[/yellow]")
        
        elif choice == "4":
            console.print("\n[yellow]Trying advanced click with full event simulation...[/yellow]")
            result = downloader.simulate_click_with_events("Important New! Online Submission")
            if result:
                console.print("[green]✅ Click simulated![/green]")
            else:
                console.print("[red]Could not find element[/red]")
                console.print("[cyan]Please click the button manually[/cyan]")
        
        elif choice == "5":
            console.print("\n[cyan]📋 Analyzing page structure...[/cyan]")
            
            # Get page title
            title = downloader.execute_js("document.title")
            console.print(f"[bold]Title:[/bold] {title}")
            
            # Count elements
            counts = downloader.execute_js("""
            (function() {
                return {
                    links: document.querySelectorAll('a').length,
                    buttons: document.querySelectorAll('button').length,
                    divs: document.querySelectorAll('div').length,
                    forms: document.querySelectorAll('form').length,
                    inputs: document.querySelectorAll('input').length
                };
            })()
            """)
            
            if counts:
                table = Table(title="Page Statistics", box=box.ROUNDED)
                table.add_column("Element Type", style="cyan")
                table.add_column("Count", style="green")
                
                for key, value in counts.items():
                    table.add_row(key.capitalize(), str(value))
                
                console.print(table)
            
            # Show all buttons with text
            buttons = downloader.execute_js("""
            (function() {
                const btns = [];
                document.querySelectorAll('button, [role="button"]').forEach(el => {
                    const text = el.textContent.trim();
                    if (text) {
                        btns.push({
                            text: text.substring(0, 50),
                            id: el.id || '',
                            class: el.className || ''
                        });
                    }
                });
                return btns;
            })()
            """)
            
            if buttons:
                console.print("\n[cyan]📌 Buttons found:[/cyan]")
                for i, btn in enumerate(buttons[:10], 1):
                    console.print(f"  {i}. {btn.get('text', '')}")
                    if i == 10 and len(buttons) > 10:
                        console.print(f"[dim]  ... and {len(buttons) - 10} more[/dim]")
        
        elif choice == "6":
            console.print("\n[cyan]💾 Saving page HTML...[/cyan]")
            html = downloader.execute_js("document.documentElement.outerHTML")
            if html:
                timestamp = int(time.time())
                filename = f"mca_page_{timestamp}.html"
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(html)
                console.print(f"[green]✅ Saved to {filename}[/green]")
            else:
                console.print("[red]Failed to get HTML[/red]")
        
        elif choice == "7":
            console.print("\n[cyan]🔄 Refreshing page...[/cyan]")
            downloader.execute_js("location.reload()")
            time.sleep(3)
            console.print("[green]✅ Page refreshed[/green]")
        
        if choice != "0":
            console.print()
            input("Press Enter to continue...")
    
    if downloader.ws:
        downloader.ws.close()
    console.print("[green]Goodbye! 👋[/green]")

if __name__ == "__main__":
    main()
