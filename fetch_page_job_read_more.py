#!/usr/bin/env python3
"""
Chrome Page Analyzer - Enhanced with Auto-Expand
Handles "Read More" buttons and extracts full content
"""

import json
import websocket
import requests
import sys
import time
import re
from typing import Optional, Dict, List, Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import box
from rich.text import Text

console = Console()

# ============================================================================
# Chrome Page Client with Click Support
# ============================================================================

class ChromePage:
    def __init__(self, port=9236):
        self.port = port
        self.ws = None
        self.connected = False
        self.page_title = ""
        self.page_url = ""
    
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
    
    def js(self, script, await_promise=False):
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
                resp = self.ws.recv()
                data = json.loads(resp)
                if data.get('id') == cmd_id:
                    result = data.get('result', {})
                    if 'result' in result:
                        return result['result'].get('value')
                    return None
            except:
                pass
        
        return None
    
    def get_text(self):
        return self.js("document.body ? document.body.innerText : ''") or ""
    
    def get_title(self):
        return self.js("document.title") or "No title"
    
    def click(self, selector):
        """Click an element by CSS selector"""
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
    
    def find_elements(self, selector):
        """Find elements by CSS selector"""
        script = f"""
        (function() {{
            const els = document.querySelectorAll('{selector}');
            return Array.from(els).map(el => ({{
                tag: el.tagName,
                text: (el.textContent || '').trim().slice(0, 100),
                id: el.id || '',
                class: el.className || '',
                visible: el.offsetParent !== null,
                innerHTML: el.innerHTML ? el.innerHTML.slice(0, 200) : ''
            }}));
        }})()
        """
        return self.js(script) or []
    
    def expand_page(self):
        """Find and click all 'Read More', 'Show More' buttons"""
        # Try multiple selectors for expand buttons
        selectors = [
            'button:contains("Read More")',
            'button:contains("Show More")',
            'button:contains("Read more")',
            '.read-more-btn',
            '.show-more-btn',
            '[class*="read-more"]',
            '[class*="show-more"]',
            'button[aria-expanded="false"]'
        ]
        
        clicked = False
        for selector in selectors:
            try:
                # Check if element exists
                elements = self.find_elements(selector)
                if elements and elements[0].get('visible'):
                    # Click it
                    if self.click(selector):
                        console.print("[green]✅ Clicked 'Read More' button[/green]")
                        clicked = True
                        # Wait for content to load
                        time.sleep(1)
            except:
                pass
        
        return clicked
    
    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except:
                pass

# ============================================================================
# Smart Extractor - Enhanced
# ============================================================================

class SmartExtractor:
    def __init__(self):
        self.payment_patterns = {
            'paid': [
                r'stipend.*?[₹Rs][\d,]+',
                r'salary.*?[₹Rs][\d,]+',
                r'[₹Rs][\d,]+.*?(?:per|month|monthly)',
                r'paid.*?(?:internship|job)',
                r'compensation.*?[₹Rs][\d,]+',
                r'remuneration.*?[₹Rs][\d,]+',
                r'₹[\d,]+',
                r'Rs[\d,]+',
                r'\$[\d,]+'
            ],
            'unpaid': [
                r'unpaid',
                r'no stipend',
                r'without pay',
                r'volunteer',
                r'expense.*?only',
                r'not.*?paid'
            ]
        }
        
        self.location_patterns = {
            'remote': [r'remote', r'work from home', r'wfh', r'virtual'],
            'onsite': [r'on.?site', r'in.?office', r'office', r'hyderabad', r'bangalore', r'mumbai', r'delhi', r'gurgaon'],
            'hybrid': [r'hybrid', r'partially remote']
        }
    
    def extract(self, text: str) -> Dict:
        """Extract structured data from text"""
        result = {
            'title': '',
            'company': '',
            'payment_status': 'Unknown',
            'payment_amount': '',
            'location': 'Unknown',
            'location_type': 'Unknown',
            'requirements': [],
            'deadline': '',
            'type': 'Unknown',
            'responsibilities': [],
            'summary': ''
        }
        
        lines = text.split('\n')
        
        # Extract title from first few lines
        title_lines = []
        for line in lines[:15]:
            clean = line.strip()
            if clean and len(clean) > 5 and not clean.lower() in ['home', 'jobs', 'internships', 'competitions', 'mentorship']:
                title_lines.append(clean)
        result['title'] = ' '.join(title_lines[:3])[:120]
        
        # Extract company
        for line in lines[:20]:
            if 'at' in line.lower() and len(line.strip()) < 80:
                parts = line.split('at')
                if len(parts) > 1:
                    result['company'] = parts[1].strip()
                    break
        
        # Payment status
        text_lower = text.lower()
        result['payment_status'] = 'Unknown'
        result['payment_amount'] = ''
        
        for pattern in self.payment_patterns['paid']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result['payment_status'] = 'Paid'
                result['payment_amount'] = match.group(0)
                break
        
        if result['payment_status'] == 'Unknown':
            for pattern in self.payment_patterns['unpaid']:
                if re.search(pattern, text_lower):
                    result['payment_status'] = 'Unpaid'
                    break
        
        # Location
        for loc_type, patterns in self.location_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    result['location_type'] = loc_type.capitalize()
                    # Find specific location
                    for line in lines:
                        if any(p in line.lower() for p in patterns):
                            clean = line.strip()
                            if clean and len(clean) < 100:
                                result['location'] = clean
                            break
                    break
            if result['location_type'] != 'Unknown':
                break
        
        # Extract requirements
        req_section = re.search(r'(?:requirement|skill|qualification)s?:?\s*(.*?)(?:\n\n|\n[A-Z]|\Z)', text, re.IGNORECASE | re.DOTALL)
        if req_section:
            req_text = req_section.group(1)
            items = re.split(r'[·•\n•]', req_text)
            for item in items:
                clean = item.strip()
                if clean and len(clean) > 5 and not clean.startswith(('•', '·')):
                    result['requirements'].append(clean[:150])
        
        # If no requirements found, try looking for bullet points
        if not result['requirements']:
            bullet_pattern = r'[•·]\s*([^\n•·]+)'
            matches = re.findall(bullet_pattern, text)
            for match in matches[:10]:
                clean = match.strip()
                if clean and len(clean) > 5:
                    result['requirements'].append(clean[:150])
        
        # Extract responsibilities
        resp_section = re.search(r'(?:responsibilities|role|what you\'ll do):?\s*(.*?)(?:\n\n|\n[A-Z]|\Z)', text, re.IGNORECASE | re.DOTALL)
        if resp_section:
            resp_text = resp_section.group(1)
            items = re.split(r'[·•\n]', resp_text)
            for item in items[:5]:
                clean = item.strip()
                if clean and len(clean) > 10:
                    result['responsibilities'].append(clean[:150])
        
        # Type detection
        if 'internship' in text_lower:
            result['type'] = 'Internship'
        elif 'job' in text_lower:
            result['type'] = 'Job'
        elif 'hackathon' in text_lower or 'competition' in text_lower:
            result['type'] = 'Competition'
        
        # Deadline
        date_patterns = [
            r'(\d{1,2}\s+[A-Za-z]+\s+\d{2,4})',
            r'([A-Za-z]+\s+\d{1,2},\s+\d{4})',
            r'(\d{2}/\d{2}/\d{4})',
            r'(\d{4}-\d{2}-\d{2})',
            r'(\d{1,2}\s+[A-Za-z]+\s+\d{2,4})'
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                result['deadline'] = match.group(1)
                break
        
        return result
    
    def format_result(self, data: Dict) -> str:
        """Format extracted data as a nice string"""
        output = []
        output.append("[bold cyan]📋 Extracted Information[/bold cyan]")
        output.append("")
        
        if data.get('title'):
            output.append(f"[bold]Position:[/bold] {data['title']}")
        if data.get('company'):
            output.append(f"[bold]Company:[/bold] {data['company']}")
        if data.get('type'):
            output.append(f"[bold]Type:[/bold] {data['type']}")
        
        payment = data.get('payment_status', 'Unknown')
        if payment == 'Paid':
            payment_text = f"[green]✅ {payment}[/green]"
        elif payment == 'Unpaid':
            payment_text = f"[red]❌ {payment}[/red]"
        else:
            payment_text = f"[yellow]⚠️ {payment}[/yellow]"
        output.append(f"[bold]Payment:[/bold] {payment_text}")
        
        if data.get('payment_amount'):
            output.append(f"[bold]Amount:[/bold] {data['payment_amount']}")
        
        if data.get('location_type') != 'Unknown':
            output.append(f"[bold]Location:[/bold] {data['location_type']} - {data.get('location', 'N/A')}")
        elif data.get('location'):
            output.append(f"[bold]Location:[/bold] {data['location']}")
        
        if data.get('deadline'):
            output.append(f"[bold]Apply By:[/bold] {data['deadline']}")
        
        if data.get('requirements'):
            output.append("")
            output.append("[bold]Requirements:[/bold]")
            for req in data['requirements'][:5]:
                output.append(f"  • {req}")
        
        if data.get('responsibilities'):
            output.append("")
            output.append("[bold]Responsibilities:[/bold]")
            for resp in data['responsibilities'][:5]:
                output.append(f"  • {resp}")
        
        return '\n'.join(output)

# ============================================================================
# Main Tool
# ============================================================================

def main():
    console.clear()
    console.print(Panel("[bold cyan]🔍 Chrome Page Analyzer - Enhanced[/bold cyan]", border_style="green"))
    
    port = int(Prompt.ask("Port", default="9236"))
    page = ChromePage(port)
    extractor = SmartExtractor()
    
    if not page.connect():
        return
    
    console.print(f"[green]✅ Connected to: {page.get_title()}[/green]")
    
    # Auto-expand on first load
    console.print("[dim]Checking for 'Read More' buttons...[/dim]")
    if page.expand_page():
        console.print("[green]✅ Page expanded![/green]")
        time.sleep(1)
    
    while True:
        console.print()
        console.print(Panel(f"[bold]Current: {page.get_title()[:60]}[/bold]", border_style="blue"))
        
        console.print("[cyan]📌 Options:[/cyan]")
        console.print("  1. Show Page Text")
        console.print("  2. 📊 Extract Opportunity Details")
        console.print("  3. 💰 Check Paid/Unpaid Status")
        console.print("  4. 📋 List All Requirements")
        console.print("  5. 🔄 Expand Page (Read More)")
        console.print("  6. 💾 Save Page Content")
        console.print("  0. Exit")
        
        choice = Prompt.ask("Select", choices=["0","1","2","3","4","5","6"])
        
        if choice == "0":
            break
        
        elif choice == "1":  # Show Page Text
            text = page.get_text()
            if text:
                console.print(Panel(text[:2000] + ("..." if len(text) > 2000 else ""), 
                                   title="Page Text", border_style="blue"))
            else:
                console.print("[yellow]No text content[/yellow]")
        
        elif choice == "2":  # Extract Details
            text = page.get_text()
            if not text:
                console.print("[yellow]No text to extract[/yellow]")
                continue
            
            with console.status("[bold green]Extracting details...[/bold green]"):
                data = extractor.extract(text)
            
            console.print()
            console.print(Panel(extractor.format_result(data), title="Extracted Details", border_style="cyan"))
            
            if Confirm.ask("Show raw extracted data (JSON)?"):
                console.print(Panel(json.dumps(data, indent=2), title="Raw Data", border_style="green"))
        
        elif choice == "3":  # Check Paid/Unpaid
            text = page.get_text()
            if not text:
                console.print("[yellow]No text to check[/yellow]")
                continue
            
            data = extractor.extract(text)
            
            console.print()
            console.print("[bold]💰 Payment Status:[/bold]")
            
            status = data.get('payment_status', 'Unknown')
            if status == 'Paid':
                console.print("[green]✅ PAID opportunity![/green]")
                if data.get('payment_amount'):
                    console.print(f"[green]   Amount: {data['payment_amount']}[/green]")
            elif status == 'Unpaid':
                console.print("[red]❌ UNPAID opportunity[/red]")
                console.print("[yellow]   Consider if the experience is worth it[/yellow]")
            else:
                console.print("[yellow]⚠️ Could not determine payment status[/yellow]")
            
            console.print()
            console.print("[dim]Evidence found:[/dim]")
            if data.get('payment_amount'):
                console.print(f"[dim]  • {data['payment_amount']}[/dim]")
            text_lower = text.lower()
            keywords = ['stipend', 'salary', 'paid', 'unpaid', '₹', 'Rs', '$']
            found = [kw for kw in keywords if kw in text_lower]
            if found:
                console.print(f"[dim]  • Keywords found: {', '.join(found)}[/dim]")
        
        elif choice == "4":  # List Requirements
            text = page.get_text()
            if not text:
                console.print("[yellow]No text to process[/yellow]")
                continue
            
            data = extractor.extract(text)
            
            if data.get('requirements'):
                console.print(f"[bold green]📋 Requirements ({len(data['requirements'])} found):[/bold green]")
                console.print()
                for i, req in enumerate(data['requirements'], 1):
                    console.print(f"  {i}. {req}")
            else:
                console.print("[yellow]No requirements found[/yellow]")
                console.print("[dim]Try option 5 to expand the page first[/dim]")
        
        elif choice == "5":  # Expand Page
            console.print("[dim]Looking for 'Read More' buttons...[/dim]")
            if page.expand_page():
                console.print("[green]✅ Page expanded![/green]")
                # Re-extract after expansion
                text = page.get_text()
                data = extractor.extract(text)
                console.print("[dim]New text length: {} characters[/dim]".format(len(text)))
            else:
                console.print("[yellow]No expandable content found[/yellow]")
        
        elif choice == "6":  # Save Page Content
            text = page.get_text()
            if not text:
                console.print("[yellow]No text to save[/yellow]")
                continue
            
            data = extractor.extract(text)
            
            filename = f"page_{int(time.time())}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"Title: {page.get_title()}\n")
                f.write(f"URL: {page.page_url}\n")
                f.write(f"Company: {data.get('company', 'N/A')}\n")
                f.write(f"Position: {data.get('title', 'N/A')}\n")
                f.write(f"Type: {data.get('type', 'N/A')}\n")
                f.write(f"Payment: {data.get('payment_status', 'Unknown')}\n")
                f.write("=" * 60 + "\n\n")
                f.write(text)
            
            console.print(f"[green]✅ Saved to {filename}[/green]")
        
        if choice != "0":
            console.print()
            input("Press Enter to continue...")
    
    page.close()
    console.print("[green]Goodbye! 👋[/green]")

if __name__ == "__main__":
    main()
