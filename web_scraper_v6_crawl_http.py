#!/usr/bin/env python3
"""
Advanced Web Scraper - Handles bot detection, cookies, and sessions
"""

import json
import requests
import time
import re
import sys
import os
from datetime import datetime
from urllib.parse import urljoin, urlparse
from collections import defaultdict
import hashlib

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich import box

console = Console()

class AdvancedScraper:
    def __init__(self, crawl_data_file=None):
        self.crawl_data = None
        self.urls = []
        self.base_url = ""
        self.scraped_data = {}
        self.full_page_texts = {}
        self.session = None
        self.cookie_jar = {}
        
        if crawl_data_file:
            self.load_crawl_data(crawl_data_file)
        
        self._init_session()
    
    def _init_session(self):
        """Initialize session with browser-like headers"""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # Set default cookies for common sites
        self.session.cookies.set('cookieconsent_status', 'dismiss')
        self.session.cookies.set('_ga', 'GA1.2.1234567890.1234567890')
    
    def load_crawl_data(self, filename):
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
    
    def detect_site_type(self, url):
        """Detect which site we're scraping"""
        if 'reddit.com' in url:
            return 'reddit'
        elif 'naukri.com' in url:
            return 'naukri'
        elif 'linkedin.com' in url:
            return 'linkedin'
        elif 'indeed.com' in url:
            return 'indeed'
        else:
            return 'generic'
    
    def fetch_with_retry(self, url, max_retries=3):
        """Fetch with retry logic and progressive headers"""
        headers_configs = [
            # Standard browser
            {},
            # Mobile user agent
            {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'},
            # Chrome with different headers
            {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'},
            # Firefox
            {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0'},
        ]
        
        for attempt in range(max_retries):
            try:
                # Rotate headers
                if attempt < len(headers_configs):
                    self.session.headers.update(headers_configs[attempt])
                
                # Add random delay
                if attempt > 0:
                    time.sleep(attempt * 2)
                
                response = self.session.get(url, timeout=20, allow_redirects=True)
                
                # Check for Cloudflare
                if 'cf-browser-verification' in response.text.lower() or 'please wait' in response.text.lower():
                    if attempt < max_retries - 1:
                        console.print(f"[dim]🔄 Bot detection, retry {attempt+2}/{max_retries}...[/dim]")
                        continue
                
                return response
                
            except Exception as e:
                if attempt < max_retries - 1:
                    continue
                return None
        
        return None
    
    def fetch_reddit(self, url):
        """Special handling for Reddit"""
        try:
            # Try the .json endpoint for API data
            json_url = url
            if '?' in url:
                json_url += '&.json'
            else:
                json_url += '/.json'
            
            response = self.session.get(json_url, timeout=15)
            if response.status_code == 200:
                try:
                    data = response.json()
                    posts = []
                    # Extract posts from Reddit API response
                    if 'data' in data and 'children' in data['data']:
                        for child in data['data']['children']:
                            if 'data' in child:
                                post_data = child['data']
                                posts.append({
                                    'title': post_data.get('title', ''),
                                    'score': post_data.get('score', 0),
                                    'num_comments': post_data.get('num_comments', 0),
                                    'author': post_data.get('author', ''),
                                    'created': post_data.get('created_utc', 0),
                                    'url': post_data.get('url', ''),
                                    'text': post_data.get('selftext', '')[:500]
                                })
                        if posts:
                            return {
                                'url': url,
                                'method': 'reddit_api',
                                'posts': posts,
                                'post_count': len(posts),
                                'title': 'Reddit API Data'
                            }
                except:
                    pass
            
            # Fallback to HTML scraping
            response = self.fetch_with_retry(url)
            if response and response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                posts = []
                
                # Look for posts in HTML
                for post in soup.find_all(['div', 'article'], class_=re.compile(r'Post|post|thing')):
                    title_elem = post.find(['h1', 'h2', 'h3', 'a'], class_=re.compile(r'title|Title'))
                    if title_elem:
                        title = title_elem.text.strip()
                        text_elem = post.find(['div', 'p'], class_=re.compile(r'text|content|body|md'))
                        text = text_elem.text.strip() if text_elem else ''
                        if title:
                            posts.append({
                                'title': title,
                                'text': text[:500]
                            })
                
                return {
                    'url': url,
                    'method': 'reddit_html',
                    'posts': posts,
                    'post_count': len(posts),
                    'title': soup.find('title').text.strip() if soup.find('title') else 'Reddit'
                }
            
            return {'error': 'failed_to_fetch', 'url': url}
            
        except Exception as e:
            return {'error': str(e), 'url': url}
    
    def fetch_naukri(self, url):
        """Special handling for Naukri"""
        try:
            response = self.fetch_with_retry(url)
            if not response or response.status_code != 200:
                return {'error': 'failed_to_fetch', 'url': url}
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            jobs = []
            
            # Look for job listings
            job_cards = soup.find_all(['div', 'article'], class_=re.compile(r'job|Job|card|Card|tuple|Tuple'))
            
            for card in job_cards:
                text = card.text
                if 'LPA' in text or 'lakh' in text or 'salary' in text.lower():
                    title = card.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a'])
                    company = card.find(['span', 'div'], class_=re.compile(r'company|Company|org|Org'))
                    
                    job = {
                        'title': title.text.strip() if title else '',
                        'company': company.text.strip() if company else '',
                        'text': text[:300]
                    }
                    
                    # Extract salary
                    salary_match = re.search(r'(\d+[,\s]*\d*)\s*(?:L|l)akh', text)
                    if salary_match:
                        job['salary'] = salary_match.group(0)
                    
                    # Extract location
                    location_match = re.search(r'([A-Z][a-z]+)\s*(?:,|$)', text)
                    if location_match:
                        job['location'] = location_match.group(1)
                    
                    if job['title'] or job['company']:
                        jobs.append(job)
            
            return {
                'url': url,
                'method': 'naukri_html',
                'jobs': jobs,
                'job_count': len(jobs),
                'title': soup.find('title').text.strip() if soup.find('title') else 'Naukri'
            }
            
        except Exception as e:
            return {'error': str(e), 'url': url}
    
    def fetch_generic(self, url):
        """Generic fetch for any site"""
        try:
            response = self.fetch_with_retry(url)
            if not response or response.status_code != 200:
                return {'error': 'failed_to_fetch', 'url': url}
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract basic data
            title = soup.find('title')
            title_text = title.text.strip() if title else ''
            
            # Extract text
            full_text = soup.get_text(separator='\n', strip=True)
            
            # Extract headers
            headers = []
            for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                for elem in soup.find_all(tag):
                    text = elem.text.strip()
                    if text:
                        headers.append({'level': tag, 'text': text[:200]})
            
            # Extract paragraphs
            paragraphs = []
            for p in soup.find_all('p'):
                text = p.text.strip()
                if text and len(text) > 10:
                    paragraphs.append(text[:500])
            
            # Extract links
            links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                text = a.text.strip() or ''
                absolute_url = urljoin(url, href)
                if absolute_url.startswith(('http://', 'https://')):
                    links.append({
                        'url': absolute_url,
                        'text': text[:100]
                    })
            
            return {
                'url': url,
                'method': 'generic',
                'title': title_text,
                'word_count': len(full_text.split()),
                'headers': headers[:20],
                'paragraphs': paragraphs[:20],
                'links': links[:50],
                'text_preview': full_text[:500],
                'full_text': full_text
            }
            
        except Exception as e:
            return {'error': str(e), 'url': url}
    
    def fetch_page(self, url):
        """Fetch page with site-specific handling"""
        site_type = self.detect_site_type(url)
        
        if site_type == 'reddit':
            return self.fetch_reddit(url)
        elif site_type == 'naukri':
            return self.fetch_naukri(url)
        else:
            return self.fetch_generic(url)
    
    def batch_scrape(self, max_pages=50, start_from=0):
        """Batch scrape with intelligent filtering"""
        # Filter URLs
        filtered_urls = []
        skip_patterns = ['.jpg', '.png', '.gif', '.webp', '.pdf', '.zip', '.mp4', '.mp3', '.css', '.js']
        skip_paths = ['/mnjuser/', '/myapply/', '/inbox', '/savedjobs', '/settings']
        
        for url in self.urls:
            if any(pattern in url for pattern in skip_patterns):
                continue
            if any(path in url for path in skip_paths):
                continue
            filtered_urls.append(url)
        
        urls_to_scrape = filtered_urls[start_from:start_from + max_pages]
        
        console.print(f"\n[bold cyan]🔄 Advanced Scraping {len(urls_to_scrape)} pages[/bold cyan]")
        
        scraped = []
        failed = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console
        ) as progress:
            task = progress.add_task("Scraping", total=len(urls_to_scrape))
            
            for i, url in enumerate(urls_to_scrape):
                progress.update(task, description=f"{i+1}/{len(urls_to_scrape)}")
                
                data = self.fetch_page(url)
                
                if 'error' in data:
                    failed.append(data)
                else:
                    scraped.append(data)
                    self.scraped_data[url] = data
                
                progress.update(task, advance=1)
                time.sleep(0.5)  # Be respectful
            
        console.print(f"\n[green]✅ Scraped {len(scraped)} pages[/green]")
        console.print(f"[yellow]❌ Failed: {len(failed)} pages[/yellow]")
        
        # Count content
        posts_count = sum(1 for s in scraped if s.get('posts'))
        jobs_count = sum(1 for s in scraped if s.get('jobs'))
        
        total_posts = sum(len(s.get('posts', [])) for s in scraped)
        total_jobs = sum(len(s.get('jobs', [])) for s in scraped)
        
        console.print(f"[cyan]📄 Pages with posts: {posts_count} ({total_posts} total)[/cyan]")
        console.print(f"[cyan]💼 Pages with jobs: {jobs_count} ({total_jobs} total)[/cyan]")
        
        return scraped, failed
    
    def analyze_scraped_data(self):
        analysis = {
            'total_pages': len(self.scraped_data),
            'pages_with_posts': 0,
            'pages_with_jobs': 0,
            'total_posts': 0,
            'total_jobs': 0,
            'avg_word_count': 0,
            'titles': [],
            'word_counts': []
        }
        
        total_words = 0
        
        for url, data in self.scraped_data.items():
            if 'error' in data:
                continue
            
            posts = data.get('posts', [])
            if posts:
                analysis['pages_with_posts'] += 1
                analysis['total_posts'] += len(posts)
            
            jobs = data.get('jobs', [])
            if jobs:
                analysis['pages_with_jobs'] += 1
                analysis['total_jobs'] += len(jobs)
            
            word_count = data.get('word_count', 0)
            total_words += word_count
            analysis['word_counts'].append(word_count)
            
            if data.get('title'):
                analysis['titles'].append(data['title'])
        
        if analysis['total_pages'] > 0:
            analysis['avg_word_count'] = total_words / analysis['total_pages']
        
        self.analysis = analysis
        return analysis
    
    def display_statistics(self):
        if not hasattr(self, 'analysis'):
            self.analyze_scraped_data()
        
        analysis = self.analysis
        
        console.print("\n[bold cyan]📊 Scraping Statistics[/bold cyan]")
        console.print(f"  Pages Scraped: {analysis['total_pages']}")
        console.print(f"  Pages with Posts: {analysis['pages_with_posts']}")
        console.print(f"  Pages with Jobs: {analysis['pages_with_jobs']}")
        console.print(f"  Total Posts Found: {analysis['total_posts']}")
        console.print(f"  Total Jobs Found: {analysis['total_jobs']}")
        console.print(f"  Avg Word Count: {analysis['avg_word_count']:.0f}")
        
        if analysis['titles']:
            console.print("\n  Sample Titles:")
            for title in analysis['titles'][:5]:
                console.print(f"    • {title[:60]}")
    
    def display_content(self, content_type='posts', max_display=20):
        all_items = []
        for url, data in self.scraped_data.items():
            if 'error' not in data:
                items = data.get(content_type, [])
                for item in items:
                    if content_type == 'posts':
                        all_items.append({
                            'url': url,
                            'title': item.get('title', 'No Title'),
                            'score': item.get('score', ''),
                            'text': item.get('text', '')[:300]
                        })
                    else:  # jobs
                        all_items.append({
                            'url': url,
                            'title': item.get('title', 'No Title'),
                            'company': item.get('company', ''),
                            'location': item.get('location', ''),
                            'salary': item.get('salary', '')
                        })
        
        if not all_items:
            console.print(f"[yellow]No {content_type} found[/yellow]")
            return
        
        label = "Posts" if content_type == 'posts' else "Jobs"
        console.print(f"\n[bold cyan]💬 {label} ({len(all_items)})[/bold cyan]\n")
        
        for i, item in enumerate(all_items[:max_display], 1):
            console.print(f"[bold]{i}. {item['title']}[/bold]")
            if content_type == 'jobs':
                if item.get('company'):
                    console.print(f"   🏢 {item['company']}")
                if item.get('location'):
                    console.print(f"   📍 {item['location']}")
                if item.get('salary'):
                    console.print(f"   💰 {item['salary']}")
            else:
                if item.get('score'):
                    console.print(f"   ⭐ Score: {item['score']}")
                if item.get('text'):
                    console.print(f"   {item['text'][:200]}...")
            console.print(f"   🔗 {item['url'][:60]}...")
            console.print()
    
    def save_data(self, filename=None):
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
    console.print(Panel("[bold cyan]🛡️ Advanced Web Scraper[/bold cyan]", border_style="green"))
    console.print("[dim]Handles bot detection, specialized site extraction[/dim]")
    
    if not HAS_BS4:
        console.print("[red]❌ BeautifulSoup not installed. Install: pip install beautifulsoup4 lxml[/red]")
        return
    
    import glob
    import os
    crawl_files = glob.glob("crawl_*.json")
    
    if not crawl_files:
        console.print("[yellow]No crawl data files found[/yellow]")
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
    
    scraper = AdvancedScraper(filename)
    
    if not scraper.urls:
        console.print("[red]No URLs found[/red]")
        return
    
    while True:
        console.print()
        console.print(Panel("[bold]Scraper Controls[/bold]", border_style="blue"))
        
        console.print("[cyan]📌 Options:[/cyan]")
        console.print("  1. 🔄 Start Scraping")
        console.print("  2. 📊 Show Statistics")
        console.print("  3. 💬 Show Posts")
        console.print("  4. 💼 Show Jobs")
        console.print("  5. 💾 Save Data")
        console.print("  0. Exit")
        
        choice = Prompt.ask("Select", choices=["0","1","2","3","4","5"])
        
        if choice == "0":
            break
        
        elif choice == "1":
            max_pages = int(Prompt.ask("Max pages to scrape", default="50"))
            start_from = int(Prompt.ask("Start from page index", default="0"))
            scraper.batch_scrape(max_pages=max_pages, start_from=start_from)
            scraper.analyze_scraped_data()
            scraper.display_statistics()
        
        elif choice == "2":
            if not scraper.scraped_data:
                console.print("[yellow]No data scraped yet[/yellow]")
            else:
                scraper.display_statistics()
        
        elif choice == "3":
            scraper.display_content('posts')
        
        elif choice == "4":
            scraper.display_content('jobs')
        
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
