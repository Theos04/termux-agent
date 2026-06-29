#!/usr/bin/env python3
"""
Chrome Page Analyzer with llama.cpp Integration
Scrapes page content and uses AI to analyze opportunities
"""

import json
import websocket
import requests
import sys
import time
import subprocess
import os
from typing import Optional, Dict, List, Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import box
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

# ============================================================================
# Chrome Page Client
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
    
    def get_html(self):
        return self.js("document.documentElement.outerHTML") or ""
    
    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except:
                pass

# ============================================================================
# Llama.cpp Integration
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
        
        # Try to find in common locations
        try:
            result = subprocess.run(["which", "llama-cli"], capture_output=True)
            if result.returncode == 0:
                return result.stdout.decode().strip()
        except:
            pass
        
        return None
    
    def _find_model(self):
        """Find a GGUF model"""
        possible_paths = [
            "./llama.cpp/models/*.gguf",
            "~/llama.cpp/models/*.gguf",
            "./*.gguf",
            "~/*.gguf"
        ]
        
        import glob
        for pattern in possible_paths:
            expanded = os.path.expanduser(pattern)
            matches = glob.glob(expanded)
            if matches:
                return matches[0]
        
        return None
    
    def analyze(self, text: str, prompt_template: str = None) -> str:
        """Analyze text using llama.cpp"""
        if not self.available:
            return "Llama.cpp not available"
        
        if not text:
            return "No text to analyze"
        
        # Truncate text if too long
        if len(text) > 4000:
            text = text[:4000] + "..."
        
        if prompt_template is None:
            prompt_template = """Analyze this job/internship opportunity and provide:

1. Company name
2. Position title
3. Type: (Full-time, Internship, Contract, etc.)
4. Payment: (Paid/Unpaid/Unknown) with amount if mentioned
5. Location: (Remote/On-site/Hybrid)
6. Requirements: List key skills/qualifications needed
7. Apply by date if mentioned
8. Summary: Brief 2-3 sentence summary

Opportunity text:
{text}

Format your response as structured bullet points."""
        
        prompt = prompt_template.replace("{text}", text)
        
        try:
            # Build command
            cmd = [
                self.llama_bin,
                "-m", self.model_path,
                "-p", prompt,
                "-n", "512",  # Generate up to 512 tokens
                "-t", "4",    # 4 threads
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
# Main Tool
# ============================================================================

def main():
    console.clear()
    console.print(Panel("[bold cyan]🤖 Chrome Page Analyzer with AI[/bold cyan]", border_style="green"))
    
    # Check llama.cpp
    analyzer = LlamaAnalyzer()
    
    port = int(Prompt.ask("Port", default="9236"))
    page = ChromePage(port)
    
    if not page.connect():
        return
    
    console.print(f"[green]✅ Connected to: {page.get_title()}[/green]")
    
    while True:
        console.print()
        console.print(Panel(f"[bold]Current: {page.get_title()[:60]}[/bold]", border_style="blue"))
        
        console.print("[cyan]📌 Options:[/cyan]")
        console.print("  1. Show Page Text")
        console.print("  2. Analyze with AI (llama.cpp)")
        console.print("  3. Custom Prompt Analysis")
        console.print("  4. Extract Job/Internship Details")
        console.print("  5. Check Paid/Unpaid Status")
        console.print("  6. Save Page Content")
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
        
        elif choice == "2":  # Analyze with AI
            if not analyzer.available:
                console.print("[red]❌ Llama.cpp not available[/red]")
                console.print("[yellow]Please install llama.cpp and download a GGUF model[/yellow]")
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
        
        elif choice == "3":  # Custom Prompt
            if not analyzer.available:
                console.print("[red]❌ Llama.cpp not available[/red]")
                continue
            
            console.print("[cyan]Enter custom prompt (use {text} for page content):[/cyan]")
            prompt = Prompt.ask("Prompt", default="Analyze this opportunity: {text}")
            
            text = page.get_text()
            if not text:
                console.print("[yellow]No text to analyze[/yellow]")
                continue
            
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                task = progress.add_task("Analyzing with custom prompt...", total=None)
                result = analyzer.analyze(text, prompt)
            
            if result:
                console.print(Panel(result, title="AI Analysis Result", border_style="green"))
            else:
                console.print("[red]Analysis failed[/red]")
        
        elif choice == "4":  # Extract Job/Internship Details
            text = page.get_text()
            if not text:
                console.print("[yellow]No text to extract[/yellow]")
                continue
            
            # Try to extract details using simple heuristics first
            details = {
                "title": page.get_title(),
                "url": page.page_url,
                "text_preview": text[:500]
            }
            
            # Look for payment info
            payment_keywords = ["stipend", "salary", "₹", "Rs", "INR", "payment", "paid", "unpaid"]
            payment_found = []
            for kw in payment_keywords:
                if kw in text.lower():
                    payment_found.append(kw)
            
            details["payment_indicators"] = payment_found
            
            # Look for location
            location_keywords = ["remote", "work from home", "hybrid", "in office", "location", "city", "bangalore", "mumbai", "delhi"]
            location_found = []
            for kw in location_keywords:
                if kw in text.lower():
                    location_found.append(kw)
            
            details["location_indicators"] = location_found
            
            console.print(Panel(json.dumps(details, indent=2), title="Extracted Details", border_style="cyan"))
            
            # Try AI analysis if available
            if analyzer.available and Confirm.ask("Also analyze with AI?"):
                prompt = """Extract the following information from this job/internship description and format as JSON:
- company_name
- position_title
- type (Full-time/Internship/Contract)
- payment (Paid/Unpaid/Unknown)
- payment_amount (if mentioned)
- location
- requirements (list)
- apply_by_date

Text: {text}

Return only valid JSON."""
                
                with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                    task = progress.add_task("Analyzing...", total=None)
                    result = analyzer.analyze(text, prompt)
                
                if result:
                    console.print(Panel(result, title="AI Extracted Details", border_style="green"))
        
        elif choice == "5":  # Check Paid/Unpaid Status
            text = page.get_text()
            if not text:
                console.print("[yellow]No text to check[/yellow]")
                continue
            
            # Quick check for payment indicators
            paid_indicators = ["stipend", "salary", "₹", "Rs", "INR", "paid", "compensation", "remuneration"]
            unpaid_indicators = ["unpaid", "volunteer", "no stipend", "without pay", "expense only"]
            
            text_lower = text.lower()
            
            is_paid = any(kw in text_lower for kw in paid_indicators)
            is_unpaid = any(kw in text_lower for kw in unpaid_indicators)
            
            console.print("[bold]Payment Status Check:[/bold]")
            if is_paid and not is_unpaid:
                console.print("[green]✅ Likely PAID[/green]")
                console.print(f"[dim]Found indicators: {[kw for kw in paid_indicators if kw in text_lower]}[/dim]")
            elif is_unpaid and not is_paid:
                console.print("[red]❌ Likely UNPAID[/red]")
                console.print(f"[dim]Found indicators: {[kw for kw in unpaid_indicators if kw in text_lower]}[/dim]")
            else:
                console.print("[yellow]⚠️ Ambiguous or no payment info found[/yellow]")
                if is_paid:
                    console.print(f"[dim]Paid indicators: {[kw for kw in paid_indicators if kw in text_lower]}[/dim]")
                if is_unpaid:
                    console.print(f"[dim]Unpaid indicators: {[kw for kw in unpaid_indicators if kw in text_lower]}[/dim]")
            
            # AI analysis if available
            if analyzer.available and Confirm.ask("Get AI analysis of payment?"):
                prompt = """Analyze this job/internship posting and determine if it's paid or unpaid. 
If paid, mention the amount if specified. Include:
- Payment status: (Paid/Unpaid/Unknown)
- Amount: (if mentioned)
- Evidence: (what text indicates this)

Text: {text}"""
                
                with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                    task = progress.add_task("Analyzing...", total=None)
                    result = analyzer.analyze(text, prompt)
                
                if result:
                    console.print(Panel(result, title="AI Payment Analysis", border_style="green"))
        
        elif choice == "6":  # Save Page Content
            text = page.get_text()
            if not text:
                console.print("[yellow]No text to save[/yellow]")
                continue
            
            filename = f"page_{int(time.time())}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"Title: {page.get_title()}\n")
                f.write(f"URL: {page.page_url}\n")
                f.write("=" * 50 + "\n\n")
                f.write(text)
            
            console.print(f"[green]✅ Saved to {filename}[/green]")
            
            # Also save as JSON
            json_filename = f"page_{int(time.time())}.json"
            data = {
                "title": page.get_title(),
                "url": page.page_url,
                "timestamp": time.time(),
                "text": text
            }
            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            console.print(f"[green]✅ Saved JSON to {json_filename}[/green]")
        
        if choice != "0":
            console.print()
            input("Press Enter to continue...")
    
    page.close()
    console.print("[green]Goodbye! 👋[/green]")

if __name__ == "__main__":
    main()
