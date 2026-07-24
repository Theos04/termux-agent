#!/usr/bin/env python3
"""
Hybrid Web Scraper - Enhanced with Better Content Extraction
"""

import json
import requests
import time
import hashlib
import sys
from datetime import datetime
from collections import defaultdict, Counter
from urllib.parse import urljoin, urlparse
import re

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    print("\033[93m⚠️  BeautifulSoup not installed. Install with: pip install beautifulsoup4 lxml\033[0m")

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich import box
from rich.syntax import Syntax

console = Console()

class HybridScraper:
    def __init__(self, crawl_data_file=None):
        self.crawl_data = None
        self.urls = []
        self.base_url = ""
        self.scraped_data = {}
        self.full_page_texts = {}
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
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
    
    def fetch_page(self, url):
        """Fetch a single page using requests + BeautifulSoup"""
        if not HAS_BS4:
            return {'error': 'beautifulsoup_not_installed', 'url': url}
        
        try:
            response = self.session.get(url, timeout=15, allow_redirects=True)
            
            # Check if redirected to login
            is_login_page = 'login' in response.url.lower() or 'signin' in response.url.lower()
            
            # Check if it's HTML
            content_type = response.headers.get('content-type', '')
            if 'text/html' not in content_type.lower():
                return {
                    'error': 'not_html',
                    'url': url,
                    'content_type': content_type,
                    'content_length': len(response.content)
                }
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(response.content, 'lxml' if 'lxml' in sys.modules else 'html.parser')
            
            # Extract all text
            full_text = soup.get_text(separator='\n', strip=True)
            
            # Extract data
            page_data = {
                'url': url,
                'final_url': response.url,
                'status_code': response.status_code,
                'content_type': content_type,
                'content_length': len(response.content),
                'is_login_page': is_login_page or self._is_login_page(soup),
                'title': self._extract_title(soup),
                'meta': self._extract_meta(soup),
                'headers': self._extract_headers(soup),
                'paragraphs': self._extract_paragraphs(soup),
                'links': self._extract_links(soup, url),
                'images': self._extract_images(soup, url),
                'forms': self._extract_forms(soup, url),
                'tables': self._extract_tables(soup),
                'lists': self._extract_lists(soup),
                'word_count': len(response.text.split()),
                'hash': hashlib.md5(response.content).hexdigest(),
                'text_preview': full_text[:500]  # First 500 chars
            }
            
            # Store full text separately
            self.full_page_texts[url] = full_text
            
            return page_data
            
        except requests.exceptions.Timeout:
            return {'error': 'timeout', 'url': url}
        except requests.exceptions.ConnectionError:
            return {'error': 'connection_failed', 'url': url}
        except requests.exceptions.HTTPError as e:
            return {'error': f'http_{e.response.status_code}', 'url': url}
        except Exception as e:
            return {'error': str(e), 'url': url}
    
    def _is_login_page(self, soup):
        """Check if page is a login page"""
        login_indicators = ['login', 'signin', 'sign in', 'log in', 'username', 'password']
        text = soup.get_text().lower()
        return any(indicator in text for indicator in login_indicators)
    
    def _extract_title(self, soup):
        """Extract page title"""
        title = soup.find('title')
        return title.text.strip() if title else ''
    
    def _extract_meta(self, soup):
        """Extract meta tags"""
        meta = {}
        for tag in soup.find_all('meta'):
            name = tag.get('name') or tag.get('property') or ''
            content = tag.get('content', '')
            if name and content:
                meta[name] = content
        return meta
    
    def _extract_headers(self, soup):
        """Extract headers (h1-h6)"""
        headers = []
        for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            for elem in soup.find_all(tag):
                text = elem.text.strip()
                if text:
                    headers.append({
                        'level': tag,
                        'text': text[:200]
                    })
        return headers
    
    def _extract_paragraphs(self, soup):
        """Extract paragraphs"""
        paragraphs = []
        for p in soup.find_all('p'):
            text = p.text.strip()
            if text and len(text) > 10:
                paragraphs.append(text[:500])
        return paragraphs
    
    def _extract_links(self, soup, base_url):
        """Extract all links"""
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.text.strip() or ''
            
            # Convert relative to absolute
            absolute_url = urljoin(base_url, href)
            
            # Only include valid URLs
            if absolute_url.startswith(('http://', 'https://')):
                links.append({
                    'url': absolute_url,
                    'text': text[:100],
                    'is_internal': self.base_url and self.base_url in absolute_url
                })
        
        return links
    
    def _extract_images(self, soup, base_url):
        """Extract images"""
        images = []
        for img in soup.find_all('img'):
            src = img.get('src', '')
            alt = img.get('alt', '')
            if src:
                absolute_url = urljoin(base_url, src)
                images.append({
                    'url': absolute_url,
                    'alt': alt[:50]
                })
        return images
    
    def _extract_forms(self, soup, base_url):
        """Extract forms"""
        forms = []
        for form in soup.find_all('form'):
            action = form.get('action', '')
            method = form.get('method', 'GET').upper()
            
            inputs = []
            for input_tag in form.find_all(['input', 'textarea', 'select']):
                input_type = input_tag.get('type', input_tag.name)
                name = input_tag.get('name', '')
                
                # Get options for select
                options = []
                if input_tag.name == 'select':
                    for option in input_tag.find_all('option'):
                        options.append(option.text.strip())
                
                inputs.append({
                    'type': input_type,
                    'name': name,
                    'placeholder': input_tag.get('placeholder', ''),
                    'required': input_tag.get('required', False),
                    'options': options[:5] if options else []
                })
            
            # Find submit button
            submit_text = ''
            submit_btn = form.find(['button', 'input'], {'type': 'submit'})
            if submit_btn:
                submit_text = submit_btn.get('value', submit_btn.text or 'Submit')
            
            forms.append({
                'action': urljoin(base_url, action) if action else '',
                'method': method,
                'inputs': inputs,
                'submit_text': submit_text
            })
        
        return forms
    
    def _extract_tables(self, soup):
        """Extract tables"""
        tables = []
        for table in soup.find_all('table'):
            rows = []
            headers = []
            
            # Get headers if any
            thead = table.find('thead')
            if thead:
                for th in thead.find_all('th'):
                    headers.append(th.text.strip())
            
            # Get data rows
            tbody = table.find('tbody') or table
            for tr in tbody.find_all('tr'):
                cells = []
                for td in tr.find_all(['td', 'th']):
                    cells.append(td.text.strip())
                if cells:
                    rows.append(cells)
            
            if rows:
                tables.append({
                    'headers': headers,
                    'rows': len(rows),
                    'columns': len(rows[0]) if rows else 0,
                    'data': rows[:5]  # Only first 5 rows
                })
        return tables
    
    def _extract_lists(self, soup):
        """Extract lists"""
        lists = []
        for list_tag in soup.find_all(['ul', 'ol']):
            items = []
            for li in list_tag.find_all('li'):
                text = li.text.strip()
                if text:
                    items.append(text[:100])
            if items:
                lists.append({
                    'type': list_tag.name,
                    'count': len(items),
                    'items': items[:10]
                })
        return lists
    
    def batch_scrape(self, urls=None, max_pages=50, start_from=0):
        """Scrape multiple pages in batch"""
        if not HAS_BS4:
            console.print("[red]❌ BeautifulSoup not installed. Install with: pip install beautifulsoup4 lxml[/red]")
            return [], []
        
        if urls is None:
            urls = self.urls
        
        # Filter URLs - only scrape HTML pages
        filtered_urls = []
        skip_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.pdf', '.zip', '.mp4', '.mp3', '.css', '.js']
        for url in urls:
            if not any(url.lower().endswith(ext) for ext in skip_extensions):
                filtered_urls.append(url)
        
        urls_to_scrape = filtered_urls[start_from:start_from + max_pages]
        
        console.print(f"\n[bold cyan]🔄 Batch Scraping {len(urls_to_scrape)} pages[/bold cyan]")
        console.print(f"[dim]Starting from page {start_from + 1}[/dim]")
        
        scraped = []
        failed = []
        
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
                
                data = self.fetch_page(url)
                
                if 'error' in data:
                    failed.append(data)
                else:
                    scraped.append(data)
                    self.scraped_data[url] = data
                
                progress.update(task, advance=1)
                time.sleep(0.3)
        
        console.print(f"\n[green]✅ Scraped {len(scraped)} pages[/green]")
        console.print(f"[yellow]❌ Failed: {len(failed)} pages[/yellow]")
        
        # Show login pages detected
        login_pages = [s for s in scraped if s.get('is_login_page', False)]
        if login_pages:
            console.print(f"[yellow]🔒 {len(login_pages)} pages require login[/yellow]")
        
        if failed:
            console.print("\n[yellow]Failed URLs (first 5):[/yellow]")
            for fail in failed[:5]:
                console.print(f"  • {fail.get('url', 'Unknown')} - {fail.get('error', 'Unknown error')}")
        
        return scraped, failed
    
    def analyze_scraped_data(self):
        """Analyze scraped data"""
        console.print("[yellow]\nAnalyzing scraped data...[/yellow]")
        
        analysis = {
            'total_pages': len(self.scraped_data),
            'login_pages': 0,
            'avg_word_count': 0,
            'content_types': defaultdict(int),
            'common_meta': Counter(),
            'form_count': 0,
            'image_count': 0,
            'link_count': 0,
            'pages_with_schema': 0,
            'word_counts': [],
            'error_pages': 0,
            'titles': []
        }
        
        total_words = 0
        
        for url, data in self.scraped_data.items():
            if 'error' in data:
                analysis['error_pages'] += 1
                continue
            
            if data.get('is_login_page'):
                analysis['login_pages'] += 1
            
            total_words += data.get('word_count', 0)
            analysis['word_counts'].append(data.get('word_count', 0))
            
            # Count forms
            forms = data.get('forms', [])
            analysis['form_count'] += len(forms)
            
            # Count images
            images = data.get('images', [])
            analysis['image_count'] += len(images)
            
            # Count links
            links = data.get('links', [])
            analysis['link_count'] += len(links)
            
            # Schema
            if data.get('schema'):
                analysis['pages_with_schema'] += 1
            
            # Meta tags
            for key, value in data.get('meta', {}).items():
                analysis['common_meta'][key] += 1
            
            # Titles
            if data.get('title'):
                analysis['titles'].append(data['title'])
            
            # Content type from meta
            if 'og:type' in data.get('meta', {}):
                analysis['content_types'][data['meta']['og:type']] += 1
        
        valid_pages = analysis['total_pages'] - analysis['error_pages']
        if valid_pages > 0:
            analysis['avg_word_count'] = total_words / valid_pages
        
        self.analysis = analysis
        return analysis
    
    def display_page_text(self, url, max_chars=1000):
        """Display full text of a specific page"""
        if url in self.full_page_texts:
            text = self.full_page_texts[url][:max_chars]
            console.print(f"\n[bold cyan]📄 Page Text:[/bold cyan] {url[:80]}")
            console.print("-" * 80)
            console.print(text)
            if len(self.full_page_texts[url]) > max_chars:
                console.print(f"\n[dim]... and {len(self.full_page_texts[url]) - max_chars} more characters[/dim]")
        else:
            console.print("[yellow]Text not available for this page[/yellow]")
    
    def display_statistics(self):
        """Display scraped statistics"""
        if not hasattr(self, 'analysis'):
            self.analyze_scraped_data()
        
        analysis = self.analysis
        
        console.print("\n[bold cyan]📊 Scraping Statistics[/bold cyan]")
        console.print(f"  Pages Scraped: {analysis['total_pages']}")
        console.print(f"  Pages with Errors: {analysis.get('error_pages', 0)}")
        console.print(f"  Login Pages Detected: {analysis.get('login_pages', 0)}")
        console.print(f"  Avg Word Count: {analysis['avg_word_count']:.0f}")
        console.print(f"  Total Forms: {analysis['form_count']}")
        console.print(f"  Total Images: {analysis['image_count']}")
        console.print(f"  Total Links: {analysis['link_count']}")
        console.print(f"  Pages with Schema: {analysis['pages_with_schema']}")
        
        if analysis['titles']:
            console.print("\n  Sample Titles:")
            for title in analysis['titles'][:5]:
                console.print(f"    • {title[:60]}")
        
        if analysis['common_meta']:
            console.print("\n  Common Meta Tags:")
            for meta, count in analysis['common_meta'].most_common(5):
                console.print(f"    • {meta}: {count} pages")
    
    def display_pages(self, max_display=10):
        """Display scraped pages summary"""
        if not self.scraped_data:
            console.print("[yellow]No scraped data[/yellow]")
            return
        
        console.print(f"\n[bold cyan]📄 Scraped Pages ({len(self.scraped_data)})[/bold cyan]")
        
        table = Table(box=box.SIMPLE)
        table.add_column("#", style="dim")
        table.add_column("Title", style="green", max_width=35)
        table.add_column("Words", style="blue")
        table.add_column("Links", style="magenta")
        table.add_column("Forms", style="yellow")
        table.add_column("Login?", style="red")
        table.add_column("Status", style="white")
        
        for i, (url, data) in enumerate(list(self.scraped_data.items())[:max_display], 1):
            if 'error' in data:
                table.add_row(str(i), "ERROR", "-", "-", "-", "-", f"[red]{data['error']}[/red]")
            else:
                title = data.get('title', 'No Title')[:35]
                words = str(data.get('word_count', 0))
                links = str(len(data.get('links', [])))
                forms = str(len(data.get('forms', [])))
                is_login = "🔒" if data.get('is_login_page') else "❌"
                status = f"[green]{data.get('status_code', 200)}[/green]"
                table.add_row(str(i), title, words, links, forms, is_login, status)
        
        console.print(table)
        
        if len(self.scraped_data) > max_display:
            console.print(f"\n[dim]... and {len(self.scraped_data) - max_display} more pages[/dim]")
    
    def view_page_content(self):
        """View detailed content of a specific page"""
        if not self.scraped_data:
            console.print("[yellow]No scraped data[/yellow]")
            return
        
        # Show list of pages
        urls = list(self.scraped_data.keys())
        console.print("\n[bold cyan]Select a page to view:[/bold cyan]")
        for i, url in enumerate(urls[:20], 1):
            data = self.scraped_data[url]
            title = data.get('title', 'No Title')[:40]
            console.print(f"  {i}. {title} - {url[:60]}")
        
        if len(urls) > 20:
            console.print(f"[dim]... and {len(urls)-20} more[/dim]")
        
        choice = Prompt.ask("Enter page number or URL")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(urls):
                url = urls[idx]
            else:
                url = choice
        except:
            url = choice
        
        if url in self.scraped_data:
            data = self.scraped_data[url]
            
            console.print(f"\n[bold cyan]📄 Page Details:[/bold cyan]")
            console.print(f"  URL: {data.get('url', 'N/A')}")
            console.print(f"  Final URL: {data.get('final_url', 'N/A')}")
            console.print(f"  Title: {data.get('title', 'No Title')}")
            console.print(f"  Status: {data.get('status_code', 'N/A')}")
            console.print(f"  Login Page: {data.get('is_login_page', False)}")
            console.print(f"  Word Count: {data.get('word_count', 0)}")
            
            if data.get('headers'):
                console.print("\n  Headers:")
                for header in data['headers'][:3]:
                    console.print(f"    {header['level']}: {header['text'][:80]}")
            
            if data.get('paragraphs'):
                console.print(f"\n  Sample Paragraphs ({len(data['paragraphs'])} total):")
                for p in data['paragraphs'][:2]:
                    console.print(f"    {p[:150]}...")
            
            if data.get('forms'):
                console.print(f"\n  Forms ({len(data['forms'])}):")
                for form in data['forms'][:2]:
                    console.print(f"    Action: {form.get('action', 'N/A')}")
                    console.print(f"    Method: {form.get('method', 'N/A')}")
                    console.print(f"    Inputs: {len(form.get('inputs', []))}")
            
            # Show text preview
            if data.get('text_preview'):
                console.print("\n[bold]Text Preview:[/bold]")
                console.print(Panel(data['text_preview'][:500], border_style="dim"))
        else:
            console.print("[red]Page not found[/red]")
    
    def save_data(self, filename=None):
        """Save scraped data to JSON"""
        if not filename:
            filename = f"scraped_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # Include full texts but truncated
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
    console.print(Panel("[bold cyan]🌐 Hybrid Web Scraper - Enhanced[/bold cyan]", border_style="green"))
    
    if not HAS_BS4:
        console.print("[red]❌ BeautifulSoup not installed![/red]")
        console.print("[yellow]Install with: pip install beautifulsoup4 lxml[/yellow]")
        return
    
    # Find crawl files
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
    
    scraper = HybridScraper(filename)
    
    if not scraper.urls:
        console.print("[red]No URLs found in crawl data[/red]")
        return
    
    while True:
        console.print()
        console.print(Panel("[bold]Scraper Controls[/bold]", border_style="blue"))
        
        console.print("[cyan]📌 Options:[/cyan]")
        console.print("  1. 🔄 Start Batch Scraping")
        console.print("  2. 📊 Show Statistics")
        console.print("  3. 📄 List Scraped Pages")
        console.print("  4. 🔍 View Page Content")
        console.print("  5. 📝 Show Page Text")
        console.print("  6. 💾 Save Data")
        console.print("  7. 📝 Export URLs to File")
        console.print("  0. Exit")
        
        choice = Prompt.ask("Select", choices=["0","1","2","3","4","5","6","7"])
        
        if choice == "0":
            break
        
        elif choice == "1":
            max_pages = int(Prompt.ask("Max pages to scrape", default="50"))
            start_from = int(Prompt.ask("Start from page index", default="0"))
            
            scraped, failed = scraper.batch_scrape(max_pages=max_pages, start_from=start_from)
            
            if scraped:
                scraper.analyze_scraped_data()
                scraper.display_statistics()
        
        elif choice == "2":
            if not scraper.scraped_data:
                console.print("[yellow]No data scraped yet. Run batch scraping first.[/yellow]")
            else:
                scraper.display_statistics()
        
        elif choice == "3":
            scraper.display_pages()
        
        elif choice == "4":
            scraper.view_page_content()
        
        elif choice == "5":
            url = Prompt.ask("Enter URL to view text")
            scraper.display_page_text(url)
        
        elif choice == "6":
            if scraper.scraped_data:
                scraper.save_data()
            else:
                console.print("[yellow]No data to save[/yellow]")
        
        elif choice == "7":
            filename = Prompt.ask("Output filename", default="urls.txt")
            with open(filename, 'w') as f:
                for url in scraper.urls:
                    f.write(url + '\n')
            console.print(f"[green]✅ Saved {len(scraper.urls)} URLs to {filename}[/green]")
        
        if choice != "0":
            console.print()
            input("Press Enter to continue...")

if __name__ == "__main__":
    main()
