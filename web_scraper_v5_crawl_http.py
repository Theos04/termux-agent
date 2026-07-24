#!/usr/bin/env python3
"""
Hybrid Web Scraper - Playwright for JavaScript-rendered content
"""

import json
import time
import hashlib
from datetime import datetime
from urllib.parse import urljoin, urlparse
from collections import defaultdict, Counter
import asyncio

try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    print("\033[93m⚠️  Playwright not installed. Install with: pip install playwright && playwright install chromium\033[0m")

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich import box

console = Console()

class PlaywrightScraper:
    def __init__(self, crawl_data_file=None):
        self.crawl_data = None
        self.urls = []
        self.base_url = ""
        self.scraped_data = {}
        self.full_page_texts = {}
        
        if crawl_data_file:
            self.load_crawl_data(crawl_data_file)
    
    def load_crawl_data(self, filename):
        """Load crawl data from JSON file"""
        try:
            with open(filename, 'r') as f:
                self.crawl_data = json.load(f)
            
            self.urls = self.crawl_data.get('discovered_urls', [])
            self.base_url = self.crawl_data.get('metadata', {}).get('base_url', '')
            
            console.print(f"[green]✅ Loaded {len(self.urls)} URLs from {filename}[/green]")
            return True
        except Exception as e:
            console.print(f"[red]Error loading file: {e}[/red]")
            return False
    
    async def fetch_page_async(self, page, url):
        """Fetch a single page using Playwright"""
        try:
            # Navigate to URL
            await page.goto(url, wait_until='networkidle', timeout=30000)
            
            # Wait for content to load
            await page.wait_for_timeout(2000)
            
            # Scroll to load lazy content
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000)
            
            # Get page content
            content = await page.content()
            title = await page.title()
            
            # Extract text
            text = await page.evaluate("document.body.innerText")
            
            # Extract structured data
            headers = await page.evaluate("""
                () => {
                    const headers = [];
                    document.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(h => {
                        headers.push({
                            level: h.tagName.toLowerCase(),
                            text: h.textContent.trim()
                        });
                    });
                    return headers;
                }
            """)
            
            paragraphs = await page.evaluate("""
                () => {
                    const paras = [];
                    document.querySelectorAll('p').forEach(p => {
                        const text = p.textContent.trim();
                        if (text && text.length > 10) {
                            paras.push(text);
                        }
                    });
                    return paras;
                }
            """)
            
            links = await page.evaluate("""
                () => {
                    const links = [];
                    document.querySelectorAll('a[href]').forEach(a => {
                        links.push({
                            text: a.textContent.trim() || '',
                            href: a.href
                        });
                    });
                    return links;
                }
            """)
            
            # Get job listings if present
            jobs = await page.evaluate("""
                () => {
                    const jobs = [];
                    // Look for job cards
                    document.querySelectorAll('[class*="job"], [class*="Job"], [class*="listing"], [class*="card"]').forEach(el => {
                        const text = el.textContent;
                        if (text && (text.includes('LPA') || text.includes('lakh') || text.includes('salary') || text.includes('experience'))) {
                            const title = el.querySelector('h1, h2, h3, h4, h5, h6, [class*="title"]');
                            const company = el.querySelector('[class*="company"], [class*="org"]');
                            const location = el.querySelector('[class*="location"]');
                            jobs.push({
                                title: title ? title.textContent.trim() : '',
                                company: company ? company.textContent.trim() : '',
                                location: location ? location.textContent.trim() : '',
                                text: text.substring(0, 300)
                            });
                        }
                    });
                    return jobs;
                }
            """)
            
            page_data = {
                'url': url,
                'final_url': page.url,
                'title': title,
                'word_count': len(text.split()),
                'headers': headers[:20],
                'paragraphs': paragraphs[:20],
                'links': links[:50],
                'jobs': jobs[:20],
                'text_preview': text[:500] if text else 'No text',
                'full_text': text
            }
            
            self.full_page_texts[url] = text
            
            return page_data
            
        except Exception as e:
            return {'error': str(e), 'url': url}
    
    async def batch_scrape_async(self, urls=None, max_pages=20, start_from=0):
        """Scrape multiple pages using Playwright"""
        if not HAS_PLAYWRIGHT:
            console.print("[red]❌ Playwright not installed. Install with: pip install playwright && playwright install chromium[/red]")
            return [], []
        
        if urls is None:
            urls = self.urls
        
        # Filter out dashboard pages
        filtered_urls = []
        skip_patterns = ['/mnjuser/', '/myapply/', '/inbox', '/savedjobs']
        for url in urls:
            if not any(pattern in url for pattern in skip_patterns):
                filtered_urls.append(url)
        
        urls_to_scrape = filtered_urls[start_from:start_from + max_pages]
        
        console.print(f"\n[bold cyan]🔄 Batch Scraping {len(urls_to_scrape)} pages[/bold cyan]")
        console.print(f"[dim]Starting from page {start_from + 1}[/dim]")
        
        scraped = []
        failed = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1366, 'height': 768},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = await context.new_page()
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=console
            ) as progress:
                task = progress.add_task("Scraping...", total=len(urls_to_scrape))
                
                for i, url in enumerate(urls_to_scrape):
                    progress.update(task, description=f"Scraping {i+1}/{len(urls_to_scrape)}")
                    
                    data = await self.fetch_page_async(page, url)
                    
                    if 'error' in data:
                        failed.append(data)
                    else:
                        scraped.append(data)
                        self.scraped_data[url] = data
                    
                    progress.update(task, advance=1)
            
            await browser.close()
        
        console.print(f"\n[green]✅ Scraped {len(scraped)} pages[/green]")
        console.print(f"[yellow]❌ Failed: {len(failed)} pages[/yellow]")
        
        # Count pages with content
        content_pages = [s for s in scraped if s.get('paragraphs') or s.get('jobs')]
        console.print(f"[cyan]📄 Pages with content: {len(content_pages)}[/cyan]")
        
        return scraped, failed
    
    def batch_scrape(self, max_pages=20, start_from=0):
        """Sync wrapper for batch scraping"""
        return asyncio.run(self.batch_scrape_async(max_pages=max_pages, start_from=start_from))
    
    def analyze_scraped_data(self):
        """Analyze scraped data"""
        analysis = {
            'total_pages': len(self.scraped_data),
            'pages_with_content': 0,
            'pages_with_jobs': 0,
            'total_jobs': 0,
            'avg_word_count': 0,
            'form_count': 0,
            'image_count': 0,
            'link_count': 0,
            'titles': [],
            'word_counts': []
        }
        
        total_words = 0
        
        for url, data in self.scraped_data.items():
            if 'error' in data:
                continue
            
            if data.get('paragraphs') or data.get('headers'):
                analysis['pages_with_content'] += 1
            
            jobs = data.get('jobs', [])
            if jobs:
                analysis['pages_with_jobs'] += 1
                analysis['total_jobs'] += len(jobs)
            
            total_words += data.get('word_count', 0)
            analysis['word_counts'].append(data.get('word_count', 0))
            analysis['link_count'] += len(data.get('links', []))
            
            if data.get('title'):
                analysis['titles'].append(data['title'])
        
        if analysis['total_pages'] > 0:
            analysis['avg_word_count'] = total_words / analysis['total_pages']
        
        self.analysis = analysis
        return analysis
    
    def display_statistics(self):
        """Display scraped statistics"""
        if not hasattr(self, 'analysis'):
            self.analyze_scraped_data()
        
        analysis = self.analysis
        
        console.print("\n[bold cyan]📊 Scraping Statistics[/bold cyan]")
        console.print(f"  Pages Scraped: {analysis['total_pages']}")
        console.print(f"  Pages with Content: {analysis['pages_with_content']}")
        console.print(f"  Pages with Jobs: {analysis['pages_with_jobs']}")
        console.print(f"  Total Jobs Found: {analysis['total_jobs']}")
        console.print(f"  Avg Word Count: {analysis['avg_word_count']:.0f}")
        console.print(f"  Total Links: {analysis['link_count']}")
        
        if analysis['titles']:
            console.print("\n  Sample Titles:")
            for title in analysis['titles'][:5]:
                console.print(f"    • {title[:60]}")
    
    def display_jobs(self, max_display=20):
        """Display extracted jobs"""
        if not self.scraped_data:
            console.print("[yellow]No scraped data[/yellow]")
            return
        
        all_jobs = []
        for url, data in self.scraped_data.items():
            if 'error' not in data:
                for job in data.get('jobs', []):
                    all_jobs.append({
                        'url': url,
                        'title': job.get('title', 'No Title'),
                        'company': job.get('company', ''),
                        'location': job.get('location', ''),
                        'text': job.get('text', '')[:200]
                    })
        
        if not all_jobs:
            console.print("[yellow]No jobs found[/yellow]")
            return
        
        console.print(f"\n[bold cyan]💼 Extracted Jobs ({len(all_jobs)})[/bold cyan]\n")
        
        for i, job in enumerate(all_jobs[:max_display], 1):
            console.print(f"[bold]{i}. {job['title']}[/bold]")
            if job['company']:
                console.print(f"   🏢 {job['company']}")
            if job['location']:
                console.print(f"   📍 {job['location']}")
            console.print(f"   🔗 {job['url'][:60]}...")
            console.print()
        
        if len(all_jobs) > max_display:
            console.print(f"[dim]... and {len(all_jobs) - max_display} more jobs[/dim]")
    
    def save_data(self, filename=None):
        """Save scraped data"""
        if not filename:
            filename = f"scraped_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        output = {
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'base_url': self.base_url,
                'total_pages': len(self.scraped_data)
            },
            'pages': self.scraped_data,
            'analysis': self.analysis if hasattr(self, 'analysis') else {}
        }
        
        with open(filename, 'w') as f:
            json.dump(output, f, indent=2, default=str)
        
        console.print(f"[green]✅ Data saved to {filename}[/green]")
        return filename

def main():
    console.clear()
    console.print(Panel("[bold cyan]🌐 Playwright Scraper - JavaScript-Rendered Content[/bold cyan]", border_style="green"))
    
    if not HAS_PLAYWRIGHT:
        console.print("[red]❌ Playwright not installed![/red]")
        console.print("[yellow]Install with: pip install playwright && playwright install chromium[/yellow]")
        return
    
    import glob
    import os
    crawl_files = glob.glob("crawl_*.json")
    
    if not crawl_files:
        console.print("[yellow]No crawl data files found[/yellow]")
        console.print("[dim]Run the Autonomous Crawler first to discover URLs[/dim]")
        return
    
    console.print("\n[bold]Found crawl data files:[/bold]")
    for i, f in enumerate(crawl_files, 1):
        size = os.path.getsize(f) / 1024
        console.print(f"  {i}. {f} ({size:.1f} KB)")
    
    choice = Prompt.ask("Select file", default="1")
    try:
        idx = int(choice) - 1
        filename = crawl_files[idx]
    except:
        filename = Prompt.ask("Enter filename")
    
    scraper = PlaywrightScraper(filename)
    
    if not scraper.urls:
        console.print("[red]No URLs found in crawl data[/red]")
        return
    
    while True:
        console.print()
        console.print(Panel("[bold]Scraper Controls[/bold]", border_style="blue"))
        
        console.print("[cyan]📌 Options:[/cyan]")
        console.print("  1. 🔄 Start Batch Scraping")
        console.print("  2. 📊 Show Statistics")
        console.print("  3. 💼 Show Extracted Jobs")
        console.print("  4. 🔍 View Page Content")
        console.print("  5. 💾 Save Data")
        console.print("  0. Exit")
        
        choice = Prompt.ask("Select", choices=["0","1","2","3","4","5"])
        
        if choice == "0":
            break
        
        elif choice == "1":
            max_pages = int(Prompt.ask("Max pages to scrape", default="20"))
            start_from = int(Prompt.ask("Start from page index", default="0"))
            scraper.batch_scrape(max_pages=max_pages, start_from=start_from)
            scraper.analyze_scraped_data()
            scraper.display_statistics()
        
        elif choice == "2":
            if not scraper.scraped_data:
                console.print("[yellow]No data scraped yet. Run batch scraping first.[/yellow]")
            else:
                scraper.display_statistics()
        
        elif choice == "3":
            scraper.display_jobs()
        
        elif choice == "4":
            if not scraper.scraped_data:
                console.print("[yellow]No data scraped yet[/yellow]")
                continue
            
            urls = list(scraper.scraped_data.keys())
            console.print("\n[bold cyan]Select a page:[/bold cyan]")
            for i, url in enumerate(urls[:15], 1):
                data = scraper.scraped_data[url]
                title = data.get('title', 'No Title')[:40]
                jobs = len(data.get('jobs', []))
                console.print(f"  {i}. {title} - {jobs} jobs")
            
            choice2 = Prompt.ask("Enter page number")
            try:
                idx = int(choice2) - 1
                if 0 <= idx < len(urls):
                    url = urls[idx]
                    data = scraper.scraped_data[url]
                    console.print(f"\n[bold cyan]📄 Page:[/bold cyan] {url}")
                    console.print(f"  Title: {data.get('title', 'No Title')}")
                    console.print(f"  Word Count: {data.get('word_count', 0)}")
                    console.print(f"  Headers: {len(data.get('headers', []))}")
                    console.print(f"  Paragraphs: {len(data.get('paragraphs', []))}")
                    console.print(f"  Jobs: {len(data.get('jobs', []))}")
                    
                    if data.get('text_preview'):
                        console.print("\n[bold]Text Preview:[/bold]")
                        console.print(Panel(data['text_preview'][:800], border_style="dim"))
            except:
                console.print("[red]Invalid selection[/red]")
        
        elif choice == "5":
            if scraper.scraped_data:
                scraper.save_data()
            else:
                console.print("[yellow]No data to save[/yellow]")
        
        if choice != "0":
            console.print()
            input("Press Enter to continue...")

if __name__ == "__main__":
    main()
