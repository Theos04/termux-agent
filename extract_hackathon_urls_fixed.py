#!/data/data/com.termux/files/usr/bin/env python3
"""
Extract Hackathon URLs - Fixed version with proper waiting
"""

import json
import websocket
import requests
import time
import re
from typing import List, Dict, Optional

class ChromePage:
    def __init__(self, port=9258):
        self.port = port
        self.ws = None
        self.connected = False
        self.page_url = ""
        self.page_title = ""

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
                print("❌ No page found")
                return False

            self.page_title = page_tab.get('title', 'Untitled')
            self.page_url = page_tab.get('url', '')
            ws_url = page_tab.get('webSocketDebuggerUrl')

            self.ws = websocket.create_connection(ws_url, timeout=10)

            # Enable Runtime and Page domains
            for method in ["Runtime.enable", "Page.enable"]:
                self.ws.send(json.dumps({"id": 1, "method": method}))
                while True:
                    resp = self.ws.recv()
                    data = json.loads(resp)
                    if data.get('id') == 1:
                        break

            self.connected = True
            print(f"✅ Connected to: {self.page_title}")
            print(f"   URL: {self.page_url}")
            return True

        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False

    def js(self, script, await_promise=False, return_by_value=True):
        """Execute JavaScript and return result"""
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
                        print(f"❌ JS Error: {result['exceptionDetails']}")
                        return None
                    return None
            except:
                pass

        return None

    def wait_for_page_load(self, timeout=30):
        """Wait for page to fully load"""
        print(f"⏳ Waiting for page to load (max {timeout}s)...")
        start_time = time.time()
        
        # Wait for document.readyState to be complete
        while time.time() - start_time < timeout:
            ready_state = self.js("return document.readyState")
            if ready_state == "complete":
                print("✅ Page loaded successfully")
                return True
            time.sleep(1)
        
        print("⚠️ Page load timeout, continuing anyway...")
        return False

    def wait_for_content(self, timeout=30):
        """Wait for page to have content"""
        print(f"⏳ Waiting for content to appear (max {timeout}s)...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # Check if there are links on the page
            link_count = self.js("return document.querySelectorAll('a[href]').length")
            if link_count and link_count > 0:
                print(f"✅ Found {link_count} links on page")
                return True
            time.sleep(2)
        
        print("⚠️ No links found after waiting")
        return False

    def navigate_to(self, url: str) -> bool:
        """Navigate to a URL with proper waiting"""
        print(f"📄 Navigating to: {url}")
        script = f"window.location.href = '{url}'"
        self.js(script)
        
        # Wait for page load
        self.wait_for_page_load()
        
        # Wait for content
        self.wait_for_content()
        
        # Additional wait for dynamic content
        print("⏳ Waiting extra 5s for dynamic content...")
        time.sleep(5)
        
        # Get current URL to verify navigation
        current_url = self.js("return window.location.href")
        print(f"📍 Current URL: {current_url}")
        
        return True

    def get_all_links(self) -> List[Dict]:
        """Get all links from the page"""
        script = """
        return Array.from(document.querySelectorAll('a[href]')).map(a => ({
            href: a.href,
            text: a.textContent.trim().slice(0, 100)
        }));
        """
        result = self.js(script)
        return result if result else []

    def get_hackathon_urls(self) -> List[str]:
        """Extract hackathon URLs specifically"""
        script = """
        const patterns = [
            /\\/hackathons\\//,
            /\\/hackathon\\//,
            /hackathon/i,
            /oppstatus=open/,
            /oppstatus=closed/,
            /oppstatus=upcoming/
        ];
        
        const urls = new Set();
        document.querySelectorAll('a[href]').forEach(a => {
            const href = a.href;
            const text = a.textContent.trim();
            
            if (href && href.includes('unstop.com')) {
                const isHackathon = patterns.some(pattern => 
                    pattern.test(href) || pattern.test(text)
                );
                
                if (isHackathon) {
                    urls.add(href);
                }
            }
        });
        
        return Array.from(urls);
        """
        result = self.js(script)
        return result if result else []

    def get_hackathon_links_with_details(self) -> List[Dict]:
        """Get hackathon links with details"""
        script = """
        const patterns = [
            /\\/hackathons\\//,
            /\\/hackathon\\//,
            /hackathon/i,
            /oppstatus=open/,
            /oppstatus=closed/,
            /oppstatus=upcoming/
        ];
        
        const results = [];
        const allLinks = document.querySelectorAll('a[href]');
        console.log('Total links found:', allLinks.length);
        
        allLinks.forEach(a => {
            const href = a.href;
            const text = a.textContent.trim();
            
            if (href && href.includes('unstop.com')) {
                const isHackathon = patterns.some(pattern => 
                    pattern.test(href) || pattern.test(text)
                );
                
                if (isHackathon) {
                    // Try to extract hackathon ID
                    const idMatch = href.match(/\\/hackathons\\/(\\d+)/);
                    const id = idMatch ? idMatch[1] : null;
                    
                    // Try to get status from URL
                    let status = 'unknown';
                    if (href.includes('oppstatus=open')) status = 'open';
                    else if (href.includes('oppstatus=closed')) status = 'closed';
                    else if (href.includes('oppstatus=upcoming')) status = 'upcoming';
                    
                    results.push({
                        url: href,
                        text: text.slice(0, 100),
                        id: id,
                        status: status,
                        title: a.title || ''
                    });
                }
            }
        });
        
        return results;
        """
        result = self.js(script)
        return result if result else []

    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except:
                pass

def main():
    print("\n" + "=" * 60)
    print("🔍 UNSTOP HACKATHON URL EXTRACTOR (FIXED)")
    print("   Using Chrome DevTools Protocol")
    print("=" * 60)

    # Connect to Chrome
    port = 9258
    page = ChromePage(port)
    
    if not page.connect():
        print("❌ Failed to connect to Chrome")
        print("   Make sure Chrome is running with remote debugging enabled")
        return

    # Check current page
    print(f"\n📍 Current page: {page.page_url}")
    
    # If on wrong page, navigate to hackathons
    if "hackathons" not in page.page_url:
        print("📄 Navigating to hackathons page...")
        page.navigate_to("https://unstop.com/hackathons?oppstatus=open")
    
    # Get hackathon URLs from current page
    print("\n🔍 Extracting hackathon URLs...")
    hackathons = page.get_hackathon_links_with_details()
    
    if hackathons:
        print(f"✅ Found {len(hackathons)} hackathon URLs")
        for h in hackathons[:10]:
            print(f"  • {h.get('text', '')[:50]} → {h.get('url', '')}")
    else:
        print("⚠️ No hackathon URLs found on current page")
        
        # Debug: get all links
        all_links = page.get_all_links()
        print(f"\n📊 Debug: Found {len(all_links)} total links")
        
        if all_links:
            print("   Sample links:")
            for link in all_links[:10]:
                print(f"     • {link.get('text', '')[:40]} → {link.get('href', '')[:80]}")
            
            # Try to find hackathon links manually
            print("\n🔍 Searching for hackathon links manually...")
            hackathon_urls = []
            for link in all_links:
                href = link.get('href', '')
                if 'hackathon' in href.lower():
                    hackathon_urls.append(href)
            
            if hackathon_urls:
                print(f"✅ Found {len(hackathon_urls)} hackathon URLs manually!")
                for url in hackathon_urls[:10]:
                    print(f"  • {url}")
                
                # Save manually found URLs
                with open('hackathon_urls_manual.txt', 'w', encoding='utf-8') as f:
                    f.write('\n'.join(hackathon_urls))
                print("\n💾 Saved to: hackathon_urls_manual.txt")
    
    # Also try other status pages
    print("\n📄 Trying other status pages...")
    for status in ['closed', 'upcoming']:
        url = f"https://unstop.com/hackathons?oppstatus={status}"
        print(f"\n📄 Navigating to: {url}")
        page.navigate_to(url)
        
        hackathons = page.get_hackathon_links_with_details()
        if hackathons:
            print(f"✅ Found {len(hackathons)} hackathon URLs on {status} page")
            for h in hackathons[:5]:
                print(f"  • {h.get('text', '')[:40]} → {h.get('url', '')}")
    
    # Close connection
    page.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()
