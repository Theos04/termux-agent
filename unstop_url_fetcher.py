#!/usr/bin/env python3
"""
Enhanced URL Fetcher & Database Manager
Fetches page titles, extracts jobs, and stores everything in SQLite
"""

import json
import websocket
import requests
import sqlite3
import time
import os
import hashlib
import sys
from datetime import datetime
from typing import List, Dict, Optional, Any
from urllib.parse import urlparse
from contextlib import contextmanager
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import box
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

console = Console()

# ============================================================================
# Import UnstopJobExtractor (with fallback)
# ============================================================================

try:
    # Try to import from the same directory
    from web_scraper_unstop import UnstopJobExtractor
    HAS_UNSTOP_EXTRACTOR = True
    console.print("[green]✅ Loaded UnstopJobExtractor[/green]")
except ImportError:
    try:
        # Try from parent directory
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from web_scraper_unstop import UnstopJobExtractor
        HAS_UNSTOP_EXTRACTOR = True
        console.print("[green]✅ Loaded UnstopJobExtractor from parent directory[/green]")
    except ImportError:
        HAS_UNSTOP_EXTRACTOR = False
        console.print("[yellow]⚠️  UnstopJobExtractor not found - using basic extraction[/yellow]")

# ============================================================================
# Enhanced Database Manager
# ============================================================================

class EnhancedURLDatabase:
    """Enhanced SQLite database with better URL management"""
    
    def __init__(self, db_path="urls.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Initialize database schema with enhancements"""
        with self.get_connection() as conn:
            # Main URLs table with more fields
            conn.execute("""
                CREATE TABLE IF NOT EXISTS urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    domain TEXT,
                    path TEXT,
                    query_params TEXT,
                    title TEXT,
                    page_type TEXT,
                    status_code INTEGER,
                    content_hash TEXT,
                    visited_at TIMESTAMP,
                    last_seen_at TIMESTAMP,
                    visit_count INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # URL tags
            conn.execute("""
                CREATE TABLE IF NOT EXISTS url_tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url_id INTEGER,
                    tag TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (url_id) REFERENCES urls(id) ON DELETE CASCADE,
                    UNIQUE(url_id, tag)
                )
            """)
            
            # Job listings with enhanced fields
            conn.execute("""
                CREATE TABLE IF NOT EXISTS job_listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url_id INTEGER,
                    job_title TEXT,
                    company TEXT,
                    location TEXT,
                    job_type TEXT,
                    salary TEXT,
                    experience TEXT,
                    skills TEXT,
                    posted_date TEXT,
                    deadline TEXT,
                    payment_status TEXT DEFAULT 'Unpaid',
                    applied BOOLEAN DEFAULT 0,
                    application_date TIMESTAMP,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (url_id) REFERENCES urls(id) ON DELETE CASCADE,
                    UNIQUE(url_id, job_title, company)
                )
            """)
            
            # Page content cache
            conn.execute("""
                CREATE TABLE IF NOT EXISTS page_content (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url_id INTEGER,
                    content_type TEXT,
                    content TEXT,
                    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (url_id) REFERENCES urls(id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_urls_domain ON urls(domain)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_urls_url ON urls(url)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_urls_visited ON urls(visited_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_url_tags ON url_tags(tag)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company ON job_listings(company)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_location ON job_listings(location)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_applied ON job_listings(applied)")
    
    @contextmanager
    def get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def add_url(self, url: str, title: str = "", metadata: Dict = None) -> int:
        """Add or update URL with title"""
        with self.get_connection() as conn:
            parsed = urlparse(url)
            domain = parsed.netloc
            path = parsed.path or "/"
            query = parsed.query or ""
            content_hash = hashlib.md5(f"{url}{title}".encode()).hexdigest()[:16]
            
            # Check if URL exists
            cursor = conn.execute("SELECT id, visit_count FROM urls WHERE url = ?", (url,))
            existing = cursor.fetchone()
            
            if existing:
                # Update - only update title if it was "Untitled" or empty
                if not title or title == "Untitled":
                    # Keep existing title if we have one
                    cursor = conn.execute("SELECT title FROM urls WHERE id = ?", (existing['id'],))
                    current = cursor.fetchone()
                    if current and current['title'] and current['title'] != "Untitled":
                        title = current['title']
                
                conn.execute("""
                    UPDATE urls 
                    SET title = COALESCE(?, title),
                        last_seen_at = CURRENT_TIMESTAMP,
                        visit_count = visit_count + 1,
                        updated_at = CURRENT_TIMESTAMP,
                        metadata = COALESCE(?, metadata)
                    WHERE id = ?
                """, (title, json.dumps(metadata) if metadata else None, existing['id']))
                return existing['id']
            else:
                # Insert new
                cursor = conn.execute("""
                    INSERT INTO urls (
                        url, domain, path, query_params, title, 
                        content_hash, visited_at, last_seen_at, visit_count,
                        metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, ?)
                """, (url, domain, path, query, title or "Untitled", content_hash,
                      json.dumps(metadata) if metadata else None))
                return cursor.lastrowid
    
    def add_tag(self, url_id: int, tag: str):
        """Add tag to URL"""
        with self.get_connection() as conn:
            conn.execute("INSERT OR IGNORE INTO url_tags (url_id, tag) VALUES (?, ?)", (url_id, tag))
    
    def add_job(self, url_id: int, job_data: Dict) -> int:
        """Add or update job listing"""
        with self.get_connection() as conn:
            # Check if job exists
            cursor = conn.execute("""
                SELECT id FROM job_listings 
                WHERE url_id = ? AND job_title = ? AND company = ?
            """, (url_id, job_data.get('title'), job_data.get('company')))
            
            existing = cursor.fetchone()
            if existing:
                # Update
                conn.execute("""
                    UPDATE job_listings 
                    SET location = ?,
                        job_type = ?,
                        salary = ?,
                        experience = ?,
                        skills = ?,
                        posted_date = ?,
                        deadline = ?,
                        metadata = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (
                    job_data.get('location', ''),
                    job_data.get('job_type', ''),
                    job_data.get('salary', ''),
                    job_data.get('experience', ''),
                    json.dumps(job_data.get('skills', [])),
                    job_data.get('posted_date', ''),
                    job_data.get('deadline', ''),
                    json.dumps(job_data.get('metadata', {})),
                    existing['id']
                ))
                return existing['id']
            else:
                # Insert new
                cursor = conn.execute("""
                    INSERT INTO job_listings (
                        url_id, job_title, company, location, job_type,
                        salary, experience, skills, posted_date, deadline,
                        metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    url_id,
                    job_data.get('title', 'Untitled'),
                    job_data.get('company', ''),
                    job_data.get('location', ''),
                    job_data.get('job_type', ''),
                    job_data.get('salary', ''),
                    job_data.get('experience', ''),
                    json.dumps(job_data.get('skills', [])),
                    job_data.get('posted_date', ''),
                    job_data.get('deadline', ''),
                    json.dumps(job_data.get('metadata', {}))
                ))
                return cursor.lastrowid
    
    def get_urls(self, domain: str = None, tag: str = None, limit: int = 100) -> List[Dict]:
        """Get URLs with tags"""
        with self.get_connection() as conn:
            query = """
                SELECT u.*, GROUP_CONCAT(t.tag) as tags
                FROM urls u
                LEFT JOIN url_tags t ON u.id = t.url_id
                WHERE 1=1
            """
            params = []
            
            if domain:
                query += " AND u.domain = ?"
                params.append(domain)
            
            if tag:
                query += " AND u.id IN (SELECT url_id FROM url_tags WHERE tag = ?)"
                params.append(tag)
            
            query += " GROUP BY u.id ORDER BY u.last_seen_at DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            results = []
            for row in cursor.fetchall():
                row_dict = dict(row)
                # Handle None values
                for key, value in row_dict.items():
                    if value is None:
                        row_dict[key] = ''
                results.append(row_dict)
            return results
    
    def get_jobs(self, company: str = None, location: str = None, 
                 applied: bool = None, limit: int = 100) -> List[Dict]:
        """Get job listings"""
        with self.get_connection() as conn:
            query = """
                SELECT j.*, u.url, u.title as page_title
                FROM job_listings j
                JOIN urls u ON j.url_id = u.id
                WHERE 1=1
            """
            params = []
            
            if company:
                query += " AND j.company LIKE ?"
                params.append(f"%{company}%")
            
            if location:
                query += " AND j.location LIKE ?"
                params.append(f"%{location}%")
            
            if applied is not None:
                query += " AND j.applied = ?"
                params.append(1 if applied else 0)
            
            query += " ORDER BY j.created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            results = []
            for row in cursor.fetchall():
                row_dict = dict(row)
                for key, value in row_dict.items():
                    if value is None:
                        row_dict[key] = ''
                results.append(row_dict)
            return results
    
    def mark_applied(self, job_id: int):
        """Mark job as applied"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE job_listings 
                SET applied = 1, application_date = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (job_id,))
    
    def get_statistics(self) -> Dict:
        """Get database statistics"""
        with self.get_connection() as conn:
            stats = {}
            
            cursor = conn.execute("SELECT COUNT(*) as count FROM urls")
            stats['total_urls'] = cursor.fetchone()['count']
            
            cursor = conn.execute("SELECT COUNT(DISTINCT domain) as count FROM urls")
            stats['unique_domains'] = cursor.fetchone()['count']
            
            cursor = conn.execute("SELECT COUNT(*) as count FROM job_listings")
            stats['total_jobs'] = cursor.fetchone()['count']
            
            cursor = conn.execute("SELECT COUNT(*) as count FROM job_listings WHERE applied = 1")
            stats['applied_jobs'] = cursor.fetchone()['count']
            
            cursor = conn.execute("""
                SELECT domain, COUNT(*) as count 
                FROM urls 
                GROUP BY domain 
                ORDER BY count DESC 
                LIMIT 10
            """)
            stats['top_domains'] = [dict(row) for row in cursor.fetchall()]
            
            return stats
    
    def get_urls_without_titles(self) -> List[Dict]:
        """Get URLs that need title fetching"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, url FROM urls 
                WHERE title = 'Untitled' OR title IS NULL OR title = ''
                ORDER BY last_seen_at DESC
                LIMIT 100
            """)
            return [dict(row) for row in cursor.fetchall()]

# ============================================================================
# Enhanced Chrome URL Fetcher
# ============================================================================

class EnhancedChromeURLFetcher:
    """Enhanced Chrome URL fetcher with title fetching and job extraction"""
    
    def __init__(self, port=9226):
        self.port = port
        self.ws = None
        self.connected = False
        self.db = EnhancedURLDatabase()
        self.current_url = None
        
    def connect(self):
        """Connect to Chrome DevTools"""
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
            
            # Enable Runtime
            self.ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
            while True:
                resp = self.ws.recv()
                data = json.loads(resp)
                if data.get('id') == 1:
                    break
            
            self.connected = True
            self.current_url = page_tab.get('url', '')
            console.print(f"[green]✅ Connected to Chrome on port {self.port}[/green]")
            return True
            
        except Exception as e:
            console.print(f"[red]Connection failed: {e}[/red]")
            return False
    
    def js(self, script, await_promise=False):
        """Execute JavaScript"""
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
                    elif 'error' in result:
                        return None
                    return None
            except Exception:
                pass
        
        return None
    
    def get_current_url(self) -> str:
        """Get current page URL"""
        url = self.js("window.location.href")
        if url:
            self.current_url = url
        return url or self.current_url
    
    def get_page_title(self) -> str:
        """Get current page title"""
        title = self.js("document.title")
        return title or "Untitled"
    
    def fetch_page_title_for_url(self, url: str) -> str:
        """Fetch title for a specific URL by navigating to it"""
        # Store current URL to return later
        original_url = self.current_url
        
        try:
            # Navigate to the URL
            self.js(f"window.location.href = '{url}'")
            time.sleep(2)  # Wait for page to load
            
            # Get title
            title = self.get_page_title()
            
            # Navigate back
            if original_url:
                self.js(f"window.location.href = '{original_url}'")
                time.sleep(2)
            
            return title
        except Exception as e:
            console.print(f"[red]Error fetching title for {url}: {e}[/red]")
            return "Untitled"
    
    def get_all_links(self) -> List[str]:
        """Get all links from page"""
        script = """
        (function() {
            const links = document.querySelectorAll('a[href]');
            const unique = new Set();
            links.forEach(a => {
                try {
                    const href = a.href;
                    if (href && !href.startsWith('javascript:') && !href.startsWith('#') && 
                        !href.startsWith('mailto:') && !href.startsWith('tel:')) {
                        unique.add(href);
                    }
                } catch(e) {}
            });
            return Array.from(unique);
        })()
        """
        return self.js(script) or []
    
    def get_job_links(self) -> List[str]:
        """Get job-related links"""
        script = """
        (function() {
            const jobLinks = [];
            const patterns = ['/opportunities/', '/jobs/', '/careers/', '/hiring/', '/openings/'];
            const links = document.querySelectorAll('a[href]');
            
            links.forEach(a => {
                try {
                    const href = a.href;
                    if (href) {
                        const lower = href.toLowerCase();
                        if (patterns.some(p => lower.includes(p)) && !jobLinks.includes(href)) {
                            jobLinks.push(href);
                        }
                    }
                } catch(e) {}
            });
            return jobLinks;
        })()
        """
        return self.js(script) or []
    
    def fetch_and_store_current_page(self, tags: List[str] = None) -> int:
        """Store current page with tags"""
        url = self.get_current_url()
        if not url:
            console.print("[red]Failed to get current URL[/red]")
            return None
        
        title = self.get_page_title()
        metadata = {
            'title': title,
            'source': 'direct_fetch',
            'timestamp': datetime.now().isoformat()
        }
        
        url_id = self.db.add_url(url, title, metadata)
        
        if tags:
            for tag in tags:
                self.db.add_tag(url_id, tag)
        
        console.print(f"[green]✅ Stored: {title[:50]}...[/green]")
        console.print(f"[dim]   URL: {url[:80]}[/dim]")
        
        return url_id
    
    def fetch_and_store_all_links(self, tags: List[str] = None, 
                                   fetch_titles: bool = False) -> List[int]:
        """Fetch and store all links from current page"""
        links = self.get_all_links()
        console.print(f"[yellow]Found {len(links)} links[/yellow]")
        
        stored_ids = []
        
        # Filter to unique, valid URLs
        valid_links = []
        for link in links:
            if link and link.startswith(('http://', 'https://')):
                # Remove duplicates
                if link not in valid_links:
                    valid_links.append(link)
        
        console.print(f"[dim]Filtered to {len(valid_links)} unique valid URLs[/dim]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console
        ) as progress:
            task = progress.add_task("Storing links...", total=len(valid_links))
            
            for link in valid_links:
                try:
                    # Determine link type
                    link_tags = tags.copy() if tags else []
                    if '/opportunities/' in link or '/jobs/' in link:
                        link_tags.append('job')
                    if '/hackathon/' in link:
                        link_tags.append('hackathon')
                    if '/competition/' in link:
                        link_tags.append('competition')
                    
                    # Store URL (initially without title)
                    url_id = self.db.add_url(link, "Untitled", {"source": "link_discovery"})
                    
                    if link_tags:
                        for tag in link_tags:
                            self.db.add_tag(url_id, tag)
                    
                    stored_ids.append(url_id)
                    progress.advance(task)
                    
                except Exception as e:
                    console.print(f"[red]Error storing link: {e}[/red]")
                    progress.advance(task)
        
        # Optionally fetch titles for stored URLs
        if fetch_titles and stored_ids:
            console.print("[yellow]Fetching page titles...[/yellow]")
            self._fetch_titles_for_urls(stored_ids[:20])  # Limit to 20 to avoid too much navigation
        
        console.print(f"[green]✅ Stored {len(stored_ids)} links[/green]")
        return stored_ids
    
    def _fetch_titles_for_urls(self, url_ids: List[int]):
        """Fetch titles for a list of URL IDs"""
        with Progress(console=console) as progress:
            task = progress.add_task("Fetching titles...", total=len(url_ids))
            
            for url_id in url_ids:
                try:
                    # Get URL from database
                    urls = self.db.get_urls(limit=1)
                    url_data = None
                    for u in urls:
                        if u.get('id') == url_id:
                            url_data = u
                            break
                    
                    if url_data and url_data.get('url'):
                        title = self.fetch_page_title_for_url(url_data['url'])
                        if title and title != "Untitled":
                            # Update the title
                            self.db.add_url(url_data['url'], title)
                    
                    progress.advance(task)
                except Exception as e:
                    console.print(f"[red]Error fetching title: {e}[/red]")
                    progress.advance(task)
    
    def fetch_job_listings(self) -> List[Dict]:
        """Fetch job listings using specialized extractor"""
        if HAS_UNSTOP_EXTRACTOR:
            try:
                console.print("[cyan]Using UnstopJobExtractor...[/cyan]")
                extractor = UnstopJobExtractor(self.port)
                if extractor.connect():
                    jobs = extractor.extract_jobs()
                    extractor.close()
                    
                    if jobs:
                        # Store jobs in database
                        url = self.get_current_url()
                        url_id = self.db.add_url(url, self.get_page_title())
                        
                        for job in jobs:
                            self.db.add_job(url_id, job)
                        
                        console.print(f"[green]✅ Extracted {len(jobs)} jobs with UnstopJobExtractor[/green]")
                        return jobs
                else:
                    console.print("[red]Failed to connect UnstopJobExtractor[/red]")
                    return self._basic_job_extraction()
                    
            except Exception as e:
                console.print(f"[red]UnstopJobExtractor error: {e}[/red]")
                return self._basic_job_extraction()
        else:
            return self._basic_job_extraction()
    
    def _basic_job_extraction(self) -> List[Dict]:
        """Basic job extraction fallback"""
        console.print("[yellow]Using basic job extraction...[/yellow]")
        
        script = """
        (function() {
            const jobs = [];
            const selectors = [
                '[class*="job"]',
                '[class*="opportunity"]',
                '[class*="listing"]',
                '[class*="card"]'
            ];
            
            const elements = document.querySelectorAll(selectors.join(','));
            
            elements.forEach(el => {
                try {
                    const title = el.querySelector('h3, h2, [class*="title"]');
                    const company = el.querySelector('[class*="company"], [class*="org"]');
                    const location = el.querySelector('[class*="location"]');
                    const salary = el.querySelector('[class*="salary"], [class*="stipend"]');
                    
                    if (title && title.textContent.trim()) {
                        jobs.push({
                            title: title.textContent.trim(),
                            company: company ? company.textContent.trim() : '',
                            location: location ? location.textContent.trim() : '',
                            salary: salary ? salary.textContent.trim() : '',
                            job_type: '',
                            experience: '',
                            skills: [],
                            posted_date: '',
                            deadline: ''
                        });
                    }
                } catch(e) {}
            });
            
            return jobs;
        })()
        """
        
        jobs = self.js(script) or []
        
        if jobs:
            # Store jobs in database
            url = self.get_current_url()
            url_id = self.db.add_url(url, self.get_page_title())
            for job in jobs:
                self.db.add_job(url_id, job)
            
            console.print(f"[green]✅ Extracted {len(jobs)} jobs with basic method[/green]")
        
        return jobs
    
    def enrich_urls_with_titles(self, limit: int = 50) -> int:
        """Enrich stored URLs with titles"""
        urls = self.db.get_urls_without_titles()
        if not urls:
            console.print("[yellow]No URLs need titles[/yellow]")
            return 0
        
        console.print(f"[yellow]Found {len(urls)} URLs without titles[/yellow]")
        console.print("[dim]Fetching titles (this may take a while)...[/dim]")
        
        enriched = 0
        for url_data in urls[:limit]:
            try:
                title = self.fetch_page_title_for_url(url_data['url'])
                if title and title != "Untitled":
                    self.db.add_url(url_data['url'], title)
                    enriched += 1
                    console.print(f"[dim]✓ {title[:40]}...[/dim]")
                time.sleep(0.5)  # Be gentle with the browser
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
        
        console.print(f"[green]✅ Enriched {enriched} URLs with titles[/green]")
        return enriched
    
    def close(self):
        """Close connection"""
        if self.ws:
            try:
                self.ws.close()
            except:
                pass

# ============================================================================
# CLI Interface
# ============================================================================

class URLFetcherCLI:
    """Interactive CLI"""
    
    def __init__(self):
        self.fetcher = None
        self.db = EnhancedURLDatabase()
    
    def run(self):
        """Main loop"""
        console.clear()
        console.print(Panel("[bold cyan]🌐 Enhanced URL Fetcher & Database Manager[/bold cyan]", 
                          border_style="green"))
        console.print("[dim]Fetch, store, and manage URLs from Chrome with job extraction[/dim]\n")
        
        port = int(Prompt.ask("Chrome port", default="9226"))
        self.fetcher = EnhancedChromeURLFetcher(port)
        
        if not self.fetcher.connect():
            console.print("[red]Failed to connect to Chrome[/red]")
            return
        
        while True:
            current_url = self.fetcher.get_current_url() or 'Unknown'
            console.print()
            console.print(Panel(
                f"[bold]Connected to Chrome on port {port}[/bold]\n"
                f"[dim]Current URL: {current_url[:60]}...[/dim]" if len(current_url) > 60 
                else f"[dim]Current URL: {current_url}[/dim]",
                border_style="blue"
            ))
            
            # Show counts
            stats = self.db.get_statistics()
            console.print(f"[dim]📊 {stats.get('total_urls', 0)} URLs • {stats.get('total_jobs', 0)} Jobs[/dim]")
            
            console.print("\n[cyan]📌 Options:[/cyan]")
            console.print("  1. Store Current Page")
            console.print("  2. Fetch & Store All Links")
            console.print("  3. Fetch & Store All Links (with Titles)")
            console.print("  4. Fetch Job Listings")
            console.print("  5. View Stored URLs")
            console.print("  6. View Stored Jobs")
            console.print("  7. View Statistics")
            console.print("  8. Search URLs")
            console.print("  9. Search Jobs")
            console.print(" 10. Mark Job as Applied")
            console.print(" 11. Enrich URLs with Titles")
            console.print(" 12. Export Data")
            console.print("  0. Exit")
            
            choice = Prompt.ask("Select", choices=["0","1","2","3","4","5","6","7","8","9","10","11","12"])
            
            if choice == "0":
                break
            
            elif choice == "1":
                tags = Prompt.ask("Tags (comma-separated)", default="")
                tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
                self.fetcher.fetch_and_store_current_page(tag_list)
            
            elif choice == "2":
                tags = Prompt.ask("Tags (comma-separated)", default="")
                tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
                self.fetcher.fetch_and_store_all_links(tag_list, fetch_titles=False)
            
            elif choice == "3":
                tags = Prompt.ask("Tags (comma-separated)", default="")
                tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
                self.fetcher.fetch_and_store_all_links(tag_list, fetch_titles=True)
            
            elif choice == "4":
                jobs = self.fetcher.fetch_job_listings()
                if jobs:
                    self._display_jobs_table(jobs[:20])
            
            elif choice == "5":
                domain = Prompt.ask("Filter by domain", default="")
                tag = Prompt.ask("Filter by tag", default="")
                limit = int(Prompt.ask("Limit", default="50"))
                
                urls = self.db.get_urls(
                    domain=domain if domain else None,
                    tag=tag if tag else None,
                    limit=limit
                )
                if urls:
                    self._display_urls_table(urls)
                else:
                    console.print("[yellow]No URLs found[/yellow]")
            
            elif choice == "6":
                company = Prompt.ask("Filter by company", default="")
                location = Prompt.ask("Filter by location", default="")
                applied = Prompt.ask("Show only applied? (yes/no)", default="no")
                limit = int(Prompt.ask("Limit", default="50"))
                
                jobs = self.db.get_jobs(
                    company=company if company else None,
                    location=location if location else None,
                    applied=(applied.lower() == "yes"),
                    limit=limit
                )
                if jobs:
                    self._display_jobs_table(jobs)
                else:
                    console.print("[yellow]No jobs found[/yellow]")
            
            elif choice == "7":
                stats = self.db.get_statistics()
                self._display_stats(stats)
            
            elif choice == "8":
                search_term = Prompt.ask("Search term")
                urls = self.db.get_urls(limit=500)
                results = []
                for u in urls:
                    url_text = u.get('url', '') or ''
                    title_text = u.get('title', '') or ''
                    if search_term.lower() in url_text.lower() or search_term.lower() in title_text.lower():
                        results.append(u)
                
                if results:
                    console.print(f"[green]Found {len(results)} URLs[/green]")
                    self._display_urls_table(results[:50])
                else:
                    console.print("[yellow]No matching URLs found[/yellow]")
            
            elif choice == "9":
                search_term = Prompt.ask("Search term (title, company, skills)")
                jobs = self.db.get_jobs(limit=500)
                results = []
                for job in jobs:
                    job_title = job.get('job_title', '') or ''
                    company = job.get('company', '') or ''
                    skills = job.get('skills', '[]')
                    try:
                        skills_list = json.loads(skills) if skills else []
                    except:
                        skills_list = []
                    skills_text = ' '.join(skills_list)
                    
                    searchable = f"{job_title} {company} {skills_text}".lower()
                    if search_term.lower() in searchable:
                        results.append(job)
                
                if results:
                    console.print(f"[green]Found {len(results)} jobs[/green]")
                    self._display_jobs_table(results[:50])
                else:
                    console.print("[yellow]No matching jobs found[/yellow]")
            
            elif choice == "10":
                jobs = self.db.get_jobs(applied=False, limit=30)
                if not jobs:
                    console.print("[yellow]No unapplied jobs found[/yellow]")
                    continue
                
                console.print("[bold]Unapplied Jobs:[/bold]")
                for i, job in enumerate(jobs[:15], 1):
                    title = job.get('job_title', '') or 'Untitled'
                    company = job.get('company', '') or 'Unknown'
                    console.print(f"  {i}. {title[:40]} - {company[:20]}")
                
                if len(jobs) > 15:
                    console.print(f"[dim]... and {len(jobs)-15} more[/dim]")
                
                job_num = int(Prompt.ask("Job number to mark as applied (0 to cancel)", default="0"))
                if job_num > 0 and job_num <= len(jobs):
                    self.db.mark_applied(jobs[job_num-1]['id'])
                    console.print("[green]✅ Marked as applied![/green]")
            
            elif choice == "11":
                limit = int(Prompt.ask("Number of URLs to enrich", default="20"))
                count = self.fetcher.enrich_urls_with_titles(limit)
                console.print(f"[green]✅ Enriched {count} URLs with titles[/green]")
            
            elif choice == "12":
                format_type = Prompt.ask("Export format (json/markdown)", default="json")
                filename = Prompt.ask("Filename", default=f"url_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                
                if format_type == "json":
                    self._export_json(filename)
                elif format_type == "markdown":
                    self._export_markdown(filename)
                else:
                    console.print("[red]Invalid format[/red]")
            
            if choice != "0":
                console.print()
                input("Press Enter to continue...")
        
        self.fetcher.close()
        console.print("[green]Goodbye! 👋[/green]")
    
    def _display_urls_table(self, urls: List[Dict]):
        """Display URLs table"""
        if not urls:
            console.print("[yellow]No URLs found[/yellow]")
            return
        
        table = Table(title=f"📋 URLs ({len(urls)})", box=box.ROUNDED)
        table.add_column("ID", style="cyan", width=5)
        table.add_column("Title", style="green", max_width=30)
        table.add_column("Domain", style="yellow", max_width=20)
        table.add_column("Visits", style="magenta", width=6)
        table.add_column("Tags", style="blue", max_width=20)
        table.add_column("Last Seen", style="dim", width=19)
        
        for url in urls[:50]:
            title = (url.get('title') or 'Untitled')[:28]
            domain = (url.get('domain') or '')[:18]
            tags = (url.get('tags') or '')[:18]
            last_seen = (url.get('last_seen_at') or '')[:19]
            
            table.add_row(
                str(url.get('id', '')),
                title,
                domain,
                str(url.get('visit_count', 0)),
                tags,
                last_seen
            )
        
        console.print(table)
        if len(urls) > 50:
            console.print(f"[dim]... and {len(urls)-50} more[/dim]")
    
    def _display_jobs_table(self, jobs: List[Dict]):
        """Display jobs table"""
        if not jobs:
            console.print("[yellow]No jobs found[/yellow]")
            return
        
        table = Table(title=f"💼 Job Listings ({len(jobs)})", box=box.ROUNDED)
        table.add_column("ID", style="cyan", width=5)
        table.add_column("Title", style="green", max_width=28)
        table.add_column("Company", style="yellow", max_width=18)
        table.add_column("Location", style="blue", max_width=18)
        table.add_column("Salary", style="magenta", max_width=15)
        table.add_column("Applied", style="green", width=8)
        
        for job in jobs[:50]:
            title = (job.get('job_title') or 'Untitled')[:26]
            company = (job.get('company') or 'Unknown')[:16]
            location = (job.get('location') or 'N/A')[:16]
            salary = (job.get('salary') or 'N/A')[:13]
            applied = "✅" if job.get('applied', 0) else "⬜"
            
            table.add_row(
                str(job.get('id', '')),
                title,
                company,
                location,
                salary,
                applied
            )
        
        console.print(table)
        if len(jobs) > 50:
            console.print(f"[dim]... and {len(jobs)-50} more[/dim]")
    
    def _display_stats(self, stats: Dict):
        """Display statistics"""
        console.print(Panel("[bold]📊 Database Statistics[/bold]", border_style="green"))
        
        table = Table(box=box.SIMPLE)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Total URLs", str(stats.get('total_urls', 0)))
        table.add_row("Unique Domains", str(stats.get('unique_domains', 0)))
        table.add_row("Total Jobs", str(stats.get('total_jobs', 0)))
        table.add_row("Applied Jobs", str(stats.get('applied_jobs', 0)))
        
        total_jobs = stats.get('total_jobs', 0)
        applied_jobs = stats.get('applied_jobs', 0)
        if total_jobs > 0:
            rate = (applied_jobs / total_jobs) * 100
            table.add_row("Application Rate", f"{rate:.1f}%")
        
        console.print(table)
        
        if stats.get('top_domains'):
            console.print("\n[bold cyan]Top Domains:[/bold cyan]")
            for domain in stats['top_domains'][:10]:
                console.print(f"  • {domain.get('domain', 'Unknown')}: {domain.get('count', 0)} URLs")
    
    def _export_json(self, filename: str):
        """Export to JSON"""
        filename = f"{filename}.json"
        data = {
            'exported_at': datetime.now().isoformat(),
            'urls': self.db.get_urls(limit=1000),
            'jobs': self.db.get_jobs(limit=1000),
            'statistics': self.db.get_statistics()
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        
        console.print(f"[green]✅ Exported to {filename}[/green]")
    
    def _export_markdown(self, filename: str):
        """Export to Markdown"""
        filename = f"{filename}.md"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"# 🌐 URL Database Export\n\n")
            f.write(f"**Exported At:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            stats = self.db.get_statistics()
            f.write("## 📊 Statistics\n\n")
            f.write(f"- **Total URLs:** {stats.get('total_urls', 0)}\n")
            f.write(f"- **Unique Domains:** {stats.get('unique_domains', 0)}\n")
            f.write(f"- **Total Jobs:** {stats.get('total_jobs', 0)}\n")
            f.write(f"- **Applied Jobs:** {stats.get('applied_jobs', 0)}\n\n")
            
            urls = self.db.get_urls(limit=50)
            if urls:
                f.write("## 📋 Recent URLs\n\n")
                for url in urls[:20]:
                    title = (url.get('title') or 'Untitled')[:50]
                    url_str = (url.get('url') or '')
                    f.write(f"- **{title}**\n")
                    f.write(f"  - URL: {url_str}\n")
                    f.write(f"  - Visits: {url.get('visit_count', 0)}\n\n")
            
            jobs = self.db.get_jobs(limit=50)
            if jobs:
                f.write("## 💼 Job Listings\n\n")
                for job in jobs[:20]:
                    title = (job.get('job_title') or 'Untitled')[:50]
                    company = (job.get('company') or 'N/A')[:30]
                    location = (job.get('location') or 'N/A')[:30]
                    salary = (job.get('salary') or 'N/A')
                    applied = '✅ Yes' if job.get('applied') else '⬜ No'
                    
                    f.write(f"### {title}\n\n")
                    f.write(f"- **Company:** {company}\n")
                    f.write(f"- **Location:** {location}\n")
                    f.write(f"- **Salary:** {salary}\n")
                    f.write(f"- **Applied:** {applied}\n\n")
        
        console.print(f"[green]✅ Exported to {filename}[/green]")

# ============================================================================
# Main
# ============================================================================

def main():
    """Main entry point"""
    cli = URLFetcherCLI()
    try:
        cli.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
