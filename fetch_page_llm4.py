#!/usr/bin/env python3
"""
Competition Scout - Automatically crawls competition pages and evaluates worthiness
Goes through all competition links, extracts details, and ranks them
"""

import json
import websocket
import requests
import sys
import time
import subprocess
import os
import re
from typing import Optional, Dict, List, Any, Set
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
import rich.box as box
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.tree import Tree
from rich.text import Text
from urllib.parse import urljoin, urlparse
from datetime import datetime
from collections import defaultdict

console = Console()

class ChromePage:
    def __init__(self, port=9236):
        self.port = port
        self.ws = None
        self.connected = False
        self.page_title = ""
        self.page_url = ""
        self.base_domain = ""

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
                        return None
                    return None
            except:
                pass

        return None

    def get_text(self):
        return self.js("document.body ? document.body.innerText : ''") or ""

    def get_title(self):
        return self.js("document.title") or "No title"

    def get_all_links(self) -> List[Dict[str, str]]:
        script = """
        (function() {
            const links = [];
            const elements = document.querySelectorAll('a[href]');
            elements.forEach(el => {
                const href = el.getAttribute('href');
                const text = el.textContent.trim() || '[No text]';
                links.push({
                    href: href,
                    text: text
                });
            });
            return links;
        })()
        """
        result = self.js(script)
        return result if result else []

    def navigate_to(self, url: str) -> bool:
        script = f"""
        (function() {{
            window.location.href = '{url}';
            return true;
        }})()
        """
        self.js(script)
        time.sleep(3)
        return True

    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except:
                pass

class CompetitionScout:
    def __init__(self, page: ChromePage):
        self.page = page
        self.competitions = []
        self.cost_keywords = ['₹', 'Rs', 'fee', 'pay', 'price', 'cost', 'registration', 'amount']
        self.free_keywords = ['free', 'no fee', 'no cost', 'free entry', '₹0', 'Rs. 0', 'free registration']
        self.worth_keywords = ['prize', 'reward', 'cash', 'winner', 'incentive', 'PPO', 'internship', 'pre-placement']
        self.excluded_keywords = ['apply now', 'register now', 'view details', 'read more']

    def extract_competition_details(self, text: str) -> Dict:
        """Extract competition details from page text"""
        details = {
            'has_registration_fee': False,
            'fee_amount': None,
            'prize_money': None,
            'has_internship': False,
            'has_ppo': False,
            'has_certificate': False,
            'is_free': False,
            'deadline': None,
            'team_size': None,
            'worth_score': 0,
            'reasons_to_apply': []
        }

        text_lower = text.lower()
        
        # Check if it's free
        for keyword in self.free_keywords:
            if keyword in text_lower:
                details['is_free'] = True
                details['reasons_to_apply'].append("Free registration")
                break
        
        # Check for registration fee
        for keyword in self.cost_keywords:
            if keyword in text_lower:
                # Try to extract amount
                fee_match = re.search(r'[₹Rs. ]*([\d,]+)\s*(?:Rs|₹|rupees)?', text)
                if fee_match:
                    amount = fee_match.group(1).replace(',', '')
                    if amount.isdigit() and int(amount) > 0:
                        details['has_registration_fee'] = True
                        details['fee_amount'] = int(amount)
                        if int(amount) > 500:
                            details['reasons_to_apply'].append(f"Registration fee: ₹{amount} (consider if worth it)")
                        else:
                            details['reasons_to_apply'].append(f"Low registration fee: ₹{amount}")
        
        # Check for prize money
        prize_match = re.search(r'prize[:\s]*[₹Rs. ]*([\d,]+)', text_lower)
        if prize_match:
            amount = prize_match.group(1).replace(',', '')
            if amount.isdigit():
                details['prize_money'] = int(amount)
                if int(amount) > 10000:
                    details['reasons_to_apply'].append(f"💰 Prize: ₹{int(amount):,}")
                    details['worth_score'] += 3
                elif int(amount) > 5000:
                    details['reasons_to_apply'].append(f"💰 Prize: ₹{int(amount):,}")
                    details['worth_score'] += 2
                else:
                    details['reasons_to_apply'].append(f"💰 Prize: ₹{int(amount):,}")
                    details['worth_score'] += 1
        
        # Check for internship/PPO
        if 'internship' in text_lower or 'ppo' in text_lower or 'pre-placement' in text_lower:
            details['has_internship'] = True
            details['reasons_to_apply'].append("🚀 Internship/PPO opportunity")
            details['worth_score'] += 3
        
        # Check for certificate
        if 'certificate' in text_lower or 'certified' in text_lower:
            details['has_certificate'] = True
            details['reasons_to_apply'].append("📜 Certificate provided")
            details['worth_score'] += 1
        
        # Check for team size
        team_match = re.search(r'team\s*(?:size)?\s*[:.\s]*([\d-]+)', text_lower)
        if team_match:
            details['team_size'] = team_match.group(1)
            details['reasons_to_apply'].append(f"👥 Team size: {details['team_size']}")
        
        # Check for deadline
        deadline_match = re.search(r'(?:deadline|last date|ends|closing date)[:\s]*([\d\s\w,]+)', text_lower)
        if deadline_match:
            details['deadline'] = deadline_match.group(1).strip()
            details['reasons_to_apply'].append(f"⏰ Deadline: {details['deadline']}")
        
        # Check for featured/prestige indicators
        if 'featured' in text_lower:
            details['worth_score'] += 1
            details['reasons_to_apply'].append("⭐ Featured competition")
        
        if 'top' in text_lower and 'company' in text_lower:
            details['worth_score'] += 1
            details['reasons_to_apply'].append("🏆 Top company participation")
        
        # Bonus: Check if it's free and has good prize
        if details['is_free'] and details['prize_money'] and details['prize_money'] > 5000:
            details['worth_score'] += 2
            details['reasons_to_apply'].append("💎 Free entry + Good prize!")
        
        return details

    def is_competition_page(self, url: str) -> bool:
        """Check if the URL is a competition page"""
        competition_patterns = [
            '/competitions/',
            '/hackathons/',
            '/quiz/',
            '/challenge/'
        ]
        return any(pattern in url for pattern in competition_patterns)

    def get_worth_status(self, details: Dict) -> tuple:
        """Get a worthiness status and color"""
        score = details.get('worth_score', 0)
        
        # If it's free and has any prize or internship, it's highly recommended
        if details.get('is_free') and (details.get('prize_money', 0) > 0 or details.get('has_internship')):
            return "🔥 HOT", "red", score + 2
        
        if score >= 5:
            return "🌟 HIGHLY RECOMMENDED", "green", score
        elif score >= 3:
            return "✅ RECOMMENDED", "yellow", score
        elif score >= 1:
            return "🔍 WORTH CHECKING", "blue", score
        else:
            return "❌ SKIP", "dim", score

    def analyze_competition(self, url: str) -> Dict:
        """Navigate to a competition URL and analyze it"""
        console.print(f"[dim]📊 Analyzing: {url[:60]}...[/dim]")
        
        try:
            self.page.navigate_to(url)
            time.sleep(2)
            
            title = self.page.get_title()
            text = self.page.get_text()
            
            # Skip if it's not a competition page
            if not self.is_competition_page(url):
                return None
            
            # Extract details
            details = self.extract_competition_details(text)
            status, color, score = self.get_worth_status(details)
            
            result = {
                'url': url,
                'title': title,
                'status': status,
                'color': color,
                'score': score,
                'is_free': details.get('is_free', False),
                'fee': details.get('fee_amount', None),
                'prize': details.get('prize_money', None),
                'has_internship': details.get('has_internship', False),
                'has_ppo': details.get('has_ppo', False),
                'has_certificate': details.get('has_certificate', False),
                'deadline': details.get('deadline', None),
                'team_size': details.get('team_size', None),
                'reasons': details.get('reasons_to_apply', []),
                'worth_score': score
            }
            
            return result
            
        except Exception as e:
            console.print(f"[red]Error analyzing {url}: {e}[/red]")
            return None

class CompetitionScoutApp:
    def __init__(self, port=9236):
        self.page = ChromePage(port)
        self.scout = CompetitionScout(self.page)
        self.analyzed_competitions = []

    def run(self):
        console.clear()
        console.print(Panel("[bold green]🎯 COMPETITION SCOUT[/bold green]", border_style="green"))
        console.print("[dim]Automatically finds and evaluates free competitions worth your time[/dim]")
        console.print()

        port = int(Prompt.ask("Chrome Port", default="9236"))
        self.page = ChromePage(port)
        self.scout = CompetitionScout(self.page)

        if not self.page.connect():
            console.print("[red]❌ Could not connect to Chrome[/red]")
            return

        console.print(f"[green]✅ Connected to: {self.page.get_title()}[/green]")
        console.print(f"[dim]   {self.page.page_url}[/dim]")

        while True:
            console.print()
            console.print(Panel("[bold cyan]📋 What do you want to do?[/bold cyan]", border_style="blue"))
            
            console.print("[cyan]Options:[/cyan]")
            console.print("  1. 🔍 Find all competition links on current page")
            console.print("  2. 🤖 Auto-analyze all competitions (recommended)")
            console.print("  3. 📊 View analyzed competitions")
            console.print("  4. 💾 Save results to file")
            console.print("  5. 🗑️  Clear analyzed list")
            console.print("  6. 🌐 Go to a specific competition URL")
            console.print("  0. Exit")

            choice = Prompt.ask("Select", choices=["0","1","2","3","4","5","6"])

            if choice == "0":
                break

            elif choice == "1":  # Find competition links
                self.find_competition_links()

            elif choice == "2":  # Auto-analyze
                self.auto_analyze()

            elif choice == "3":  # View results
                self.view_results()

            elif choice == "4":  # Save results
                self.save_results()

            elif choice == "5":  # Clear
                self.analyzed_competitions = []
                console.print("[green]✅ Cleared analyzed list[/green]")

            elif choice == "6":  # Go to specific URL
                url = Prompt.ask("Enter competition URL")
                if url:
                    self.page.navigate_to(url)
                    console.print("[green]✅ Navigated to URL[/green]")

    def find_competition_links(self):
        """Find all competition links on the current page"""
        console.print("[cyan]🔍 Finding competition links...[/cyan]")
        
        links = self.page.get_all_links()
        competition_links = []
        
        for link in links:
            href = link.get('href', '')
            if self.scout.is_competition_page(href):
                competition_links.append({
                    'url': href,
                    'text': link.get('text', '')
                })
        
        if competition_links:
            console.print(f"[green]✅ Found {len(competition_links)} competition links[/green]")
            
            table = Table(title="Competition Links", box=box.ROUNDED)
            table.add_column("#", style="dim")
            table.add_column("Name", style="white")
            table.add_column("URL", style="cyan")
            
            for i, link in enumerate(competition_links[:20], 1):
                table.add_row(
                    str(i),
                    link['text'][:40] if link['text'] != '[No text]' else "Competition",
                    link['url'][:50]
                )
            
            console.print(table)
            
            if len(competition_links) > 20:
                console.print(f"[dim]... and {len(competition_links) - 20} more[/dim]")
            
            # Option to analyze all
            if Confirm.ask("Analyze all these competitions?"):
                self.analyze_competition_links(competition_links)
        else:
            console.print("[yellow]No competition links found on this page[/yellow]")

    def analyze_competition_links(self, competition_links, max_analyze=30):
        """Analyze a list of competition links"""
        console.print(f"[cyan]🤖 Analyzing {min(len(competition_links), max_analyze)} competitions...[/cyan]")
        console.print("[dim]This may take a while...[/dim]")
        
        # Limit to max_analyze
        to_analyze = competition_links[:max_analyze]
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console
        ) as progress:
            task = progress.add_task("Analyzing competitions...", total=len(to_analyze))
            
            for i, link in enumerate(to_analyze):
                url = link['url']
                progress.update(task, description=f"Analyzing {i+1}/{len(to_analyze)}")
                
                result = self.scout.analyze_competition(url)
                if result:
                    self.analyzed_competitions.append(result)
                
                progress.advance(task)
        
        # Sort by worth score
        self.analyzed_competitions.sort(key=lambda x: x.get('worth_score', 0), reverse=True)
        
        console.print(f"[green]✅ Analyzed {len(self.analyzed_competitions)} competitions[/green]")
        self.view_results()

    def auto_analyze(self):
        """Automatically find and analyze all competition links"""
        console.print("[cyan]🔍 Finding all competition links...[/cyan]")
        
        links = self.page.get_all_links()
        competition_links = []
        
        for link in links:
            href = link.get('href', '')
            if self.scout.is_competition_page(href):
                # Avoid duplicates
                if href not in [c['url'] for c in competition_links]:
                    competition_links.append({
                        'url': href,
                        'text': link.get('text', '')
                    })
        
        if not competition_links:
            console.print("[yellow]No competition links found[/yellow]")
            return
        
        console.print(f"[green]✅ Found {len(competition_links)} unique competitions[/green]")
        
        if Confirm.ask(f"Analyze all {len(competition_links)} competitions? (This will take time)"):
            self.analyze_competition_links(competition_links)

    def view_results(self):
        """Display analyzed competitions ranked by worth"""
        if not self.analyzed_competitions:
            console.print("[yellow]No competitions analyzed yet[/yellow]")
            return
        
        console.print()
        console.print(Panel("[bold green]📊 ANALYZED COMPETITIONS[/bold green]", border_style="green"))
        
        # Show summary stats
        free_count = sum(1 for c in self.analyzed_competitions if c.get('is_free', False))
        with_prize = sum(1 for c in self.analyzed_competitions if c.get('prize', 0) > 0)
        with_internship = sum(1 for c in self.analyzed_competitions if c.get('has_internship', False))
        
        console.print(f"[cyan]Total analyzed:[/cyan] {len(self.analyzed_competitions)}")
        console.print(f"[green]Free competitions:[/green] {free_count}")
        console.print(f"[yellow]With prizes:[/yellow] {with_prize}")
        console.print(f"[blue]With internships:[/blue] {with_internship}")
        
        # Show table of all results
        table = Table(title="Competition Rankings", box=box.ROUNDED)
        table.add_column("#", style="dim")
        table.add_column("Status", style="bold")
        table.add_column("Score", style="yellow")
        table.add_column("Title", style="white")
        table.add_column("Fee", style="cyan")
        table.add_column("Prize", style="green")
        table.add_column("Internship", style="blue")
        
        for i, comp in enumerate(self.analyzed_competitions[:30], 1):
            status = comp.get('status', '')
            color = comp.get('color', 'white')
            score = comp.get('worth_score', 0)
            title = comp.get('title', '')[:40]
            fee = "Free" if comp.get('is_free', False) else f"₹{comp.get('fee', '?')}"
            prize = f"₹{comp['prize']:,}" if comp.get('prize', 0) > 0 else "—"
            internship = "✅" if comp.get('has_internship', False) else "—"
            
            table.add_row(
                str(i),
                Text(status, style=color),
                str(score),
                title,
                fee,
                prize,
                internship
            )
        
        console.print(table)
        
        if len(self.analyzed_competitions) > 30:
            console.print(f"[dim]... and {len(self.analyzed_competitions) - 30} more[/dim]")
        
        # Show top recommendations
        console.print()
        console.print(Panel("[bold green]🔥 TOP RECOMMENDATIONS[/bold green]", border_style="green"))
        
        top_comps = [c for c in self.analyzed_competitions if c.get('worth_score', 0) >= 3][:10]
        
        if top_comps:
            for i, comp in enumerate(top_comps, 1):
                console.print(f"{i}. {comp.get('status', '')} - [cyan]{comp.get('title', '')[:60]}[/cyan]")
                if comp.get('reasons'):
                    for reason in comp.get('reasons', [])[:3]:
                        console.print(f"   • {reason}")
                console.print(f"   🔗 {comp.get('url', '')[:80]}")
                console.print()
        else:
            console.print("[dim]No highly recommended competitions found yet[/dim]")

    def save_results(self):
        """Save analyzed results to file"""
        if not self.analyzed_competitions:
            console.print("[yellow]No results to save[/yellow]")
            return
        
        filename = f"competitions_{int(time.time())}.json"
        
        # Categorize by worth
        categorized = {
            'hot': [c for c in self.analyzed_competitions if 'HOT' in c.get('status', '')],
            'highly_recommended': [c for c in self.analyzed_competitions if 'HIGHLY' in c.get('status', '')],
            'recommended': [c for c in self.analyzed_competitions if 'RECOMMENDED' in c.get('status', '')],
            'check': [c for c in self.analyzed_competitions if 'CHECKING' in c.get('status', '')],
            'skip': [c for c in self.analyzed_competitions if 'SKIP' in c.get('status', '')]
        }
        
        with open(filename, 'w') as f:
            json.dump({
                'total_analyzed': len(self.analyzed_competitions),
                'categorized': categorized,
                'all': self.analyzed_competitions
            }, f, indent=2)
        
        console.print(f"[green]✅ Saved results to {filename}[/green]")
        
        # Also save a readable text file
        text_filename = f"competitions_{int(time.time())}.txt"
        with open(text_filename, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write("COMPETITION SCOUT RESULTS\n")
            f.write("=" * 80 + "\n\n")
            
            for category, comps in categorized.items():
                if comps:
                    f.write(f"\n{'=' * 80}\n")
                    f.write(f"{category.upper()} ({len(comps)})\n")
                    f.write(f"{'=' * 80}\n\n")
                    for comp in comps:
                        f.write(f"Title: {comp.get('title', '')}\n")
                        f.write(f"URL: {comp.get('url', '')}\n")
                        f.write(f"Score: {comp.get('worth_score', 0)}\n")
                        f.write(f"Free: {comp.get('is_free', False)}\n")
                        f.write(f"Prize: {comp.get('prize', 'N/A')}\n")
                        if comp.get('reasons'):
                            f.write("Why apply:\n")
                            for reason in comp.get('reasons', []):
                                f.write(f"  - {reason}\n")
                        f.write("\n" + "-" * 40 + "\n\n")
        
        console.print(f"[green]✅ Saved readable text to {text_filename}[/green]")

def main():
    app = CompetitionScoutApp()
    app.run()

if __name__ == "__main__":
    main()
