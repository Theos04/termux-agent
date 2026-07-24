#!/usr/bin/env python3
"""
Enhanced Chrome Page Analyzer with DOM Exploration & Clickable Elements
Scrapes page content, maps hyperlinks, and handles interactive elements
"""

import json
import websocket
import requests
import sys
import time
import subprocess
import os
from typing import Optional, Dict, List, Any, Set
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
import rich.box as box
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.tree import Tree
from urllib.parse import urljoin, urlparse
from collections import Counter
import re

console = Console()

# ============================================================================
# Enhanced Chrome Page Client with DOM Exploration
# ============================================================================

class ChromePage:
    def __init__(self, port=9236):
        self.port = port
        self.ws = None
        self.connected = False
        self.page_title = ""
        self.page_url = ""
        self.base_domain = ""
        self.visited_urls: Set[str] = set()
        self.clickable_elements: List[Dict] = []

    def connect(self):
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
            self.base_domain = urlparse(self.page_url).netloc
            ws_url = page_tab.get('webSocketDebuggerUrl')

            self.ws = websocket.create_connection(ws_url, timeout=10)

            self.ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
            while True:
                resp = self.ws.recv()
                data = json.loads(resp)
                if data.get('id') == 1:
                    break

            self.connected = True
            return True

        except Exception as e:
            console.print(f"[red]Connection failed: {e}[/red]")
            return False

    def js(self, script, await_promise=False, return_by_value=True):
        if not self.connected:
            return None

        cmd_id = int(time.time() * 1000) % 100000

        self.ws.send(json.dumps({
            "id": cmd_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": script,
                "returnByValue": return_by_value,
                "awaitPromise": await_promise
            }
        }))

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
                    if 'exceptionDetails' in result:
                        console.print(f"[red]JS Error: {result['exceptionDetails']}[/red]")
                        return None
                    return None
            except:
                pass

        return None

    def get_text(self):
        return self.js("document.body ? document.body.innerText : ''") or ""

    def get_title(self):
        return self.js("document.title") or "No title"

    def get_html(self):
        return self.js("document.documentElement.outerHTML") or ""

    def get_all_links(self) -> List[Dict[str, str]]:
        """Extract all hyperlinks with their context and additional metadata"""
        script = """
        (function() {
            const links = [];
            const elements = document.querySelectorAll('a[href]');
            elements.forEach(el => {
                const href = el.getAttribute('href');
                const text = el.textContent.trim() || '[No text]';
                const title = el.getAttribute('title') || '';
                const rel = el.getAttribute('rel') || '';
                const target = el.getAttribute('target') || '';
                const className = el.className || '';
                const id = el.id || '';
                
                const isExternal = href && (href.startsWith('http://') || href.startsWith('https://'));
                const isInternal = href && !isExternal && !href.startsWith('javascript:') && !href.startsWith('#');
                const isAnchor = href && href.startsWith('#');
                
                // Check if it looks like a competitor link (contains common competitor keywords)
                const competitorKeywords = ['competitor', 'alternative', 'vs', 'compare', 'similar', 'rival', 'other', 'options'];
                const isCompetitor = text.toLowerCase().includes('competitor') || 
                                    text.toLowerCase().includes('alternative') ||
                                    text.toLowerCase().includes('vs') ||
                                    text.toLowerCase().includes('compare') ||
                                    text.toLowerCase().includes('similar') ||
                                    (href && competitorKeywords.some(kw => href.toLowerCase().includes(kw)));
                
                links.push({
                    href: href,
                    text: text,
                    title: title || '',
                    rel: rel || '',
                    target: target || '',
                    className: className || '',
                    id: id || '',
                    type: isExternal ? 'external' : (isInternal ? 'internal' : (isAnchor ? 'anchor' : 'other')),
                    is_clickable: true,
                    element: el.tagName,
                    isCompetitor: isCompetitor,
                    domain: href ? new URL(href, window.location.href).hostname : ''
                });
            });
            return links;
        })()
        """
        result = self.js(script)
        return result if result else []

    def get_clickable_elements(self) -> List[Dict[str, Any]]:
        """Find all clickable elements (buttons, links, clickable divs)"""
        script = """
        (function() {
            const elements = [];

            // Function to check if element is clickable
            function isClickable(el) {
                // Check for click listeners
                const hasListener = el._listeners && el._listeners.click;

                // Check attributes
                const hasClickAttr = el.hasAttribute('onclick');
                const hasRole = el.getAttribute('role') === 'button' ||
                               el.getAttribute('role') === 'link';
                const hasCursor = window.getComputedStyle(el).cursor === 'pointer';

                return hasListener || hasClickAttr || hasRole || hasCursor;
            }

            // Get all elements
            const allElements = document.querySelectorAll('*');
            allElements.forEach(el => {
                const tag = el.tagName.toLowerCase();

                // Standard clickable elements
                if (tag === 'button' || tag === 'a' || tag === 'input' ||
                    (tag === 'div' && isClickable(el)) ||
                    (tag === 'span' && isClickable(el))) {

                    const rect = el.getBoundingClientRect();
                    const isVisible = rect.width > 0 && rect.height > 0;

                    if (isVisible) {
                        const href = el.getAttribute('href');
                        const type = el.getAttribute('type');
                        const role = el.getAttribute('role');
                        const text = el.textContent.trim();
                        const id = el.getAttribute('id');
                        const classes = el.className;
                        const dataset = JSON.stringify(el.dataset);

                        // Get nearest form if any
                        let form = el.closest('form');
                        let formAction = form ? form.getAttribute('action') : null;
                        let formMethod = form ? form.getAttribute('method') : 'GET';

                        elements.push({
                            tag: tag,
                            text: text || '[No text]',
                            href: href || null,
                            type: type || null,
                            role: role || null,
                            id: id || null,
                            classes: classes || '',
                            dataset: dataset || '{}',
                            is_visible: true,
                            form_action: formAction,
                            form_method: formMethod,
                            position: {
                                x: Math.round(rect.x),
                                y: Math.round(rect.y),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height)
                            }
                        });
                    }
                }
            });

            return elements;
        })()
        """
        result = self.js(script)
        return result if result else []

    def click_element(self, selector: str) -> bool:
        """Click an element by selector"""
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

    def click_by_text(self, text: str) -> bool:
        """Click an element by its text content"""
        script = f"""
        (function() {{
            const elements = document.querySelectorAll('button, a, [role="button"], [role="link"]');
            for (let el of elements) {{
                if (el.textContent.trim() === '{text}') {{
                    el.click();
                    return true;
                }}
            }}
            return false;
        }})()
        """
        return self.js(script) or False

    def get_form_inputs(self) -> List[Dict[str, Any]]:
        """Extract all form inputs with their current values"""
        script = """
        (function() {
            const inputs = [];
            const elements = document.querySelectorAll('input, select, textarea');
            elements.forEach(el => {
                const tag = el.tagName.toLowerCase();
                const type = el.getAttribute('type') || 'text';
                const name = el.getAttribute('name') || '';
                const value = el.value || '';
                const placeholder = el.getAttribute('placeholder') || '';
                const required = el.hasAttribute('required');
                const disabled = el.disabled;

                inputs.push({
                    tag: tag,
                    type: type,
                    name: name,
                    value: value,
                    placeholder: placeholder,
                    required: required,
                    disabled: disabled,
                    options: tag === 'select' ?
                        Array.from(el.options).map(opt => ({
                            text: opt.text,
                            value: opt.value,
                            selected: opt.selected
                        })) : null
                });
            });
            return inputs;
        })()
        """
        result = self.js(script)
        return result if result else []

    def get_dom_tree(self, max_depth=5) -> Dict[str, Any]:
        """Get a simplified DOM tree"""
        script = f"""
        (function() {{
            function getTree(node, depth) {{
                if (depth > {max_depth}) return null;
                if (node.nodeType !== 1) return null;

                const obj = {{
                    tag: node.tagName.toLowerCase(),
                    id: node.id || null,
                    classes: Array.from(node.classList),
                    children: []
                }};

                // Only include meaningful elements
                const shouldInclude = obj.tag === 'div' || obj.tag === 'section' ||
                                     obj.tag === 'article' || obj.tag === 'main' ||
                                     obj.tag === 'header' || obj.tag === 'footer' ||
                                     obj.tag === 'nav' || obj.tag === 'form';

                if (node.children) {{
                    for (let child of node.children) {{
                        const childTree = getTree(child, depth + 1);
                        if (childTree) {{
                            obj.children.push(childTree);
                        }}
                    }}
                }}

                return obj;
            }}

            return getTree(document.body, 0);
        }})()
        """
        result = self.js(script)
        return result if result else {}

    def find_elements_by_selector(self, selector: str) -> List[Dict]:
        """Find elements by CSS selector"""
        script = f"""
        (function() {{
            const elements = [];
            const nodes = document.querySelectorAll('{selector}');
            nodes.forEach(el => {{
                elements.push({{
                    tag: el.tagName.toLowerCase(),
                    text: el.textContent.trim(),
                    html: el.outerHTML.substring(0, 200),
                    id: el.id || null,
                    classes: Array.from(el.classList)
                }});
            }});
            return elements;
        }})()
        """
        result = self.js(script)
        return result if result else []

    def navigate_to(self, url: str) -> bool:
        """Navigate to a URL"""
        script = f"""
        (function() {{
            window.location.href = '{url}';
            return true;
        }})()
        """
        self.js(script)
        time.sleep(2)  # Wait for page to load
        return True

    def get_page_metadata(self) -> Dict:
        """Get comprehensive page metadata"""
        script = """
        (function() {
            return {
                title: document.title,
                url: window.location.href,
                domain: window.location.hostname,
                description: document.querySelector('meta[name="description"]')?.getAttribute('content') || '',
                keywords: document.querySelector('meta[name="keywords"]')?.getAttribute('content') || '',
                author: document.querySelector('meta[name="author"]')?.getAttribute('content') || '',
                charset: document.characterSet || document.charset || '',
                viewport: document.querySelector('meta[name="viewport"]')?.getAttribute('content') || '',
                language: document.documentElement.lang || '',
                total_links: document.querySelectorAll('a[href]').length,
                total_images: document.querySelectorAll('img').length,
                total_scripts: document.querySelectorAll('script').length,
                total_styles: document.querySelectorAll('link[rel="stylesheet"]').length,
                has_form: document.querySelectorAll('form').length > 0,
                has_login_form: document.querySelectorAll('form input[type="password"]').length > 0,
                word_count: document.body ? document.body.innerText.split(/\\s+/).length : 0,
                is_secure: window.location.protocol === 'https:'
            };
        })()
        """
        result = self.js(script)
        return result if result else {}

    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except:
                pass

# ============================================================================
# DOM Explorer & Link Mapper with Competition Detection
# ============================================================================

class DOMExplorer:
    def __init__(self, page: ChromePage):
        self.page = page
        self.visited = set()
        self.links_map: Dict[str, List[Dict]] = {}
        self.competition_keywords = [
            'competitor', 'alternative', 'vs', 'compare', 'similar', 'rival',
            'other options', 'best alternatives', 'competition', 'competing',
            'rivals', 'alternatives', 'compare to', 'comparison'
        ]

    def map_links(self, max_pages=10, same_domain=True) -> Dict:
        """Crawl and map links on the page with competition detection"""
        console.print("[cyan]🔍 Mapping hyperlinks...[/cyan]")

        links = self.page.get_all_links()

        # Separate internal and external links
        internal_links = []
        external_links = []
        competition_links = []
        anchor_links = []

        for link in links:
            href = link.get('href', '')
            is_competitor = link.get('isCompetitor', False) or self._is_competition_link(link)
            
            if href.startswith('#'):
                anchor_links.append(link)
                if is_competitor:
                    competition_links.append(link)
            elif href.startswith(('http://', 'https://')):
                if self.page.base_domain in href:
                    internal_links.append(link)
                else:
                    external_links.append(link)
                    if is_competitor:
                        competition_links.append(link)
            elif href.startswith('/') or href.startswith('./') or href.startswith('../'):
                # Relative URLs - treat as internal
                full_url = urljoin(self.page.page_url, href)
                link['href'] = full_url
                internal_links.append(link)

        # Group external links by domain
        domain_groups = {}
        for link in external_links:
            domain = link.get('domain', '')
            if domain:
                if domain not in domain_groups:
                    domain_groups[domain] = []
                domain_groups[domain].append(link)

        # Find potential competitor domains
        competitor_domains = []
        for domain, domain_links in domain_groups.items():
            if self._is_competitor_domain(domain) or domain_links[0].get('isCompetitor', False):
                competitor_domains.append(domain)

        result = {
            'current_url': self.page.page_url,
            'current_domain': self.page.base_domain,
            'internal_links': internal_links,
            'external_links': external_links,
            'anchor_links': anchor_links,
            'competition_links': competition_links,
            'competitor_domains': competitor_domains,
            'domain_groups': domain_groups,
            'total_links': len(links),
            'unique_internal': len(set(l['href'] for l in internal_links)),
            'unique_external': len(set(l['href'] for l in external_links))
        }

        return result

    def _is_competition_link(self, link: Dict) -> bool:
        """Check if a link is likely a competitor based on text and context"""
        text = link.get('text', '').lower()
        href = link.get('href', '').lower()
        
        # Check for competition indicators in text or href
        for keyword in self.competition_keywords:
            if keyword in text or keyword in href:
                return True
        
        return False

    def _is_competitor_domain(self, domain: str) -> bool:
        """Check if a domain looks like a competitor"""
        # Common competitor domains (you can expand this)
        competitor_patterns = [
            r'\bcompeting\b',
            r'\balt\b',
            r'\bcompare\b',
            r'\bvs\b',
            r'\brival\b'
        ]
        
        for pattern in competitor_patterns:
            if re.search(pattern, domain, re.IGNORECASE):
                return True
        
        return False

    def get_competitor_analysis(self) -> Dict:
        """Analyze the page for competitor information"""
        console.print("[yellow]🔎 Analyzing competition...[/yellow]")
        
        # Get all links with competition detection
        links = self.page.get_all_links()
        competitor_links = [l for l in links if l.get('isCompetitor', False)]
        
        # Also check text content for competitor mentions
        text = self.page.get_text().lower()
        competitor_mentions = []
        for keyword in self.competition_keywords:
            if keyword in text:
                competitor_mentions.append(keyword)
        
        return {
            'competitor_links': competitor_links,
            'competitor_keywords_found': competitor_mentions,
            'total_competitor_links': len(competitor_links),
            'competitor_domains': list(set([l.get('domain', '') for l in competitor_links if l.get('domain')]))
        }

    def explore_page_structure(self) -> Dict:
        """Analyze page structure and identify key sections"""
        console.print("[cyan]🏗️ Analyzing page structure...[/cyan]")

        structure = {
            'headers': self.page.find_elements_by_selector('h1, h2, h3, h4, h5, h6'),
            'navigation': self.page.find_elements_by_selector('nav, header nav, .nav, #nav'),
            'main_content': self.page.find_elements_by_selector('main, #main, .main, article, #content'),
            'sidebars': self.page.find_elements_by_selector('aside, .sidebar, #sidebar'),
            'footer': self.page.find_elements_by_selector('footer, .footer, #footer'),
            'forms': self.page.find_elements_by_selector('form'),
            'buttons': self.page.find_elements_by_selector('button, [role="button"]'),
            'modals': self.page.find_elements_by_selector('.modal, #modal, .popup'),
            'lists': self.page.find_elements_by_selector('ul, ol'),
            'tables': self.page.find_elements_by_selector('table')
        }

        return structure

# ============================================================================
# Llama.cpp Integration (Enhanced)
# ============================================================================

class LlamaAnalyzer:
    def __init__(self, model_path=None):
        self.model_path = model_path or self._find_model()
        self.llama_bin = self._find_llama_bin()
        self.available = self.llama_bin and self.model_path

        if self.available:
            console.print(f"[green]✅ Llama.cpp available[/green]")
            console.print(f"[dim]   Binary: {self.llama_bin}[/dim]")
            console.print(f"[dim]   Model: {self.model_path}[/dim]")
        else:
            console.print("[yellow]⚠️ Llama.cpp not found[/yellow]")
            console.print("[dim]   Please install llama.cpp or specify model path[/dim]")

    def _find_llama_bin(self):
        """Find llama.cpp binary"""
        possible_paths = [
            "./llama.cpp/llama-cli",
            "./llama.cpp/main",
            "~/llama.cpp/llama-cli",
            "llama-cli",
            "llama"
        ]

        for path in possible_paths:
            expanded = os.path.expanduser(path)
            if os.path.exists(expanded) and os.access(expanded, os.X_OK):
                return expanded

        try:
            result = subprocess.run(["which", "llama-cli"], capture_output=True)
            if result.returncode == 0:
                return result.stdout.decode().strip()
        except:
            pass

        return None

    def _find_model(self):
        import glob

        possible_paths = [
            "./llama.cpp/models/*.gguf",
            "~/llama.cpp/models/*.gguf",
            "./*.gguf",
            "~/*.gguf"
        ]

        candidates = []

        for pattern in possible_paths:
            expanded = os.path.expanduser(pattern)
            for model in glob.glob(expanded):
                name = os.path.basename(model).lower()
                if name.startswith("ggml-vocab"):
                    continue
                try:
                    size = os.path.getsize(model)
                except OSError:
                    continue
                if size < 100 * 1024 * 1024:
                    continue
                candidates.append(model)

        if not candidates:
            return None

        return max(candidates, key=os.path.getsize)

    def analyze(self, text: str, prompt_template: str = None) -> str:
        """Analyze text using llama.cpp"""
        if not self.available:
            return "Llama.cpp not available"

        if not text:
            return "No text to analyze"

        if len(text) > 4000:
            text = text[:4000] + "..."

        if prompt_template is None:
            prompt_template = """Analyze this web page content and provide a comprehensive summary:

1. Main purpose of the page
2. Key topics discussed
3. Any opportunities (jobs, internships, products, services)
4. Important actions or calls to action
5. Key data points or statistics

Page content:
{text}

Format as structured bullet points with clear sections."""

        prompt = prompt_template.replace("{text}", text)

        try:
            cmd = [
                self.llama_bin,
                "-m", self.model_path,
                "-p", prompt,
                "-n", "512",
                "-t", "4",
                "--temp", "0.7",
                "--repeat-penalty", "1.1"
            ]

            console.print("[dim]Analyzing with llama.cpp...[/dim]")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return f"Error: {result.stderr[:200]}"

        except subprocess.TimeoutExpired:
            return "Analysis timed out"
        except Exception as e:
            return f"Error: {e}"

# ============================================================================
# Main Tool - Enhanced with DOM Exploration
# ============================================================================

def show_competition_links(explorer: DOMExplorer):
    """Show competition links specifically"""
    console.print()
    console.print(Panel("[bold yellow]🎯 COMPETITION LINKS[/bold yellow]", border_style="red"))
    
    competitor_analysis = explorer.get_competitor_analysis()
    
    if competitor_analysis['competitor_links']:
        table = Table(title=f"Competitor Links Found ({len(competitor_analysis['competitor_links'])})", 
                     box=box.ROUNDED, border_style="red")
        table.add_column("#", style="dim")
        table.add_column("Text", style="white")
        table.add_column("URL", style="cyan")
        table.add_column("Domain", style="yellow")
        table.add_column("Title/Context", style="dim")
        
        for i, link in enumerate(competitor_analysis['competitor_links'], 1):
            table.add_row(
                str(i),
                link.get('text', '')[:40],
                link.get('href', '')[:50],
                link.get('domain', '')[:30],
                link.get('title', '')[:30]
            )
        
        console.print(table)
        
        # Show competitor domains
        if competitor_analysis['competitor_domains']:
            console.print("\n[yellow]🎯 Competitor Domains Found:[/yellow]")
            for domain in competitor_analysis['competitor_domains']:
                console.print(f"   • [red]{domain}[/red]")
    else:
        console.print("[yellow]No competitor links detected[/yellow]")
        console.print("[dim]Try analyzing the page structure for competitor mentions in the content[/dim]")
    
    # Show competitor keywords found in text
    if competitor_analysis['competitor_keywords_found']:
        console.print("\n[cyan]🔑 Competitor Keywords Found:[/cyan]")
        for keyword in competitor_analysis['competitor_keywords_found']:
            console.print(f"   • {keyword}")

def show_all_links(explorer: DOMExplorer):
    """Show ALL links with detailed information - no limits"""
    console.print()
    console.print(Panel("[bold cyan]📊 ALL LINKS ON PAGE[/bold cyan]", border_style="green"))
    
    link_map = explorer.map_links()
    
    # Show statistics
    stats_table = Table(title="Link Statistics", box=box.ROUNDED)
    stats_table.add_column("Type", style="cyan")
    stats_table.add_column("Count", style="green")
    stats_table.add_column("Unique", style="yellow")
    
    stats_table.add_row("Internal Links", 
                       str(len(link_map['internal_links'])),
                       str(link_map['unique_internal']))
    stats_table.add_row("External Links", 
                       str(len(link_map['external_links'])),
                       str(link_map['unique_external']))
    stats_table.add_row("Anchor Links", 
                       str(len(link_map['anchor_links'])),
                       str(len(set(l['href'] for l in link_map['anchor_links']))))
    stats_table.add_row("Competitor Links", 
                       str(len(link_map['competition_links'])),
                       "🎯")
    stats_table.add_row("Total", 
                       str(link_map['total_links']), 
                       "")
    
    console.print(stats_table)
    
    # Show competitor domains
    if link_map['competitor_domains']:
        console.print("\n[red]🎯 Competitor Domains:[/red]")
        for domain in link_map['competitor_domains']:
            console.print(f"   • {domain}")
    
    # Show ALL internal links - NO LIMIT
    console.print("\n[cyan]📌 ALL INTERNAL LINKS:[/cyan]")
    if link_map['internal_links']:
        # Show all internal links without limit
        for i, link in enumerate(link_map['internal_links'], 1):
            console.print(f"  {i}. {link.get('text', '')[:50]} → [cyan]{link.get('href', '')}[/cyan]")
        console.print(f"[dim]Total: {len(link_map['internal_links'])} internal links[/dim]")
    else:
        console.print("[dim]No internal links found[/dim]")
    
    # Show ALL external links - NO LIMIT
    console.print("\n[cyan]🌐 ALL EXTERNAL LINKS:[/cyan]")
    if link_map['external_links']:
        # Group external links by domain
        domain_groups = link_map['domain_groups']
        
        for domain, domain_links in sorted(domain_groups.items(), key=lambda x: len(x[1]), reverse=True):
            is_competitor = domain in link_map['competitor_domains']
            domain_color = "red" if is_competitor else "yellow"
            console.print(f"\n[bold]{domain_color}]📁 {domain}[/] ({len(domain_links)} links)")
            
            for link in domain_links:
                console.print(f"   • {link.get('text', '')[:40]} → [cyan]{link.get('href', '')}[/cyan]")
    else:
        console.print("[dim]No external links found[/dim]")
    
    # Show ALL competition links - NO LIMIT
    console.print("\n[yellow]🎯 ALL COMPETITOR LINKS:[/yellow]")
    if link_map['competition_links']:
        for i, link in enumerate(link_map['competition_links'], 1):
            console.print(f"  {i}. {link.get('text', '')[:40]} → [red]{link.get('href', '')}[/red] (Domain: {link.get('domain', '')})")
        console.print(f"[dim]Total: {len(link_map['competition_links'])} competitor links[/dim]")
    else:
        console.print("[dim]No competitor links detected[/dim]")
    
    # Option to navigate to a link
    if link_map['internal_links'] and Confirm.ask("Navigate to an internal link?"):
        # Show all internal links for navigation
        for i, link in enumerate(link_map['internal_links'], 1):
            console.print(f"  {i}. {link.get('text')[:40]}")
        
        link_num = int(Prompt.ask(f"Enter number (1-{len(link_map['internal_links'])})", default="1")) - 1
        if 0 <= link_num < len(link_map['internal_links']):
            url = link_map['internal_links'][link_num].get('href')
            if url:
                console.print(f"[cyan]Navigating to: {url}[/cyan]")
                explorer.page.navigate_to(url)
                console.print("[green]✅ Page loaded[/green]")

def main():
    console.clear()
    console.print(Panel("[bold cyan]🤖 Advanced Chrome Page Explorer[/bold cyan]", border_style="green"))
    console.print("[dim]DOM Explorer | Clickable Elements | Link Mapper | Competition Detection | AI Analysis[/dim]")
    console.print()

    analyzer = LlamaAnalyzer()

    port = int(Prompt.ask("Port", default="9236"))
    page = ChromePage(port)
    explorer = DOMExplorer(page)

    if not page.connect():
        return

    console.print(f"[green]✅ Connected to: {page.get_title()}[/green]")
    console.print(f"[dim]   {page.page_url}[/dim]")

    while True:
        console.print()
        console.print(Panel(f"[bold]Current: {page.get_title()[:60]}[/bold]", border_style="blue"))

        console.print("[cyan]📌 Options:[/cyan]")
        console.print("  1. Show Page Text")
        console.print("  2. Analyze with AI (llama.cpp)")
        console.print("  3. 📊 Show ALL Links")
        console.print("  4. 🎯 Show Competitor Links Only")
        console.print("  5. 🖱️ Find Clickable Elements")
        console.print("  6. 🏗️ Analyze Page Structure")
        console.print("  7. 📝 Extract Form Inputs")
        console.print("  8. 📄 Page Metadata")
        console.print("  9. 💾 Save Page Content")
        console.print("  0. Exit")

        choice = Prompt.ask("Select", choices=["0","1","2","3","4","5","6","7","8","9"])

        if choice == "0":
            break

        elif choice == "1":  # Show Page Text
            text = page.get_text()
            if text:
                console.print(Panel(text[:2000] + ("..." if len(text) > 2000 else ""),
                                   title="Page Text", border_style="blue"))
            else:
                console.print("[yellow]No text content[/yellow]")

        elif choice == "2":  # Analyze with AI
            if not analyzer.available:
                console.print("[red]❌ Llama.cpp not available[/red]")
                continue

            text = page.get_text()
            if not text:
                console.print("[yellow]No text to analyze[/yellow]")
                continue

            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                task = progress.add_task("Analyzing with AI...", total=None)
                result = analyzer.analyze(text)

            if result:
                console.print(Panel(result, title="AI Analysis Result", border_style="green"))
            else:
                console.print("[red]Analysis failed[/red]")

        elif choice == "3":  # Show ALL Links
            show_all_links(explorer)

        elif choice == "4":  # Show Competitor Links Only
            show_competition_links(explorer)

        elif choice == "5":  # Find Clickable Elements
            elements = page.get_clickable_elements()

            if not elements:
                console.print("[yellow]No clickable elements found[/yellow]")
                continue

            table = Table(title=f"Clickable Elements ({len(elements)})", box=box.ROUNDED)
            table.add_column("#", style="dim")
            table.add_column("Tag", style="cyan")
            table.add_column("Text", style="white")
            table.add_column("Action", style="green")
            table.add_column("Position", style="dim")

            for i, el in enumerate(elements[:20], 1):
                action = "click"
                if el.get('href'):
                    action = f"navigate: {el['href'][:20]}..."
                elif el.get('form_action'):
                    action = f"submit form: {el['form_action'][:20]}..."

                table.add_row(
                    str(i),
                    el.get('tag', ''),
                    el.get('text', '')[:30],
                    action[:25],
                    f"({el.get('position', {}).get('x', 0)}, {el.get('position', {}).get('y', 0)})"
                )

            console.print(table)

            if len(elements) > 20:
                console.print(f"[dim]... and {len(elements) - 20} more elements[/dim]")

            # Click on an element
            if Confirm.ask("Click on an element?"):
                el_num = int(Prompt.ask("Enter number", default="1")) - 1
                if 0 <= el_num < len(elements):
                    el = elements[el_num]
                    # Try to click by text or selector
                    if el.get('id'):
                        if page.click_element(f"#{el['id']}"):
                            console.print("[green]✅ Element clicked[/green]")
                    elif el.get('text') and el['text'] != '[No text]':
                        if page.click_by_text(el['text']):
                            console.print("[green]✅ Element clicked by text[/green]")
                        else:
                            console.print("[yellow]⚠️ Could not click element[/yellow]")
                    else:
                        console.print("[yellow]⚠️ Element has no clickable identifier[/yellow]")

        elif choice == "6":  # Analyze Page Structure
            structure = explorer.explore_page_structure()

            table = Table(title="Page Structure Analysis", box=box.ROUNDED)
            table.add_column("Section", style="cyan")
            table.add_column("Found", style="green")
            table.add_column("Details", style="white")

            for section, elements in structure.items():
                if elements:
                    detail = f"{len(elements)} elements found"
                    if len(elements) <= 3:
                        detail += f": {', '.join([e.get('text', '')[:20] for e in elements])}"
                    table.add_row(section.capitalize(), "✅", detail)
                else:
                    table.add_row(section.capitalize(), "❌", "Not found")

            console.print(table)

            # Show DOM tree
            if Confirm.ask("Show DOM tree (first 3 levels)?"):
                tree_data = page.get_dom_tree(max_depth=3)
                if tree_data:
                    tree = Tree(f"[bold]{tree_data.get('tag', 'root')}[/bold]")
                    def add_children(parent, children, max_display=10):
                        for i, child in enumerate(children[:max_display]):
                            branch = parent.add(f"{child.get('tag', '')} {child.get('id', '') or ''}")
                            if child.get('children'):
                                add_children(branch, child['children'], 5)
                        if len(children) > max_display:
                            parent.add(f"[dim]... and {len(children) - max_display} more[/dim]")

                    if tree_data.get('children'):
                        add_children(tree, tree_data['children'])
                    console.print(tree)

        elif choice == "7":  # Extract Form Inputs
            inputs = page.get_form_inputs()

            if not inputs:
                console.print("[yellow]No form inputs found[/yellow]")
                continue

            table = Table(title=f"Form Inputs ({len(inputs)})", box=box.ROUNDED)
            table.add_column("Type", style="cyan")
            table.add_column("Name", style="yellow")
            table.add_column("Value", style="green")
            table.add_column("Placeholder", style="dim")
            table.add_column("Required", style="red")

            for inp in inputs:
                table.add_row(
                    inp.get('type', ''),
                    inp.get('name', '')[:15],
                    inp.get('value', '')[:20],
                    inp.get('placeholder', '')[:15],
                    "✓" if inp.get('required') else ""
                )

            console.print(table)

            # Option to fill a form
            if Confirm.ask("Fill a form input?"):
                for i, inp in enumerate(inputs, 1):
                    console.print(f"  {i}. {inp.get('name')} ({inp.get('type')}) = {inp.get('value')}")

                inp_num = int(Prompt.ask("Enter input number", default="1")) - 1
                if 0 <= inp_num < len(inputs):
                    inp = inputs[inp_num]
                    value = Prompt.ask(f"Enter value for {inp.get('name')}")
                    # JavaScript to set value
                    script = f"""
                    const inputs = document.querySelectorAll('input[name="{inp.get('name')}"], input[type="{inp.get('type')}"]');
                    inputs.forEach(el => {{
                        if (el.type === 'checkbox' || el.type === 'radio') {{
                            el.checked = true;
                        }} else {{
                            el.value = '{value}';
                        }}
                    }});
                    """
                    page.js(script)
                    console.print("[green]✅ Input filled[/green]")

        elif choice == "8":  # Page Metadata
            metadata = page.get_page_metadata()

            table = Table(title="Page Metadata", box=box.ROUNDED)
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="white")

            for key, value in metadata.items():
                if isinstance(value, (int, bool)):
                    display = str(value)
                else:
                    display = value[:60] + ("..." if len(str(value)) > 60 else "")
                table.add_row(key.replace('_', ' ').title(), display)

            console.print(table)

        elif choice == "9":  # Save Page Content
            text = page.get_text()
            if not text:
                console.print("[yellow]No text to save[/yellow]")
                continue

            timestamp = int(time.time())

            # Save text
            filename = f"page_{timestamp}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"Title: {page.get_title()}\n")
                f.write(f"URL: {page.page_url}\n")
                f.write(f"Timestamp: {time.ctime()}\n")
                f.write("=" * 50 + "\n\n")
                f.write(text)
            console.print(f"[green]✅ Saved text to {filename}[/green]")

            # Save full HTML
            html_filename = f"page_{timestamp}.html"
            with open(html_filename, 'w', encoding='utf-8') as f:
                f.write(page.get_html())
            console.print(f"[green]✅ Saved HTML to {html_filename}[/green]")

            # Save structured data with competition analysis
            link_map = explorer.map_links()
            competitor_analysis = explorer.get_competitor_analysis()
            
            json_data = {
                "title": page.get_title(),
                "url": page.page_url,
                "timestamp": time.time(),
                "metadata": page.get_page_metadata(),
                "links": {
                    "all": page.get_all_links(),
                    "internal": link_map['internal_links'],
                    "external": link_map['external_links'],
                    "competitor": competitor_analysis['competitor_links']
                },
                "competitor_analysis": competitor_analysis,
                "clickable_elements": page.get_clickable_elements(),
                "form_inputs": page.get_form_inputs(),
                "text": text
            }

            json_filename = f"page_{timestamp}.json"
            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2)
            console.print(f"[green]✅ Saved structured data to {json_filename}[/green]")

        if choice != "0":
            console.print()
            input("Press Enter to continue...")

    page.close()
    console.print("[green]Goodbye! 👋[/green]")

if __name__ == "__main__":
    main()
