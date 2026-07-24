#!/usr/bin/env python3
"""
Autonomous Web Crawler - Site Discovery & Data Extraction
Builds complete site map by following links and extracting data
"""

import json
import websocket
import requests
import sys
import time
import hashlib
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import box
from rich.tree import Tree
from collections import defaultdict, deque
from urllib.parse import urlparse, urljoin
from datetime import datetime

console = Console()

class AutonomousCrawler:
    def __init__(self, port=9257):
        self.port = port
        self.ws = None
        self.connected = False
        self.base_url = ""
        self.discovered_urls = set()
        self.visited_urls = set()
        self.url_queue = deque()
        self.site_map = {}
        self.page_data = {}
        self.api_endpoints = set()
        self.assets = defaultdict(set)
        self.crawl_stats = {
            'pages_visited': 0,
            'links_found': 0,
            'api_calls': 0,
            'errors': 0
        }
        self.har_data = []

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

            ws_url = page_tab.get('webSocketDebuggerUrl')
            self.ws = websocket.create_connection(ws_url, timeout=10)

            # Enable domains
            self._enable_domains()
            
            self.connected = True
            self.base_url = urlparse(page_tab.get('url', '')).netloc
            
            console.print(f"[green]✅ Connected to Chrome on port {self.port}[/green]")
            console.print(f"[dim]   Base URL: {self.base_url}[/dim]")
            return True

        except Exception as e:
            console.print(f"[red]Connection failed: {e}[/red]")
            return False

    def _enable_domains(self):
        """Enable necessary CDP domains"""
        domains = ["Network.enable", "Runtime.enable", "DOM.enable", "Page.enable"]
        for i, domain in enumerate(domains, start=1):
            try:
                self.ws.send(json.dumps({"id": i, "method": domain}))
                self.ws.settimeout(1)
                try:
                    self.ws.recv()
                except:
                    pass
            except:
                pass

    def js(self, script, await_promise=False):
        """Execute JavaScript and return result"""
        if not self.connected:
            return None

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
                    return None
            except:
                continue
        return None

    def get_current_url(self):
        """Get current page URL"""
        return self.js("window.location.href") or ""

    def get_page_links(self):
        """Extract all links from current page"""
        script = """
        (function() {
            const links = [];
            const base = window.location.origin;
            document.querySelectorAll('a[href]').forEach(a => {
                const href = a.href;
                const text = a.textContent.trim() || '';
                if (href && !href.startsWith('javascript:') && !href.startsWith('mailto:')) {
                    try {
                        const url = new URL(href);
                        // Only include same-domain links
                        if (url.origin === window.location.origin) {
                            links.push({
                                url: href,
                                path: url.pathname,
                                text: text.substring(0, 50),
                                is_relative: href.startsWith('/')
                            });
                        }
                    } catch(e) {}
                }
            });
            return links;
        })()
        """
        return self.js(script) or []

    def extract_page_data(self):
        """Extract structured data from current page"""
        script = """
        (function() {
            const data = {
                url: window.location.href,
                title: document.title,
                timestamp: Date.now(),
                headers: [],
                paragraphs: [],
                lists: [],
                tables: [],
                forms: [],
                meta: {},
                schema: []
            };
            
            // Get meta tags
            document.querySelectorAll('meta').forEach(meta => {
                const name = meta.getAttribute('name') || meta.getAttribute('property') || '';
                const content = meta.getAttribute('content') || '';
                if (name && content) {
                    data.meta[name] = content;
                }
            });
            
            // Get headers
            document.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(h => {
                data.headers.push({
                    level: parseInt(h.tagName[1]),
                    text: h.textContent.trim()
                });
            });
            
            // Get paragraphs
            document.querySelectorAll('p').forEach(p => {
                const text = p.textContent.trim();
                if (text.length > 10) {
                    data.paragraphs.push(text);
                }
            });
            
            // Get lists
            document.querySelectorAll('ul, ol').forEach(list => {
                const items = list.querySelectorAll('li');
                data.lists.push({
                    type: list.tagName.toLowerCase(),
                    items: Array.from(items).map(li => li.textContent.trim()).slice(0, 10)
                });
            });
            
            // Get tables
            document.querySelectorAll('table').forEach(table => {
                const rows = table.querySelectorAll('tr');
                data.tables.push({
                    rows: rows.length,
                    cols: rows[0] ? rows[0].querySelectorAll('td, th').length : 0,
                    headers: rows[0] ? Array.from(rows[0].querySelectorAll('th')).map(th => th.textContent.trim()) : []
                });
            });
            
            // Get forms
            document.querySelectorAll('form').forEach(form => {
                data.forms.push({
                    action: form.action || '',
                    method: form.method || 'GET',
                    inputs: form.querySelectorAll('input, textarea, select').length,
                    fields: Array.from(form.querySelectorAll('input[name], select[name], textarea[name]')).map(el => ({
                        name: el.name || '',
                        type: el.type || el.tagName.toLowerCase()
                    }))
                });
            });
            
            // Get JSON-LD schema
            document.querySelectorAll('script[type="application/ld+json"]').forEach(script => {
                try {
                    data.schema.push(JSON.parse(script.textContent));
                } catch(e) {}
            });
            
            return data;
        })()
        """
        return self.js(script) or {}

    def navigate_to_url(self, url):
        """Navigate to a URL"""
        console.print(f"[dim]Navigating to: {url}[/dim]")
        result = self.js(f"window.location.href = '{url}'")
        time.sleep(3)  # Wait for page to load
        return True

    def discover_site(self, max_pages=50):
        """Autonomously crawl and discover the entire site"""
        console.print(f"\n[bold cyan]🕷️ Starting Autonomous Crawl[/bold cyan]")
        console.print(f"[dim]Max pages: {max_pages}[/dim]")
        
        # Start with current page
        current_url = self.get_current_url()
        if current_url:
            self.url_queue.append(current_url)
            self.discovered_urls.add(current_url)
        
        page_count = 0
        
        while self.url_queue and page_count < max_pages:
            url = self.url_queue.popleft()
            
            if url in self.visited_urls:
                continue
            
            console.print(f"\n[bold]Page {page_count + 1}:[/bold] {url[:80]}")
            
            # Navigate to URL
            if page_count > 0:
                self.navigate_to_url(url)
            
            # Extract page data
            page_data = self.extract_page_data()
            self.page_data[url] = page_data
            self.visited_urls.add(url)
            page_count += 1
            
            # Extract links
            links = self.get_page_links()
            console.print(f"[dim]  Found {len(links)} links[/dim]")
            
            # Add new links to queue
            for link in links:
                link_url = link.get('url', '')
                if link_url and link_url not in self.discovered_urls:
                    self.discovered_urls.add(link_url)
                    self.url_queue.append(link_url)
            
            # Update stats
            self.crawl_stats['pages_visited'] = page_count
            self.crawl_stats['links_found'] += len(links)
            
            # Show progress
            console.print(f"[dim]  Queue: {len(self.url_queue)} URLs remaining[/dim]")
            
            # Small delay to be polite
            time.sleep(0.5)
        
        # Build site map
        self._build_site_map()
        
        console.print(f"\n[bold green]✅ Crawl Complete![/bold green]")
        console.print(f"  Pages visited: {self.crawl_stats['pages_visited']}")
        console.print(f"  Links discovered: {self.crawl_stats['links_found']}")
        console.print(f"  Unique URLs: {len(self.discovered_urls)}")

    def _build_site_map(self):
        """Build hierarchical site map from discovered URLs"""
        self.site_map = defaultdict(list)
        
        for url in self.discovered_urls:
            parsed = urlparse(url)
            path_parts = parsed.path.strip('/').split('/') if parsed.path else ['root']
            
            # Group by first path segment
            if path_parts and path_parts[0]:
                category = path_parts[0]
            else:
                category = 'root'
            
            self.site_map[category].append({
                'url': url,
                'path': parsed.path,
                'depth': len(path_parts)
            })

    def analyze_api_patterns(self):
        """Analyze network traffic to discover API patterns"""
        script = """
        (function() {
            const apis = [];
            // Get all fetch/XHR requests from performance
            const entries = performance.getEntriesByType('resource');
            entries.forEach(entry => {
                const url = entry.name;
                if (url.includes('/api/') || url.includes('/rest/') || 
                    url.includes('/graphql') || url.includes('.json')) {
                    apis.push({
                        url: url,
                        type: entry.initiatorType || 'unknown',
                        duration: entry.duration || 0
                    });
                }
            });
            return apis;
        })()
        """
        return self.js(script) or []

    def save_crawl_data(self, filename=None):
        """Save crawl data to JSON file"""
        if not filename:
            filename = f"crawl_{int(time.time())}.json"
        
        data = {
            'metadata': {
                'base_url': self.base_url,
                'timestamp': datetime.now().isoformat(),
                'stats': self.crawl_stats
            },
            'site_map': self.site_map,
            'pages': self.page_data,
            'discovered_urls': list(self.discovered_urls)
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        console.print(f"[green]✅ Saved crawl data to {filename}[/green]")
        return filename

    def display_site_map(self):
        """Display site map in tree format"""
        if not self.site_map:
            console.print("[yellow]No site map available. Run crawl first.[/yellow]")
            return
        
        console.print(f"\n[bold cyan]🗺️ Site Map[/bold cyan]")
        console.print(f"[dim]Total pages: {len(self.discovered_urls)}[/dim]\n")
        
        tree = Tree(f"[bold]{self.base_url}[/bold]")
        
        for category, urls in sorted(self.site_map.items()):
            if category == 'root':
                branch = tree.add(f"[yellow]/[/yellow]")
            else:
                branch = tree.add(f"[yellow]/{category}/[/yellow]")
            
            # Show first 5 URLs per category
            for url_info in urls[:5]:
                path = url_info['path']
                depth = url_info['depth']
                indent = "  " * (depth - 1) if depth > 1 else ""
                branch.add(f"{indent}[dim]{path if path else '/'}[/dim]")
            
            if len(urls) > 5:
                branch.add(f"[dim]... and {len(urls)-5} more[/dim]")
        
        console.print(tree)

    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except:
                pass

def main():
    console.clear()
    console.print(Panel("[bold cyan]🕷️ Autonomous Web Crawler[/bold cyan]", border_style="green"))
    console.print("[dim]Site Discovery + Data Extraction + API Detection[/dim]")

    port = int(Prompt.ask("Port", default="9257"))
    crawler = AutonomousCrawler(port)

    if not crawler.connect():
        return

    while True:
        console.print()
        console.print(Panel(f"[bold]Current URL: {crawler.get_current_url() or 'Unknown'}[/bold]", border_style="blue"))

        console.print("[cyan]📌 Options:[/cyan]")
        console.print("  1. 🕷️ Start Autonomous Crawl")
        console.print("  2. Extract Current Page Data")
        console.print("  3. Show Site Map")
        console.print("  4. Analyze API Patterns")
        console.print("  5. Save Crawl Data")
        console.print("  6. Navigate to URL")
        console.print("  7. Execute Custom JS")
        console.print("  8. Show Stats")
        console.print("  9. Refresh Page")
        console.print("  0. Exit")

        choice = Prompt.ask("Select", choices=["0","1","2","3","4","5","6","7","8","9"])

        if choice == "0":
            break

        elif choice == "1":
            max_pages = int(Prompt.ask("Max pages to crawl", default="50"))
            crawler.discover_site(max_pages)

        elif choice == "2":
            data = crawler.extract_page_data()
            if data:
                console.print(f"\n[bold cyan]📄 Page Data[/bold cyan]")
                console.print(f"  URL: {data.get('url', 'N/A')}")
                console.print(f"  Title: {data.get('title', 'N/A')}")
                console.print(f"  Headers: {len(data.get('headers', []))}")
                console.print(f"  Paragraphs: {len(data.get('paragraphs', []))}")
                console.print(f"  Lists: {len(data.get('lists', []))}")
                console.print(f"  Tables: {len(data.get('tables', []))}")
                console.print(f"  Forms: {len(data.get('forms', []))}")
                
                if data.get('schema'):
                    console.print(f"  Schema: {len(data['schema'])} items")
            else:
                console.print("[yellow]No data extracted[/yellow]")

        elif choice == "3":
            crawler.display_site_map()

        elif choice == "4":
            apis = crawler.analyze_api_patterns()
            if apis:
                console.print(f"\n[bold cyan]🔌 API Endpoints Detected ({len(apis)})[/bold cyan]")
                for api in apis[:20]:
                    console.print(f"  {api.get('type', '')} {api.get('url', '')[:80]}")
                if len(apis) > 20:
                    console.print(f"[dim]... and {len(apis)-20} more[/dim]")
            else:
                console.print("[yellow]No API patterns detected[/yellow]")

        elif choice == "5":
            if not crawler.page_data:
                console.print("[yellow]No data to save. Run crawl first.[/yellow]")
            else:
                crawler.save_crawl_data()

        elif choice == "6":
            url = Prompt.ask("URL")
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"
            crawler.navigate_to_url(url)

        elif choice == "7":
            script = Prompt.ask("JavaScript code")
            result = crawler.js(script)
            if result is not None:
                console.print(Panel(str(result)[:2000], title="Result", border_style="green"))
            else:
                console.print("[yellow]No result or error[/yellow]")

        elif choice == "8":
            console.print(f"\n[bold cyan]📊 Crawl Statistics[/bold cyan]")
            console.print(f"  Pages visited: {crawler.crawl_stats['pages_visited']}")
            console.print(f"  Links discovered: {crawler.crawl_stats['links_found']}")
            console.print(f"  Unique URLs: {len(crawler.discovered_urls)}")
            console.print(f"  API endpoints: {len(crawler.api_endpoints)}")
            console.print(f"  Queue size: {len(crawler.url_queue)}")

        elif choice == "9":
            crawler.js("location.reload()")
            console.print("[yellow]⏳ Page reloading...[/yellow]")
            time.sleep(2)
            console.print("[green]✅ Refreshed![/green]")

        if choice != "0":
            console.print()
            input("Press Enter to continue...")

    crawler.close()
    console.print("[green]Goodbye! 👋[/green]")

if __name__ == "__main__":
    main()
