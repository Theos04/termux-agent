#!/data/data/com.termux/files/usr/bin/env python3
"""
Unstop Hackathon URL Mapper with Proper Wait Times
"""

import json
import time
import requests
import sys
import os
from typing import List, Dict, Optional, Set
from urllib.parse import urlparse, urljoin
import re

# Add parent directory to path for imports
sys.path.append('/data/data/com.termux/files/home/automation/chrome-launcher')

# ============================================================================
# Unstop API Client with Better Waiting
# ============================================================================

class UnstopAPIClient:
    def __init__(self, api_base="http://127.0.0.1:5000"):
        self.api_base = api_base
        self.session_id = None
        self.session_name = "unstop"

    def start_session(self, url: str = "https://unstop.com/") -> bool:
        """Start a Chrome session for Unstop"""
        try:
            response = requests.post(
                f"{self.api_base}/session/{self.session_name}/start",
                json={"url": url}
            )
            
            if response.status_code == 200:
                data = response.json()
                self.session_id = data.get('session_id')
                print(f"✅ Session started: {self.session_id}")
                return True
            else:
                print(f"❌ Failed to start session: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error starting session: {e}")
            return False

    def get_session_status(self) -> Dict:
        """Get current session status"""
        try:
            response = requests.get(
                f"{self.api_base}/session/{self.session_name}/status"
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": response.text}
                
        except Exception as e:
            return {"error": str(e)}

    def execute_js(self, script: str, wait_time: int = 0) -> Dict:
        """Execute JavaScript in the browser with optional wait"""
        if wait_time > 0:
            print(f"  ⏳ Waiting {wait_time}s for DOM to stabilize...")
            time.sleep(wait_time)
            
        try:
            response = requests.post(
                f"{self.api_base}/session/{self.session_name}/execute",
                json={"script": script}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": response.text}
                
        except Exception as e:
            return {"error": str(e)}

    def click_element(self, selector: str) -> Dict:
        """Click an element by selector"""
        try:
            response = requests.post(
                f"{self.api_base}/session/{self.session_name}/click",
                json={"selector": selector}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": response.text}
                
        except Exception as e:
            return {"error": str(e)}

    def navigate_to(self, url: str) -> Dict:
        """Navigate to a URL"""
        try:
            response = requests.post(
                f"{self.api_base}/session/{self.session_name}/navigate",
                json={"url": url}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": response.text}
                
        except Exception as e:
            return {"error": str(e)}

    def wait_for_page_load(self, timeout: int = 15) -> bool:
        """Wait for page to load with JavaScript check"""
        print(f"  ⏳ Waiting {timeout}s for page to load...")
        time.sleep(timeout)
        
        # Check if page is loaded
        script = """
        return {
            readyState: document.readyState,
            hasContent: document.body && document.body.children.length > 0,
            url: window.location.href
        }
        """
        result = self.execute_js(script)
        if result and result.get('result'):
            state = result['result']
            print(f"  📄 Page state: readyState={state.get('readyState')}, hasContent={state.get('hasContent')}")
            return state.get('readyState') == 'complete'
        return False

    def get_page_content(self) -> Dict:
        """Get page HTML and text content"""
        script = """
        return {
            html: document.documentElement.outerHTML,
            text: document.body ? document.body.innerText : '',
            title: document.title,
            url: window.location.href,
            hasContent: document.body && document.body.children.length > 0
        }
        """
        return self.execute_js(script)

    def get_all_links(self) -> List[Dict]:
        """Get all links from the page"""
        script = """
        return Array.from(document.querySelectorAll('a[href]')).map(a => ({
            href: a.href,
            text: a.textContent.trim(),
            title: a.title || '',
            className: a.className || '',
            id: a.id || '',
            target: a.target || '',
            rel: a.rel || ''
        }));
        """
        result = self.execute_js(script)
        return result.get('result', []) if result else []

    def get_links_with_wait(self, wait_time: int = 15) -> List[Dict]:
        """Get all links after waiting for page to stabilize"""
        print(f"  ⏳ Waiting {wait_time}s for DOM to stabilize...")
        time.sleep(wait_time)
        return self.get_all_links()

    def extract_hackathon_links(self) -> List[Dict]:
        """Extract hackathon-specific links from the page"""
        script = """
        const links = [];
        const hackathonPatterns = [
            /\\/hackathons\\//,
            /\\/hackathon\\//,
            /\\/hack\\//,
            /hackathon/i,
            /oppstatus=open/,
            /oppstatus=closed/,
            /oppstatus=upcoming/
        ];
        
        document.querySelectorAll('a[href]').forEach(a => {
            const href = a.href;
            const text = a.textContent.trim();
            
            // Check if it's a hackathon link
            const isHackathon = hackathonPatterns.some(pattern => 
                pattern.test(href) || pattern.test(text)
            );
            
            if (isHackathon && href.includes('unstop.com')) {
                links.push({
                    href: href,
                    text: text,
                    title: a.title || '',
                    className: a.className || '',
                    id: a.id || ''
                });
            }
        });
        
        return links;
        """
        result = self.execute_js(script, wait_time=0)  # Wait handled separately
        return result.get('result', []) if result else []

    def extract_hackathon_links_with_wait(self, wait_time: int = 15) -> List[Dict]:
        """Extract hackathon links after waiting for DOM"""
        print(f"  ⏳ Waiting {wait_time}s for DOM to stabilize...")
        time.sleep(wait_time)
        return self.extract_hackathon_links()

    def get_pagination_links(self) -> List[str]:
        """Get pagination links from the page"""
        script = """
        const links = [];
        document.querySelectorAll('a[href*="page="], a[href*="?page="], .pagination a, .pager a, [aria-label*="page"]').forEach(a => {
            if (a.href) {
                links.push(a.href);
            }
        });
        return links;
        """
        result = self.execute_js(script)
        return result.get('result', []) if result else []

    def scroll_to_bottom(self) -> Dict:
        """Scroll to bottom of page to load more content"""
        script = """
        window.scrollTo(0, document.body.scrollHeight);
        return document.body.scrollHeight;
        """
        return self.execute_js(script)

    def click_load_more(self) -> bool:
        """Click 'Load More' button if present"""
        script = """
        const loadMoreButtons = document.querySelectorAll('button:contains("Load More"), button:contains("View More"), .load-more, .view-more');
        for (let btn of loadMoreButtons) {
            if (btn.offsetParent !== null) {
                btn.click();
                return true;
            }
        }
        return false;
        """
        result = self.execute_js(script)
        return result.get('result', False) if result else False

    def wait_for_element(self, selector: str, timeout: int = 30) -> bool:
        """Wait for an element to appear in the DOM"""
        print(f"  ⏳ Waiting for element: {selector}")
        start_time = time.time()
        
        script = f"""
        const start = Date.now();
        const timeout = {timeout * 1000};
        while (Date.now() - start < timeout) {{
            const el = document.querySelector('{selector}');
            if (el && el.offsetParent !== null) {{
                return true;
            }}
        }}
        return false;
        """
        
        result = self.execute_js(script)
        found = result.get('result', False) if result else False
        
        if found:
            print(f"  ✅ Element found: {selector}")
        else:
            print(f"  ⏱️ Element not found after {timeout}s: {selector}")
        
        return found

# ============================================================================
# Hackathon URL Mapper with Proper Waiting
# ============================================================================

class HackathonURLMapper:
    def __init__(self, client: UnstopAPIClient):
        self.client = client
        self.base_url = "https://unstop.com"
        self.hackathon_patterns = [
            r'/hackathons/',
            r'/hackathon/',
            r'/hack/',
            r'hackathon',
            r'oppstatus=open',
            r'oppstatus=closed',
            r'oppstatus=upcoming'
        ]
        self.visited_urls: Set[str] = set()
        self.hackathon_urls: List[Dict] = []
        self.pagination_urls: List[str] = []
        self.error_urls: List[str] = []
        self.wait_time = 15  # Default wait time in seconds

    def is_hackathon_url(self, url: str) -> bool:
        """Check if a URL is a hackathon-related URL"""
        if not url:
            return False
        
        url_lower = url.lower()
        
        # Check if it's a hackathon URL
        for pattern in self.hackathon_patterns:
            if re.search(pattern, url_lower):
                return True
        
        return False

    def is_hackathon_listing(self, url: str) -> bool:
        """Check if URL is a hackathon listing page"""
        if not url:
            return False
        
        # Check for listing patterns
        listing_patterns = [
            r'/hackathons/?$',
            r'/hackathons\?',
            r'/hackathons\?oppstatus=',
            r'/hackathons\?page=',
            r'/hackathons\?.*oppstatus'
        ]
        
        url_lower = url.lower()
        for pattern in listing_patterns:
            if re.search(pattern, url_lower):
                return True
        
        return False

    def extract_hackathon_ids(self, url: str) -> Optional[int]:
        """Extract hackathon ID from URL"""
        # Pattern for hackathon detail URLs
        patterns = [
            r'/hackathons/(\d+)/',
            r'/hackathon/(\d+)/',
            r'/hack/(\d+)/'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return int(match.group(1))
        
        return None

    def map_page_urls(self, url: str, max_depth: int = 3, wait_time: int = 15) -> Dict:
        """Map URLs from a specific page with proper waiting"""
        print(f"\n🔍 Mapping URLs from: {url}")
        
        if url in self.visited_urls:
            print(f"  ⏭️ Already visited: {url}")
            return {'visited': True}
        
        if max_depth <= 0:
            print(f"  ⏭️ Max depth reached")
            return {'max_depth': True}
        
        # Navigate to URL
        result = self.client.navigate_to(url)
        if result.get('error'):
            print(f"  ❌ Failed to navigate: {result['error']}")
            self.error_urls.append(url)
            return {'error': result['error']}
        
        # Wait for page load with proper timeout
        self.client.wait_for_page_load(wait_time)
        
        # Additional wait for dynamic content
        print(f"  ⏳ Waiting {wait_time}s for dynamic content to load...")
        time.sleep(wait_time)
        
        # Wait for hackathon cards to appear
        self.client.wait_for_element('.hackathon-card, .event-card, .card, [class*="hackathon"], [class*="event"]', timeout=30)
        
        # Mark as visited
        self.visited_urls.add(url)
        
        # Get all links after DOM is stable
        all_links = self.client.get_all_links()
        print(f"  📊 Found {len(all_links)} total links")
        
        # Filter hackathon links
        hackathon_links = []
        listing_links = []
        pagination_links = []
        
        for link in all_links:
            href = link.get('href', '')
            if not href:
                continue
            
            # Skip external links (keep only unstop.com)
            if 'unstop.com' not in href:
                continue
            
            # Skip anchor links
            if href.startswith('#') or href.endswith('#'):
                continue
            
            # Skip mailto, tel, etc.
            if href.startswith(('mailto:', 'tel:', 'javascript:')):
                continue
            
            # Normalize URL
            if href.startswith('/'):
                href = urljoin(self.base_url, href)
            
            # Check if it's a hackathon URL
            if self.is_hackathon_url(href):
                hackathon_data = {
                    'url': href,
                    'text': link.get('text', '')[:100],
                    'type': 'detail' if not self.is_hackathon_listing(href) else 'listing'
                }
                
                # Extract hackathon ID if present
                hackathon_id = self.extract_hackathon_ids(href)
                if hackathon_id:
                    hackathon_data['id'] = hackathon_id
                
                hackathon_links.append(hackathon_data)
                
                if not self.is_hackathon_listing(href):
                    # Only add to hackathon_urls if not already present
                    if href not in [h['url'] for h in self.hackathon_urls]:
                        self.hackathon_urls.append(hackathon_data)
            
            # Check if it's a listing page
            if self.is_hackathon_listing(href):
                listing_links.append(href)
            
            # Check if it's pagination
            if 'page=' in href or '?page=' in href:
                pagination_links.append(href)
        
        print(f"  📊 Found {len(hackathon_links)} hackathon links")
        print(f"  📊 Found {len(listing_links)} listing links")
        print(f"  📊 Found {len(pagination_links)} pagination links")
        
        # Store pagination URLs
        self.pagination_urls.extend(pagination_links)
        
        # Try to find load more button
        print("  🔄 Checking for 'Load More' button...")
        load_more = self.client.click_load_more()
        if load_more:
            print("  🔄 Clicked 'Load More' button")
            time.sleep(5)  # Wait for new content
            # Get more links after loading
            additional_links = self.client.get_all_links()
            for link in additional_links:
                href = link.get('href', '')
                if href and 'unstop.com' in href:
                    if self.is_hackathon_url(href) and href not in [h['url'] for h in self.hackathon_urls]:
                        hackathon_data = {
                            'url': href,
                            'text': link.get('text', '')[:100],
                            'type': 'detail'
                        }
                        hackathon_id = self.extract_hackathon_ids(href)
                        if hackathon_id:
                            hackathon_data['id'] = hackathon_id
                        self.hackathon_urls.append(hackathon_data)
        
        # If this is a listing page, process pagination
        if self.is_hackathon_listing(url):
            # Try to find all pagination links
            pagination_links = self.client.get_pagination_links()
            for page_link in pagination_links:
                if page_link not in self.pagination_urls:
                    self.pagination_urls.append(page_link)
        
        # Recursively process listing pages
        if max_depth > 1:
            for listing_url in listing_links[:3]:  # Limit to avoid infinite loops
                if listing_url not in self.visited_urls:
                    self.map_page_urls(listing_url, max_depth - 1, wait_time)
        
        # Process pagination pages
        if max_depth > 1:
            for page_url in pagination_links[:3]:  # Limit to 3 pages to avoid infinite loops
                if page_url not in self.visited_urls and page_url != url:
                    self.map_page_urls(page_url, max_depth - 1, wait_time)
        
        return {
            'url': url,
            'hackathon_links_found': len(hackathon_links),
            'listing_links_found': len(listing_links),
            'pagination_links_found': len(pagination_links),
            'total_hackathon_urls': len(self.hackathon_urls)
        }

    def map_hackathons(self, start_url: str = "https://unstop.com/hackathons?oppstatus=open", max_pages: int = 3, wait_time: int = 15) -> Dict:
        """Main function to map hackathon URLs"""
        print(f"\n🚀 Starting Hackathon URL Mapping")
        print(f"   Start URL: {start_url}")
        print(f"   Max pages: {max_pages}")
        print(f"   Wait time: {wait_time}s")
        print(f"   ⚠️  Please wait for pages to load...")
        
        # Start the mapping process
        self.map_page_urls(start_url, max_depth=max_pages, wait_time=wait_time)
        
        # Sort and deduplicate hackathon URLs
        unique_hackathons = {}
        for h in self.hackathon_urls:
            url = h['url']
            if url not in unique_hackathons:
                unique_hackathons[url] = h
        
        self.hackathon_urls = list(unique_hackathons.values())
        
        # Summary
        print(f"\n📊 Mapping Complete!")
        print(f"   Total pages visited: {len(self.visited_urls)}")
        print(f"   Hackathon URLs found: {len(self.hackathon_urls)}")
        print(f"   Pagination URLs found: {len(set(self.pagination_urls))}")
        print(f"   Errors: {len(self.error_urls)}")
        
        return {
            'visited_urls': list(self.visited_urls),
            'hackathon_urls': self.hackathon_urls,
            'pagination_urls': list(set(self.pagination_urls)),
            'error_urls': self.error_urls,
            'total_hackathons': len(self.hackathon_urls)
        }

    def save_results(self, filename: str = "hackathon_urls.json"):
        """Save mapping results to file"""
        results = {
            'timestamp': time.time(),
            'base_url': self.base_url,
            'visited_urls': list(self.visited_urls),
            'hackathon_urls': self.hackathon_urls,
            'pagination_urls': list(set(self.pagination_urls)),
            'error_urls': self.error_urls,
            'total_hackathons': len(self.hackathon_urls)
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n💾 Results saved to: {filename}")
        
        # Also save a simple list of URLs
        url_list = [h['url'] for h in self.hackathon_urls]
        with open('hackathon_urls.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(url_list))
        
        print(f"💾 URL list saved to: hackathon_urls.txt")

    def display_summary(self):
        """Display a summary of mapped URLs"""
        print("\n" + "=" * 60)
        print("📊 HACKATHON URL MAP SUMMARY")
        print("=" * 60)
        
        print(f"\n📍 Total Hackathon URLs: {len(self.hackathon_urls)}")
        print(f"📍 Total Pages Visited: {len(self.visited_urls)}")
        
        if self.hackathon_urls:
            print("\n📋 Hackathon URLs:")
            for i, h in enumerate(self.hackathon_urls[:10], 1):
                hackathon_id = h.get('id', 'N/A')
                print(f"  {i}. ID: {hackathon_id} - {h['url']}")
            if len(self.hackathon_urls) > 10:
                print(f"  ... and {len(self.hackathon_urls) - 10} more")
        
        if self.pagination_urls:
            print(f"\n📄 Pagination URLs: {len(set(self.pagination_urls))}")
        
        if self.error_urls:
            print(f"\n❌ Errors: {len(self.error_urls)}")
            for url in self.error_urls[:5]:
                print(f"  - {url}")

# ============================================================================
# Main Execution
# ============================================================================

def main():
    """Main entry point for hackathon URL mapping and actions"""
    print("\n" + "=" * 60)
    print("🎯 UNSTOP HACKATHON URL MAPPER & ACTION HANDLER")
    print("=" * 60)
    
    # Initialize client and mapper
    client = UnstopAPIClient()
    mapper = HackathonURLMapper(client)
    
    # Start session
    print("\n🔍 Checking session status...")
    status = client.get_session_status()
    print(f"📊 Session Status: {status}")
    
    if not status.get('connected', False):
        print("⚠️  Session not connected. Starting new session...")
        if not client.start_session("https://unstop.com/hackathons?oppstatus=open"):
            print("❌ Failed to start session")
            return
        # Wait for initial page load
        print("  ⏳ Waiting for initial page load...")
        time.sleep(15)
    
    # ========================================================================
    # Option 1: Map Hackathon URLs
    # ========================================================================
    print("\n" + "=" * 60)
    print("📊 OPTION 1: MAP HACKATHON URLS")
    print("=" * 60)
    
    # Map hackathon URLs with proper waiting
    results = mapper.map_hackathons(
        start_url="https://unstop.com/hackathons?oppstatus=open",
        max_pages=2,  # Limit to 2 pages for demo
        wait_time=15   # Wait 15 seconds per page
    )
    
    # Display summary
    mapper.display_summary()
    
    # Save results
    mapper.save_results()
    
    # ========================================================================
    # Option 2: Process Hackathon URLs
    # ========================================================================
    print("\n" + "=" * 60)
    print("🔄 OPTION 2: PROCESS HACKATHON PAGES")
    print("=" * 60)
    
    if mapper.hackathon_urls:
        print(f"\n📋 Found {len(mapper.hackathon_urls)} hackathons")
        print("   To process individual hackathons, use the quick extractor:")
        print("   ./quick_url_extractor.py")
    
    # ========================================================================
    # Option 3: Extract URLs from Specific Pages with Waiting
    # ========================================================================
    print("\n" + "=" * 60)
    print("🔍 OPTION 3: EXTRACT URLS FROM SPECIFIC PAGES")
    print("=" * 60)
    
    # Test specific pages with proper waiting
    test_urls = [
        "https://unstop.com/hackathons?oppstatus=open",
        "https://unstop.com/hackathons?oppstatus=closed",
        "https://unstop.com/hackathons?oppstatus=upcoming"
    ]
    
    for test_url in test_urls:
        print(f"\n📄 Extracting URLs from: {test_url}")
        
        # Navigate to page
        client.navigate_to(test_url)
        print(f"  ⏳ Waiting 15s for page to load...")
        time.sleep(15)
        
        # Extract hackathon links with wait
        hackathon_links = client.extract_hackathon_links_with_wait(wait_time=5)
        print(f"  Found {len(hackathon_links)} hackathon links")
        
        # Extract all links
        all_links = client.get_all_links()
        print(f"  Found {len(all_links)} total links")
        
        # Show sample if found
        if hackathon_links:
            print(f"  Sample hackathon link: {hackathon_links[0].get('href', 'N/A')}")
    
    print("\n✅ All done!")

if __name__ == "__main__":
    main()
