#!/usr/bin/env python3
"""
Dynamic Chrome JavaScript Executor - Fixed with Python websocket
"""

import json
import subprocess
import sys
import os
import time
import tempfile
import threading
import queue
from typing import Optional, Dict, List, Any

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

try:
    import websocket
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client"])
    import websocket

class ChromeJSExecutor:
    def __init__(self, port: int = 9227):
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.ws_url = None
        self.tabs = []

    def get_tabs(self) -> List[Dict]:
        """Get all tabs from Chrome"""
        try:
            response = requests.get(f"{self.base_url}/json", timeout=5)
            if response.status_code == 200:
                tabs = response.json()
                self.tabs = [t for t in tabs if t.get('type') == 'page']
                return self.tabs
            return []
        except Exception as e:
            print(f"❌ Error fetching tabs: {e}")
            return []

    def get_websocket_url(self, tab_index: int = 0) -> Optional[str]:
        """Get WebSocket URL for a specific tab"""
        if not self.tabs:
            self.get_tabs()

        if not self.tabs:
            print("❌ No tabs found")
            return None

        if tab_index >= len(self.tabs):
            print(f"❌ Tab index {tab_index} out of range")
            return None

        ws_url = self.tabs[tab_index].get('webSocketDebuggerUrl')
        if ws_url:
            self.ws_url = ws_url
            return ws_url
        return None

    def list_tabs(self):
        """Display all available tabs"""
        if not self.tabs:
            self.get_tabs()

        if not self.tabs:
            print("❌ No tabs found")
            return

        print("\n📑 Available Tabs:")
        print("=" * 60)
        for i, tab in enumerate(self.tabs):
            title = tab.get('title', 'Untitled')[:50]
            url = tab.get('url', '')[:50]
            print(f"  [{i}] {title}")
            print(f"      URL: {url}")
            print()

    def execute_script(self, script: str, tab_index: int = 0, timeout: int = 180) -> Optional[Any]:
        """Execute JavaScript using Python websocket with proper handling"""
        ws_url = self.get_websocket_url(tab_index)
        if not ws_url:
            return None

        print(f"✅ Using WebSocket: {ws_url}")
        print(f"⏳ Executing script (timeout: {timeout}s)...")

        try:
            # Connect with origin header
            ws = websocket.create_connection(
                ws_url,
                timeout=10,
                header={"Origin": f"http://127.0.0.1:{self.port}"}
            )
            
            # Enable Runtime
            ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
            
            # Wait for the enable response
            enable_response = ws.recv()
            
            # Execute script
            cmd = {
                "id": 2,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": script,
                    "returnByValue": True,
                    "awaitPromise": True
                }
            }
            ws.send(json.dumps(cmd))
            
            # Collect all responses until we get our result
            result = None
            start_time = time.time()
            responses = []
            
            while time.time() - start_time < timeout:
                try:
                    response = ws.recv()
                    responses.append(response)
                    data = json.loads(response)
                    
                    # Check if this is our response
                    if 'id' in data and data['id'] == 2:
                        if 'result' in data and 'result' in data['result']:
                            result = data['result']['result'].get('value')
                            break
                        elif 'error' in data:
                            print(f"⚠️ Script error: {data['error']}")
                            break
                except websocket.WebSocketTimeoutException:
                    # No data received, continue waiting
                    continue
                except Exception as e:
                    # If we get an error, check if we already have the result
                    break
            
            ws.close()
            
            if result is not None:
                return result
            else:
                # Check if we got any response at all
                if responses:
                    print(f"⚠️ Received {len(responses)} responses but no result")
                    # Show the last response for debugging
                    try:
                        last = json.loads(responses[-1])
                        print(f"Last response: {json.dumps(last, indent=2)[:500]}")
                    except:
                        pass
                return None
            
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return None

    def extract_reddit_posts(self, search_query: str = "cats", max_scrolls: int = 20, tab_index: int = 0) -> Optional[List[Dict]]:
        """Extract Reddit posts with auto-scrolling"""
        
        # Simplified script that we know works
        script = f"""
        (async function() {{
            const searchQuery = "{search_query}";
            const maxScrolls = {max_scrolls};
            
            // Navigate to search
            window.location.href = `https://www.reddit.com/search/?q=${{encodeURIComponent(searchQuery)}}`;
            await new Promise(resolve => setTimeout(resolve, 4000));
            
            function extractCurrentPosts() {{
                const posts = [];
                const postUnits = document.querySelectorAll('[data-testid="sdui-post-unit"]');
                
                postUnits.forEach(unit => {{
                    const subredditLink = unit.querySelector('a[href*="/r/"]');
                    const subreddit = subredditLink?.textContent?.trim() || '';
                    
                    const titleElement = unit.querySelector('[data-testid="post-title-text"]');
                    const title = titleElement?.textContent?.trim() || '';
                    
                    const postLink = unit.querySelector('[data-testid="post-title-text"]');
                    const postUrl = postLink?.getAttribute('href') || '';
                    
                    const voteElement = unit.querySelector('[data-testid="search-counter-row"] faceplate-number:first-child');
                    const votes = voteElement?.getAttribute('number') || '';
                    
                    const commentElement = unit.querySelector('[data-testid="search-counter-row"] faceplate-number:last-child');
                    const comments = commentElement?.getAttribute('number') || '';
                    
                    const timeElement = unit.querySelector('faceplate-timeago');
                    const timeAgo = timeElement?.textContent?.trim() || '';
                    
                    if ((title || subreddit) && !posts.some(p => p.url === postUrl)) {{
                        posts.push({{
                            subreddit: subreddit,
                            title: title,
                            url: postUrl.startsWith('http') ? postUrl : `https://www.reddit.com${{postUrl}}`,
                            votes: votes,
                            comments: comments,
                            timeAgo: timeAgo
                        }});
                    }}
                }});
                
                return posts;
            }}
            
            const allPosts = [];
            let scrollAttempts = 0;
            let noNewPostsCount = 0;
            
            while (scrollAttempts < maxScrolls) {{
                const currentPosts = extractCurrentPosts();
                let newPostsCount = 0;
                
                currentPosts.forEach(post => {{
                    if (!allPosts.some(p => p.url === post.url)) {{
                        allPosts.push(post);
                        newPostsCount++;
                    }}
                }});
                
                if (newPostsCount === 0) {{
                    noNewPostsCount++;
                }} else {{
                    noNewPostsCount = 0;
                }}
                
                if (noNewPostsCount >= 3) {{
                    break;
                }}
                
                window.scrollTo(0, document.documentElement.scrollHeight);
                scrollAttempts++;
                await new Promise(resolve => setTimeout(resolve, 1500));
            }}
            
            return allPosts;
        }})()
        """
        
        return self.execute_script(script, tab_index, timeout=180)

def main():
    print("🔧 Dynamic Chrome JavaScript Executor")
    print("=" * 60)
    
    # Get port
    port_input = input("🔌 Chrome debug port (default 9227): ").strip()
    port = int(port_input) if port_input else 9227
    
    # Create executor
    executor = ChromeJSExecutor(port)
    
    # Check connection
    print(f"\n📡 Connecting to Chrome on port {port}...")
    tabs = executor.get_tabs()
    
    if not tabs:
        print("❌ No tabs found. Make sure Chrome is running with:")
        print(f"   chromium-browser --remote-debugging-port={port}")
        return
    
    print(f"✅ Found {len(tabs)} tabs")
    executor.list_tabs()
    
    # Select tab
    tab_input = input(f"\n📑 Select tab (0-{len(tabs)-1}, default 0): ").strip()
    tab_index = int(tab_input) if tab_input else 0
    
    # Main loop
    while True:
        print("\n" + "=" * 60)
        print("📝 Options:")
        print("  1. Execute JavaScript")
        print("  2. Extract Reddit posts (auto-scrolling)")
        print("  3. List tabs")
        print("  4. Change tab")
        print("  0. Exit")
        print("=" * 60)
        
        choice = input("Select option: ").strip()
        
        if choice == "0":
            print("👋 Goodbye!")
            break
        
        elif choice == "1":
            print("\n📝 Enter JavaScript (type 'END' on a new line when done):")
            print("💡 Tip: Wrap in async function if using await")
            lines = []
            while True:
                line = input()
                if line.strip() == "END":
                    break
                lines.append(line)
            script = "\n".join(lines)
            
            if script:
                result = executor.execute_script(script, tab_index)
                if result is not None:
                    print(f"\n✅ Result: {json.dumps(result, indent=2, default=str)[:3000]}")
                else:
                    print("\n❌ No result returned")
        
        elif choice == "2":
            query = input("🔎 Search term (default: cats): ").strip()
            query = query if query else "cats"
            
            scrolls_input = input("📜 Max scrolls (default: 20): ").strip()
            max_scrolls = int(scrolls_input) if scrolls_input else 20
            
            print(f"\n⏳ Searching for '{query}' and extracting posts...")
            print("⏱️ This may take a while (scrolling through pages)...")
            posts = executor.extract_reddit_posts(query, max_scrolls, tab_index)
            
            if posts:
                print(f"\n✅ Found {len(posts)} posts!")
                
                # Display first 10
                print("\n📝 First 10 posts:")
                for i, post in enumerate(posts[:10], 1):
                    print(f"\n{i}. {post.get('title', 'No title')[:60]}")
                    print(f"   r/{post.get('subreddit', 'Unknown')}")
                    print(f"   Votes: {post.get('votes', 'N/A')} | Comments: {post.get('comments', 'N/A')}")
                    print(f"   Time: {post.get('timeAgo', 'N/A')}")
                
                # Save option
                save = input("\n💾 Save results to file? (y/n): ").strip().lower()
                if save == 'y':
                    timestamp = int(time.time())
                    json_file = f"reddit_{query}_{timestamp}.json"
                    csv_file = f"reddit_{query}_{timestamp}.csv"
                    
                    with open(json_file, 'w') as f:
                        json.dump(posts, f, indent=2)
                    print(f"✅ Saved JSON to {json_file}")
                    
                    with open(csv_file, 'w') as f:
                        f.write("subreddit,title,votes,comments,timeAgo,url\n")
                        for post in posts:
                            title = post.get('title', '').replace(',', ' ').replace('\n', ' ')
                            f.write(f"{post.get('subreddit', '')},{title},{post.get('votes', '')},{post.get('comments', '')},{post.get('timeAgo', '')},{post.get('url', '')}\n")
                    print(f"✅ Saved CSV to {csv_file}")
            else:
                print("❌ No posts found")
        
        elif choice == "3":
            executor.list_tabs()
        
        elif choice == "4":
            tab_input = input(f"\n📑 Select tab (0-{len(tabs)-1}): ").strip()
            if tab_input:
                tab_index = int(tab_input)
                ws_url = executor.get_websocket_url(tab_index)
                if ws_url:
                    print(f"✅ Switched to tab {tab_index}")
                else:
                    print(f"❌ Invalid tab index")
        
        else:
            print("❌ Invalid choice")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted. Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
