#!/data/data/com.termux/files/usr/bin/env python3
"""
Extract Hackathon URLs directly using Chrome DevTools Protocol (like geturl.py)
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

            # Enable Runtime
            self.ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
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

    def navigate_to(self, url: str) -> bool:
        """Navigate to a URL"""
        script = f"window.location.href = '{url}'"
        self.js(script)
        time.sleep(15)  # Wait for page to load
        return True

    def get_all_links(self) -> List[Dict]:
        """Get all links from the page"""
        script = """
        return Array.from(document.querySelectorAll('a[href]')).map(a => ({
            href: a.href,
            text: a.textContent.trim()
        }));
        """
        return self.js(script) or []

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
        return self.js(script) or []

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
        document.querySelectorAll('a[href]').forEach(a => {
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
                        text: text,
                        id: id,
                        status: status,
                        title: a.title || ''
                    });
                }
            }
        });
        
        return results;
        """
        return self.js(script) or []

    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except:
                pass

def main():
    print("\n" + "=" * 60)
    print("🔍 UNSTOP HACKATHON URL EXTRACTOR")
    print("   Using Chrome DevTools Protocol (like geturl.py)")
    print("=" * 60)

    # Connect to Chrome
    port = 9258  # Using the port from geturl.py
    page = ChromePage(port)
    
    if not page.connect():
        print("❌ Failed to connect to Chrome")
        print("   Make sure Chrome is running with remote debugging enabled")
        return

    # Pages to process
    pages = [
        "https://unstop.com/hackathons?oppstatus=open",
        "https://unstop.com/hackathons?oppstatus=closed",
        "https://unstop.com/hackathons?oppstatus=upcoming"
    ]

    all_hackathons = []
    all_urls = set()

    for page_url in pages:
        print(f"\n📄 Processing: {page_url}")
        
        # Navigate to page
        print(f"⏳ Navigating and waiting 15s...")
        page.navigate_to(page_url)
        
        # Get hackathon URLs
        hackathons = page.get_hackathon_links_with_details()
        
        if hackathons:
            print(f"✅ Found {len(hackathons)} hackathon URLs")
            for h in hackathons[:5]:
                print(f"  • {h.get('text', '')[:40]} → {h.get('url', '')}")
                all_urls.add(h.get('url', ''))
            all_hackathons.extend(hackathons)
        else:
            print("⚠️ No hackathon URLs found")
            
            # Debug: get all links
            all_links = page.get_all_links()
            print(f"   Total links on page: {len(all_links)}")
            if all_links:
                print("   Sample links:")
                for link in all_links[:5]:
                    print(f"     • {link.get('text', '')[:30]} → {link.get('href', '')[:60]}")

        # Wait between pages
        if page_url != pages[-1]:
            print(f"⏳ Waiting 5s before next page...")
            time.sleep(5)

    # Close connection
    page.close()

    # Save results
    if all_urls:
        print(f"\n📊 Total unique hackathon URLs: {len(all_urls)}")
        
        # Save to file
        with open('hackathon_urls.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(all_urls)))
        print("💾 Saved to: hackathon_urls.txt")
        
        # Save detailed JSON
        with open('hackathon_details.json', 'w', encoding='utf-8') as f:
            json.dump(all_hackathons, f, indent=2)
        print("💾 Saved to: hackathon_details.json")
        
        # Count by status
        status_counts = {}
        for h in all_hackathons:
            status = h.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"\n📊 Summary by status:")
        for status, count in status_counts.items():
            print(f"   {status}: {count}")
        
        # Show all URLs
        print(f"\n📋 All URLs:")
        for i, url in enumerate(sorted(all_urls), 1):
            print(f"  {i}. {url}")
    else:
        print("\n❌ No hackathon URLs found")

if __name__ == "__main__":
    main()
