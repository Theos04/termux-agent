#!/data/data/com.termux/files/usr/bin/env python3
"""
Extract hackathon URLs using geturl.py's ChromePage class
"""

import sys
import json
import time

# Import ChromePage from geturl.py
# First, let's check if we can import it directly
try:
    # Try to import from geturl.py
    import importlib.util
    spec = importlib.util.spec_from_file_location("geturl", "geturl.py")
    geturl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(geturl)
    ChromePage = geturl.ChromePage
    print("✅ Loaded ChromePage from geturl.py")
except Exception as e:
    print(f"❌ Could not import from geturl.py: {e}")
    print("   Trying to use the class from the current file...")
    
    # Fallback: define ChromePage here (simplified version from geturl.py)
    import websocket
    import requests
    import json
    import time
    
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
                    print("❌ No page found")
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
                print(f"❌ Connection failed: {e}")
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
                            print(f"❌ JS Error: {result['exceptionDetails']}")
                            return None
                        return None
                except:
                    pass

            return None

        def get_all_links(self):
            script = """
            return Array.from(document.querySelectorAll('a[href]')).map(a => ({
                href: a.href,
                text: a.textContent.trim()
            }));
            """
            return self.js(script) or []

        def get_hackathon_links(self):
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
                        results.push({
                            url: href,
                            text: text.slice(0, 100),
                            id: href.match(/\\/hackathons\\/(\\d+)/)?.[1] || null
                        });
                    }
                }
            });
            
            return results;
            """
            return self.js(script) or []

        def navigate_to(self, url):
            script = f"window.location.href = '{url}'"
            self.js(script)
            time.sleep(15)
            return True

        def close(self):
            if self.ws:
                try:
                    self.ws.close()
                except:
                    pass

def main():
    print("\n" + "=" * 60)
    print("🔍 EXTRACT HACKATHON URLs USING geturl.py")
    print("=" * 60)
    
    # Use port 9258 (from your Chrome session)
    port = 9258
    page = ChromePage(port)
    
    if not page.connect():
        print("❌ Failed to connect to Chrome")
        return
    
    print(f"✅ Connected to: {page.page_title}")
    print(f"   URL: {page.page_url}")
    
    # Check if we're on the right page
    if "hackathons" not in page.page_url:
        print("\n📄 Navigating to hackathons page...")
        page.navigate_to("https://unstop.com/hackathons?oppstatus=open")
        # Reconnect after navigation
        page.close()
        time.sleep(2)
        page = ChromePage(port)
        if not page.connect():
            print("❌ Failed to reconnect")
            return
        print(f"📍 Now on: {page.page_url}")
    
    # Wait extra time for dynamic content
    print("\n⏳ Waiting 10s for dynamic content to load...")
    time.sleep(10)
    
    # Get all links first (debug)
    print("\n🔍 Getting all links...")
    all_links = page.get_all_links()
    print(f"   Found {len(all_links)} total links")
    
    if all_links:
        print("\n📋 Sample links:")
        for link in all_links[:10]:
            print(f"   • {link.get('text', '')[:40]} → {link.get('href', '')[:80]}")
    
    # Get hackathon links
    print("\n🔍 Extracting hackathon URLs...")
    hackathons = page.get_hackathon_links()
    
    if hackathons:
        print(f"✅ Found {len(hackathons)} hackathon URLs!")
        print("\n📋 Hackathon URLs:")
        for h in hackathons:
            print(f"   • {h.get('text', '')[:50]} → {h.get('url', '')}")
        
        # Save to file
        urls = [h['url'] for h in hackathons]
        with open('hackathon_urls.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(urls))
        print(f"\n💾 Saved {len(urls)} URLs to hackathon_urls.txt")
        
        # Save full details
        with open('hackathon_details.json', 'w', encoding='utf-8') as f:
            json.dump(hackathons, f, indent=2)
        print("💾 Saved details to hackathon_details.json")
    else:
        print("❌ No hackathon URLs found")
        print("\n💡 Suggestions:")
        print("   1. Try running geturl.py manually first to see the page")
        print("   2. Make sure you're logged into Unstop")
        print("   3. Try navigating to the page manually in Chrome")
        print("   4. The page structure might have changed")
    
    page.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()
