#!/usr/bin/env python3
"""
Chrome Page Tool - Enhanced Interactive Version
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
from rich.tree import Tree
from collections import defaultdict
from urllib.parse import urlparse

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

    def get_structured_text(self):
        """Get structured text content organized by sections/headings"""
        script = """
        (function() {
            const sections = [];
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_ELEMENT,
                {
                    acceptNode: function(node) {
                        const tag = node.tagName.toLowerCase();
                        if (['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'div', 'section', 'article'].includes(tag)) {
                            return NodeFilter.FILTER_ACCEPT;
                        }
                        return NodeFilter.FILTER_SKIP;
                    }
                }
            );
            
            let currentSection = {type: 'text', content: ''};
            let node = walker.nextNode();
            while (node) {
                const tag = node.tagName.toLowerCase();
                const text = node.textContent.trim();
                if (text && text.length > 0) {
                    if (['h1', 'h2', 'h3', 'h4', 'h5', 'h6'].includes(tag)) {
                        if (currentSection.content) {
                            sections.push(currentSection);
                        }
                        currentSection = {
                            type: 'heading',
                            level: parseInt(tag[1]),
                            content: text
                        };
                    } else {
                        if (currentSection.type === 'heading' && currentSection.content) {
                            sections.push(currentSection);
                            currentSection = {type: 'text', content: ''};
                        }
                        if (currentSection.type === 'text') {
                            currentSection.content += (currentSection.content ? '\\n' : '') + text;
                        }
                    }
                }
                node = walker.nextNode();
            }
            if (currentSection.content) {
                sections.push(currentSection);
            }
            return sections;
        })()
        """
        return self.js(script) or []

    def get_text_by_sections(self):
        """Get page text organized by major sections with hierarchy"""
        script = """
        (function() {
            const sections = [];
            const mainContent = document.querySelector('main') || document.body;
            
            const getSection = (element, level = 0) => {
                const tag = element.tagName.toLowerCase();
                if (['section', 'article', 'main', 'div'].includes(tag)) {
                    const section = {
                        type: 'section',
                        level: level,
                        heading: '',
                        content: [],
                        elements: []
                    };
                    
                    // Find heading within section
                    const headings = element.querySelectorAll('h1, h2, h3, h4, h5, h6');
                    if (headings.length > 0) {
                        section.heading = headings[0].textContent.trim();
                    }
                    
                    // Get text content
                    const textContent = element.textContent.trim();
                    if (textContent) {
                        // Split into paragraphs
                        const paragraphs = textContent.split(/\\n\\s*\\n/).filter(p => p.trim());
                        section.content = paragraphs.map(p => p.trim());
                    }
                    
                    return section;
                }
                return null;
            };
            
            // Get all sections
            const sectionElements = document.querySelectorAll('section, article, main > div');
            sectionElements.forEach(el => {
                const section = getSection(el);
                if (section && section.content.length > 0) {
                    sections.push(section);
                }
            });
            
            // If no sections found, get paragraphs
            if (sections.length === 0) {
                const paragraphs = document.querySelectorAll('p');
                if (paragraphs.length > 0) {
                    sections.push({
                        type: 'section',
                        heading: 'Content',
                        content: Array.from(paragraphs).map(p => p.textContent.trim()).filter(p => p)
                    });
                } else {
                    // Fallback to body text
                    const bodyText = document.body.textContent.trim();
                    if (bodyText) {
                        sections.push({
                            type: 'section',
                            heading: 'Page Content',
                            content: [bodyText]
                        });
                    }
                }
            }
            
            return sections;
        })()
        """
        return self.js(script) or []

    def get_structured_links(self):
        """Get links organized by category/path prefix"""
        script = """
        (function() {
            const links = document.querySelectorAll('a[href]');
            const categorized = {};
            
            links.forEach(a => {
                const href = a.href;
                const text = a.textContent.trim() || '[no text]';
                try {
                    const url = new URL(href);
                    let category = url.pathname.split('/')[1] || 'root';
                    if (!category) category = 'root';
                    
                    if (!categorized[category]) {
                        categorized[category] = [];
                    }
                    categorized[category].push({
                        href: href,
                        text: text,
                        path: url.pathname
                    });
                } catch(e) {
                    if (!categorized['other']) {
                        categorized['other'] = [];
                    }
                    categorized['other'].push({
                        href: href,
                        text: text,
                        path: href
                    });
                }
            });
            
            return categorized;
        })()
        """
        return self.js(script) or {}

    def get_elements_detailed(self, selector):
        """Get detailed element information with more context"""
        script = f"""
        (function() {{
            const els = document.querySelectorAll('{selector}');
            return Array.from(els).map(el => {{
                const rect = el.getBoundingClientRect();
                const styles = window.getComputedStyle(el);
                return {{
                    tag: el.tagName.toLowerCase(),
                    text: (el.textContent || '').trim().slice(0, 200),
                    id: el.id || '',
                    class: el.className || '',
                    href: el.href || '',
                    src: el.src || '',
                    value: el.value || '',
                    type: el.type || '',
                    name: el.name || '',
                    placeholder: el.placeholder || '',
                    title: el.title || '',
                    aria_label: el.getAttribute('aria-label') || '',
                    visible: el.offsetParent !== null,
                    position: {{
                        top: Math.round(rect.top),
                        left: Math.round(rect.left)
                    }},
                    size: {{
                        width: Math.round(rect.width),
                        height: Math.round(rect.height)
                    }},
                    color: styles.color,
                    background: styles.backgroundColor,
                    fontWeight: styles.fontWeight,
                    fontSize: styles.fontSize
                }};
            }});
        }})()
        """
        return self.js(script) or []

    def get_forms_detailed(self):
        """Get detailed form information"""
        script = """
        (function() {
            const forms = document.querySelectorAll('form');
            return Array.from(forms).map(form => {
                const inputs = form.querySelectorAll('input, textarea, select');
                return {
                    id: form.id || '',
                    name: form.name || '',
                    method: form.method || 'GET',
                    action: form.action || '',
                    inputs: Array.from(inputs).map(input => ({
                        type: input.type || input.tagName.toLowerCase(),
                        name: input.name || '',
                        id: input.id || '',
                        value: input.value || '',
                        placeholder: input.placeholder || '',
                        required: input.required || false
                    })),
                    submit_buttons: Array.from(form.querySelectorAll('button[type="submit"], input[type="submit"]')).map(btn => ({
                        text: btn.textContent || btn.value || 'Submit',
                        id: btn.id || ''
                    }))
                };
            });
        })()
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

def display_structured_text(sections):
    """Display structured text with hierarchy and formatting"""
    if not sections:
        console.print("[yellow]No text content found[/yellow]")
        return
    
    console.print("\n[bold cyan]📄 Page Content by Sections[/bold cyan]\n")
    
    for i, section in enumerate(sections, 1):
        if section.get('heading'):
            console.print(f"[bold yellow]{i}. {section['heading']}[/bold yellow]")
        else:
            console.print(f"[bold yellow]{i}. Section[/bold yellow]")
        
        content = section.get('content', [])
        if isinstance(content, list):
            for para in content[:5]:  # Show first 5 paragraphs
                if para.strip():
                    console.print(f"   {para[:200]}{'...' if len(para) > 200 else ''}")
                    console.print()
        else:
            console.print(f"   {content[:500]}{'...' if len(content) > 500 else ''}")
            console.print()
        
        if len(content) > 5:
            console.print(f"   [dim]... and {len(content)-5} more paragraphs[/dim]")
        
        console.print()

def display_links_categorized(categorized_links):
    """Display links organized by category/path"""
    if not categorized_links:
        console.print("[yellow]No links found[/yellow]")
        return
    
    total_links = sum(len(links) for links in categorized_links.values())
    console.print(f"\n[bold cyan]🔗 Links by Category ({total_links} total)[/bold cyan]\n")
    
    for category, links in sorted(categorized_links.items()):
        console.print(f"[bold green]/{category}/[/bold green] [dim]({len(links)} links)[/dim]")
        
        # Show first 10 links in each category
        for link in links[:10]:
            text = link.get('text', '')[:40]
            path = link.get('path', '')[:40]
            console.print(f"  • [blue]{text}[/blue] → [dim]{path}[/dim]")
        
        if len(links) > 10:
            console.print(f"  [dim]... and {len(links)-10} more[/dim]")
        console.print()

def display_elements_detailed(elements, title="Elements"):
    """Display elements with detailed information"""
    if not elements:
        console.print("[yellow]No elements found[/yellow]")
        return
    
    # Group by type
    grouped = defaultdict(list)
    for el in elements:
        tag = el.get('tag', 'unknown')
        grouped[tag].append(el)
    
    console.print(f"\n[bold cyan]{title}[/bold cyan] [dim]({len(elements)} total)[/dim]\n")
    
    for tag, items in sorted(grouped.items()):
        console.print(f"[bold yellow]{tag.upper()}[/bold yellow] [dim]({len(items)})[/dim]")
        
        for item in items[:5]:  # Show first 5 of each type
            text = (item.get('text') or item.get('value') or item.get('placeholder') or '')[:50]
            if item.get('href'):
                console.print(f"  • [blue]{text}[/blue] → [dim]{item.get('href', '')[:40]}[/dim]")
            else:
                console.print(f"  • [green]{text}[/green]")
                if item.get('id'):
                    console.print(f"    [dim]id: {item['id']}[/dim]")
                if item.get('type'):
                    console.print(f"    [dim]type: {item['type']}[/dim]")
        
        if len(items) > 5:
            console.print(f"  [dim]... and {len(items)-5} more[/dim]")
        console.print()

def display_forms_detailed(forms):
    """Display detailed form information"""
    if not forms:
        console.print("[yellow]No forms found[/yellow]")
        return
    
    console.print(f"\n[bold cyan]📝 Forms ({len(forms)})[/bold cyan]\n")
    
    for i, form in enumerate(forms, 1):
        console.print(f"[bold yellow]Form {i}[/bold yellow]")
        if form.get('id'):
            console.print(f"  id: [green]{form['id']}[/green]")
        if form.get('action'):
            console.print(f"  action: [dim]{form['action']}[/dim]")
        console.print(f"  method: [cyan]{form.get('method', 'GET')}[/cyan]")
        
        if form.get('inputs'):
            console.print("  [bold]Inputs:[/bold]")
            for inp in form['inputs'][:10]:
                type_info = inp.get('type', 'text')
                name_info = inp.get('name') or inp.get('id') or ''
                placeholder = inp.get('placeholder', '')
                required = "[red]*[/red]" if inp.get('required') else ""
                console.print(f"    • {type_info:10} {name_info:15} {placeholder[:30]} {required}")
            
            if len(form['inputs']) > 10:
                console.print(f"    [dim]... and {len(form['inputs'])-10} more[/dim]")
        
        if form.get('submit_buttons'):
            buttons = ', '.join([b.get('text', '') for b in form['submit_buttons']])
            console.print(f"  [bold]Submit:[/bold] {buttons}")
        
        console.print()

def display_interactive_elements(page, element_type):
    """Display interactive elements (inputs, buttons, selects)"""
    if element_type == 'inputs':
        selector = 'input:not([type="hidden"]):not([type="submit"]):not([type="button"]), textarea, select'
        title = "Input Fields & Selectables"
    elif element_type == 'buttons':
        selector = 'button, input[type="submit"], input[type="button"], input[type="reset"]'
        title = "Buttons"
    else:
        return
    
    elements = page.find_elements(selector)
    display_elements_detailed(elements, title)

def display_page_info(page):
    """Display comprehensive page information"""
    info = page.get_page_info()
    if not info:
        console.print("[yellow]No info available[/yellow]")
        return
    
    # Get additional info
    links = page.find_elements('a[href]')
    forms = page.get_forms_detailed()
    
    console.print("\n[bold cyan]📊 Page Statistics[/bold cyan]\n")
    
    # Create a table for stats
    table = Table(box=box.SIMPLE)
    table.add_column("Metric", style="yellow")
    table.add_column("Value", style="green")
    
    for key, value in info.items():
        if key not in ['url', 'title']:
            table.add_row(key.replace('_', ' ').title(), str(value))
    
    table.add_row("Total Links", str(len(links)))
    table.add_row("Total Forms", str(len(forms)))
    console.print(table)
    
    console.print(f"\n[bold]URL:[/bold] [blue]{info.get('url', 'N/A')}[/blue]")
    console.print(f"[bold]Title:[/bold] [cyan]{info.get('title', 'N/A')}[/cyan]")

def main():
    console.clear()
    console.print(Panel("[bold cyan]🌐 Chrome Page Tool - Enhanced[/bold cyan]", border_style="green"))

    port = int(Prompt.ask("Port", default="9236"))
    page = ChromePage(port)

    if not page.connect():
        return

    while True:
        console.print()
        console.print(Panel(f"[bold]Current Page: {page.get_title() or 'Unknown'}[/bold]", border_style="blue"))

        console.print("[cyan]📌 Options:[/cyan]")
        console.print("  1. Page Info & Statistics")
        console.print("  2. Show Page Text (Structured)")
        console.print("  3. Find Elements (Detailed)")
        console.print("  4. Show All Links (Categorized)")
        console.print("  5. Show All Buttons")
        console.print("  6. Show All Inputs & Selectables")
        console.print("  7. Show All Images")
        console.print("  8. Show Forms (Detailed)")
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
            display_page_info(page)

        elif choice == "2":  # Show Page Text (Structured)
            sections = page.get_text_by_sections()
            display_structured_text(sections)

        elif choice == "3":  # Find Elements (Detailed)
            selector = Prompt.ask("CSS selector")
            elements = page.get_elements_detailed(selector)
            display_elements_detailed(elements, f"Elements matching '{selector}'")

        elif choice == "4":  # Show Links (Categorized)
            links = page.get_structured_links()
            display_links_categorized(links)

        elif choice == "5":  # Show Buttons
            display_interactive_elements(page, 'buttons')

        elif choice == "6":  # Show Inputs & Selectables
            display_interactive_elements(page, 'inputs')

        elif choice == "7":  # Show Images
            elements = page.get_elements_detailed('img[src]')
            display_elements_detailed(elements, f"Images ({len(elements)})")

        elif choice == "8":  # Show Forms (Detailed)
            forms = page.get_forms_detailed()
            display_forms_detailed(forms)

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
